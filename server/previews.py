import json
import os
import subprocess
import sys
import threading

from fastapi import APIRouter, Depends, HTTPException, Request

from .auth import authenticated
from .formats import kind

router = APIRouter(prefix='/api')
conversion_slots = threading.BoundedSemaphore(2)


@router.get('/preview', dependencies=[Depends(authenticated)])
def preview(request: Request, path: str):
    preview_kind = kind(path)
    if preview_kind not in ('text', 'docx'):
        raise HTTPException(415, '이 형식은 다운로드해서 확인하세요.')
    fd = request.app.state.storage.open_file(path)
    try:
        limit = 2 * 1024 * 1024 if preview_kind == 'text' else 10 * 1024 * 1024
        if os.fstat(fd).st_size > limit:
            raise HTTPException(413, '미리보기 크기를 초과했습니다. 원본을 다운로드하세요.')
        if preview_kind == 'text':
            with os.fdopen(os.dup(fd), 'rb') as source:
                raw = source.read(limit + 1)
            if len(raw) > limit:
                raise HTTPException(413, '미리보기 크기를 초과했습니다.')
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                raise HTTPException(415, 'UTF-8 텍스트만 미리볼 수 있습니다. 원본을 다운로드하세요.')
            if '\x00' in text:
                raise HTTPException(415, '바이너리 파일은 텍스트로 미리볼 수 없습니다.')
            return {'kind': 'text', 'text': text}
        if not conversion_slots.acquire(blocking=False):
            raise HTTPException(503, '다른 문서를 변환 중입니다. 잠시 후 다시 시도하세요.')
        try:
            result = subprocess.run([sys.executable, '-m', 'server.docx_worker', str(fd)],
                                    pass_fds=(fd,), capture_output=True, timeout=15, check=False)
            if result.returncode != 0:
                raise HTTPException(422, '문서 변환을 완료할 수 없습니다. 원본을 다운로드하세요.')
            data = json.loads(result.stdout)
            if 'error' in data:
                raise HTTPException(data['status'], data['error'])
            return data
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            raise HTTPException(422, '문서 변환 시간이 초과되었거나 변환에 실패했습니다.')
        finally:
            conversion_slots.release()
    finally:
        os.close(fd)
