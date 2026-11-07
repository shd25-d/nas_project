"""Authenticated ZIP streams with descriptor-relative, no-symlink traversal."""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
import io
import ntpath
import os
import stat
import time
from urllib.parse import quote
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .auth import authenticated
from .storage import DIR_FLAGS, RESERVED

router = APIRouter(prefix='/api')
MAX_ENTRIES = 100_000
MAX_DEPTH = 256
CHUNK_SIZE = 256 * 1024


@dataclass(frozen=True)
class Entry:
    parts: tuple
    info: os.stat_result


class ZipBuffer:
    """Unseekable ZIP output, drained after each bounded input block."""
    def __init__(self):
        self.chunks = deque()
        self.position = 0

    def write(self, data):
        if data:
            self.chunks.append(bytes(data))
            self.position += len(data)
        return len(data)

    def tell(self):
        return self.position

    def seek(self, *args):
        raise io.UnsupportedOperation('ZIP output is streamed')

    def flush(self):
        pass

    def drain(self):
        while self.chunks:
            yield self.chunks.popleft()


@contextmanager
def directory_from(root, parts):
    fd = os.dup(root)
    try:
        for part in parts:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def safe_name(name):
    # POSIX permits backslashes and drive-like names; reject ZIP extraction escapes.
    if name in ('', '.', '..') or '/' in name or '\\' in name or ntpath.splitdrive(name)[0] or any(ord(c) < 32 for c in name):
        raise HTTPException(400, 'ZIP에 안전하게 담을 수 없는 파일 이름이 있습니다. 이름을 변경하세요.')
    try:
        name.encode('utf-8')
    except UnicodeEncodeError:
        raise HTTPException(400, 'ZIP 다운로드에는 UTF-8로 표현할 수 있는 파일 이름이 필요합니다.')
    return name


def snapshot(storage, path):
    """Read metadata only before sending headers, so errors remain normal API errors."""
    label = safe_name(path.rsplit('/', 1)[-1]) if path else '내 파일'
    with storage.lock, storage.directory(path) as root:
        root_info = os.fstat(root)
        entries = [Entry((), root_info)]
        pending = [()]
        while pending:
            parts = pending.pop()
            with directory_from(root, parts) as fd:
                for name in sorted(os.listdir(fd)):
                    if name == RESERVED:
                        continue
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                        continue
                    relative = parts + (safe_name(name),)
                    if len(relative) > MAX_DEPTH or len('/'.join((label,) + relative).encode('utf-8')) > 65_530:
                        raise HTTPException(413, 'ZIP의 폴더 깊이나 경로 길이 제한을 초과했습니다. 하위 폴더를 나누어 다운로드하세요.')
                    if len(entries) >= MAX_ENTRIES:
                        raise HTTPException(413, 'ZIP에는 폴더를 포함해 최대 100,000개 항목을 담을 수 있습니다. 폴더를 나누어 다운로드하세요.')
                    if stat.S_ISREG(info.st_mode):
                        source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                        try:
                            info = os.fstat(source)
                            if not stat.S_ISREG(info.st_mode):
                                raise HTTPException(409, 'ZIP 준비 중 파일이 변경되었습니다. 다시 시도하세요.')
                        finally:
                            os.close(source)
                    entries.append(Entry(relative, info))
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(relative)
        return label, entries


def zip_info(name, info, is_directory):
    date = time.localtime(info.st_mtime)[:6]
    if date[0] < 1980:
        date = (1980, 1, 1, 0, 0, 0)
    elif date[0] > 2107:
        date = (2107, 12, 31, 23, 59, 58)
    result = zipfile.ZipInfo(name + ('/' if is_directory else ''), date_time=date)
    result.create_system = 3
    result.external_attr = ((stat.S_IFDIR | 0o755) if is_directory else (stat.S_IFREG | 0o644)) << 16
    if is_directory:
        result.external_attr |= 0x10
    result.compress_type = zipfile.ZIP_STORED if is_directory else zipfile.ZIP_DEFLATED
    # ZipInfo's compression-level field is private on the supported Python 3.12.
    result._compresslevel = 1
    return result


def unchanged(expected, current):
    return (expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns) == (
        current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)


def archive_chunks(storage, path, label, entries):
    output = ZipBuffer()
    with storage.directory(path) as root:
        current = os.fstat(root)
        expected = entries[0].info
        if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
            raise RuntimeError('ZIP source folder changed during download')
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
            for entry in entries:
                name = '/'.join((label,) + entry.parts)
                is_directory = stat.S_ISDIR(entry.info.st_mode)
                info = zip_info(name, entry.info, is_directory)
                if is_directory:
                    archive.writestr(info, b'')
                    yield from output.drain()
                    continue
                with directory_from(root, entry.parts[:-1]) as parent:
                    fd = os.open(entry.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                    with os.fdopen(fd, 'rb') as source:
                        current = os.fstat(source.fileno())
                        if not stat.S_ISREG(current.st_mode) or not unchanged(entry.info, current):
                            raise RuntimeError('ZIP source file changed during download')
                        with archive.open(info, 'w', force_zip64=True) as member:
                            yield from output.drain()
                            remaining = entry.info.st_size
                            while remaining:
                                data = source.read(min(remaining, CHUNK_SIZE))
                                if not data:
                                    raise RuntimeError('ZIP source file was truncated during download')
                                remaining -= len(data)
                                member.write(data)
                                yield from output.drain()
                            if not unchanged(entry.info, os.fstat(source.fileno())):
                                raise RuntimeError('ZIP source file changed during download')
                        yield from output.drain()
        yield from output.drain()


@router.api_route('/archive', methods=['GET', 'HEAD'], dependencies=[Depends(authenticated)])
def download_archive(request: Request, path: str = '', check: bool = False):
    storage = request.app.state.storage
    label, entries = snapshot(storage, path)
    if check:
        return {'filename': label + '.zip'}
    filename = quote(label + '.zip', safe='')
    headers = {'Content-Disposition': f"attachment; filename=\"folder.zip\"; filename*=UTF-8''{filename}",
               'Accept-Ranges': 'none'}
    if request.method == 'HEAD':
        return Response(media_type='application/zip', headers=headers)
    stream = archive_chunks(storage, path, label, entries)
    return StreamingResponse(stream, media_type='application/zip', headers=headers, background=BackgroundTask(stream.close))
