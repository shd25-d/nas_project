"""Descriptor-relative storage. No path component may be a symlink."""
from contextlib import contextmanager
import ctypes
import errno
import os
from pathlib import Path
import stat
import sys
import threading

from fastapi import HTTPException

DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
RESERVED = '.nas-upload'
libc = ctypes.CDLL(None, use_errno=True)


def components(path: str, allow_root=True):
    if len(path) > 4096 or '\\' in path or '\x00' in path:
        raise HTTPException(400, '올바르지 않은 경로입니다.')
    if path == '' and allow_root:
        return []
    parts = path.split('/')
    if any(p in ('', '.', '..', RESERVED) or len(p.encode('utf-8')) > 255 for p in parts):
        raise HTTPException(400, '올바르지 않은 경로입니다.')
    return parts


def filename(name: str):
    parts = components(name, allow_root=False)
    if len(parts) != 1 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise HTTPException(400, '파일 이름에 경로나 제어 문자를 사용할 수 없습니다.')
    return name


@contextmanager
def translate_errors():
    try:
        yield
    except FileExistsError:
        raise HTTPException(409, '같은 이름이 이미 있습니다. 다른 이름을 사용하세요.')
    except (FileNotFoundError, NotADirectoryError):
        raise HTTPException(404, '파일 또는 폴더를 찾을 수 없습니다.')
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.EINVAL):
            raise HTTPException(400, '지원하지 않는 경로입니다.')
        if error.errno == errno.ENOSPC:
            raise HTTPException(507, '저장 공간이 부족합니다.')
        if error.errno in (errno.EACCES, errno.EPERM):
            raise HTTPException(403, '저장 폴더의 접근 권한을 확인하세요.')
        raise


def rename_exclusive(src_fd: int, source: str, dst_fd: int, destination: str):
    """Kernel-level no-replace rename, including directories (Linux and macOS)."""
    if sys.platform == 'darwin':
        function, flags = libc.renameatx_np, 4  # RENAME_EXCL
    elif hasattr(libc, 'renameat2'):
        function, flags = libc.renameat2, 1  # RENAME_NOREPLACE
    else:
        raise HTTPException(503, '이 운영체제는 안전한 파일 이동을 지원하지 않습니다.')
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(src_fd, os.fsencode(source), dst_fd, os.fsencode(destination), flags) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


class Storage:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.RLock()
        root.mkdir(parents=True, exist_ok=True)
        with self.directory('') as fd:
            try:
                os.mkdir(RESERVED, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            staging = os.open(RESERVED, DIR_FLAGS, dir_fd=fd)
            try:
                # One application worker owns staging; recover interrupted writes on startup.
                for name in os.listdir(staging):
                    info = os.stat(name, dir_fd=staging, follow_symlinks=False)
                    if not stat.S_ISDIR(info.st_mode):
                        os.unlink(name, dir_fd=staging)
            finally:
                os.close(staging)

    @contextmanager
    def directory(self, path: str):
        parts = components(path)
        with translate_errors():
            fd = os.open(self.root, DIR_FLAGS)
            try:
                for part in parts:
                    next_fd = os.open(part, DIR_FLAGS, dir_fd=fd)
                    os.close(fd)
                    fd = next_fd
                yield fd
            finally:
                os.close(fd)

    @contextmanager
    def parent(self, path: str):
        parts = components(path, allow_root=False)
        with self.directory('/'.join(parts[:-1])) as fd:
            yield fd, parts[-1]

    def open_file(self, path: str):
        with self.parent(path) as (parent, name):
            with translate_errors():
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    os.close(fd)
                    raise HTTPException(400, '일반 파일만 열 수 있습니다.')
                return fd

    def list(self, path: str):
        with self.directory(path) as fd:
            entries = []
            for name in os.listdir(fd):
                if name == RESERVED:
                    continue
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                    continue
                entries.append({'name': name, 'path': '/'.join(filter(None, [path, name])),
                                'is_dir': stat.S_ISDIR(info.st_mode), 'size': info.st_size if stat.S_ISREG(info.st_mode) else None,
                                'modified': info.st_mtime})
            disk = os.fstatvfs(fd)
            total, free = disk.f_blocks * disk.f_frsize, disk.f_bavail * disk.f_frsize
            return {'path': path, 'entries': entries, 'storage': {'total': total, 'free': free, 'used': total - free}}

    def mkdir(self, path, name):
        filename(name)
        with self.lock, self.directory(path) as fd, translate_errors():
            os.mkdir(name, mode=0o750, dir_fd=fd)

    def move(self, source, destination):
        source_parts = components(source, allow_root=False)
        dest_parts = components(destination, allow_root=False)
        filename(dest_parts[-1])
        if source_parts == dest_parts or dest_parts[:len(source_parts)] == source_parts:
            raise HTTPException(400, '자기 자신이나 하위 폴더로 이동할 수 없습니다.')
        with self.lock, self.parent(source) as (src_fd, src), self.parent(destination) as (dst_fd, dst), translate_errors():
            info = os.stat(src, dir_fd=src_fd, follow_symlinks=False)
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise HTTPException(400, '일반 파일과 폴더만 이동할 수 있습니다.')
            rename_exclusive(src_fd, src, dst_fd, dst)

    def remove(self, path):
        with self.lock, self.parent(path) as (parent, name), translate_errors():
            self._remove(parent, name)

    def _remove(self, parent, name):
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            fd = os.open(name, DIR_FLAGS, dir_fd=parent)
            try:
                for child in os.listdir(fd):
                    self._remove(fd, child)
            finally:
                os.close(fd)
            os.rmdir(name, dir_fd=parent)
        else:
            # Unlink the link itself, never its target, when deleting a containing folder.
            os.unlink(name, dir_fd=parent)
