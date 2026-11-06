from email.utils import formatdate
import os
import re
import secrets
from urllib.parse import quote

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .auth import authenticated, mutation
from .formats import kind, media_type
from .storage import DIR_FLAGS, RESERVED, filename, rename_exclusive, translate_errors

router = APIRouter(prefix='/api')


class Folder(BaseModel):
    path: str = Field(default='', max_length=4096)
    name: str = Field(min_length=1, max_length=255)


class Move(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    destination: str = Field(min_length=1, max_length=4096)


@router.get('/files', dependencies=[Depends(authenticated)])
def listing(request: Request, path: str = ''):
    result = request.app.state.storage.list(path)
    for entry in result['entries']:
        entry['kind'] = 'folder' if entry['is_dir'] else kind(entry['name'])
    result['max_upload_bytes'] = request.app.state.settings.max_upload_bytes
    return result


@router.post('/folders', status_code=201, dependencies=[Depends(mutation)])
def mkdir(body: Folder, request: Request):
    request.app.state.storage.mkdir(body.path, body.name)
    return {'ok': True}


def write_all(fd, chunk):
    remaining = memoryview(chunk)
    while remaining:
        count = os.write(fd, remaining)
        remaining = remaining[count:]


@router.post('/upload', status_code=201, dependencies=[Depends(mutation)])
async def upload(request: Request, name: str, path: str = ''):
    storage, limit = request.app.state.storage, request.app.state.settings.max_upload_bytes
    filename(name)
    length = request.headers.get('content-length')
    if length:
        try:
            if int(length) > limit:
                raise HTTPException(413, '파일이 업로드 크기 제한을 초과했습니다.')
        except ValueError:
            raise HTTPException(400, '잘못된 업로드 크기입니다.')
    with storage.directory(path) as parent, storage.directory('') as root, translate_errors():
        staging = os.open(RESERVED, DIR_FLAGS, dir_fd=root)
        temporary = secrets.token_hex(24)
        fd = None
        try:
            # Fail before receiving a large body if the destination already exists.
            try:
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise HTTPException(409, '같은 이름이 이미 있습니다. 다른 이름을 사용하세요.')
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                         mode=0o640, dir_fd=staging)
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, '파일이 업로드 크기 제한을 초과했습니다.')
                if chunk:
                    await anyio.to_thread.run_sync(write_all, fd, chunk)
            await anyio.to_thread.run_sync(os.fsync, fd)
            os.close(fd)
            fd = None
            with storage.lock:
                rename_exclusive(staging, temporary, parent, name)
            return {'ok': True, 'size': size}
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=staging)
            except FileNotFoundError:
                pass
            os.close(staging)


@router.patch('/entry', dependencies=[Depends(mutation)])
def move(body: Move, request: Request):
    request.app.state.storage.move(body.path, body.destination)
    return {'ok': True}


@router.delete('/entry', dependencies=[Depends(mutation)])
def remove(request: Request, path: str):
    if path == RESERVED or path.endswith('/' + RESERVED):
        raise HTTPException(400, '내부 폴더는 삭제할 수 없습니다.')
    request.app.state.storage.remove(path)
    return {'ok': True}


def byte_range(header, size):
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
    if not match or size == 0:
        raise ValueError
    first, last = match.groups()
    if not first:
        if not last or int(last) <= 0:
            raise ValueError
        return max(0, size - int(last)), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError
    return start, end


def read_chunks(fd, start, length):
    try:
        os.lseek(fd, start, os.SEEK_SET)
        while length > 0:
            data = os.read(fd, min(length, 256 * 1024))
            if not data:
                break
            length -= len(data)
            yield data
    finally:
        os.close(fd)


@router.api_route('/content', methods=['GET', 'HEAD'], dependencies=[Depends(authenticated)])
def content(request: Request, path: str, download: bool = False):
    fd = request.app.state.storage.open_file(path)
    info = os.fstat(fd)
    size, start, end, code = info.st_size, 0, info.st_size - 1, 200
    etag = f'"{info.st_ino:x}-{info.st_mtime_ns:x}-{size:x}"'
    last_modified = formatdate(info.st_mtime, usegmt=True)
    range_header = request.headers.get('range')
    if_range = request.headers.get('if-range')
    if range_header and (not if_range or if_range in (etag, last_modified)):
        try:
            start, end = byte_range(range_header, size)
            code = 206
        except (ValueError, OverflowError):
            os.close(fd)
            return Response(status_code=416, headers={'Content-Range': f'bytes */{size}'})
    mime = media_type(path)
    disposition = 'attachment' if download or mime == 'application/octet-stream' else 'inline'
    headers = {'Content-Length': str(max(0, end - start + 1)), 'Accept-Ranges': 'bytes', 'ETag': etag,
               'Last-Modified': last_modified,
               'Content-Disposition': f"{disposition}; filename=\"download\"; filename*=UTF-8''{quote(path.split('/')[-1], safe='')}"}
    if code == 206:
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    if request.method == 'HEAD':
        os.close(fd)
        return Response(status_code=code, media_type=mime, headers=headers)
    return StreamingResponse(read_chunks(fd, start, max(0, end - start + 1)), status_code=code, media_type=mime, headers=headers)
