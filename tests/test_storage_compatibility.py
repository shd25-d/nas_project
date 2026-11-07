"""Real file operations with only the unsupported kernel syscall simulated."""
import concurrent.futures
import ctypes
import errno
import os

import pytest

from server import storage
from tests.test_files import upload


class UnsupportedRename:
    def __call__(self, *args):
        ctypes.set_errno(errno.EINVAL)
        return -1


@pytest.fixture
def without_exclusive_rename(monkeypatch):
    class Libc:
        renameat2 = UnsupportedRename()
        renameatx_np = UnsupportedRename()

    monkeypatch.setattr(storage, 'libc', Libc())


def test_upload_on_filesystem_without_exclusive_rename(signed, settings, without_exclusive_rename):
    assert signed.post('/api/folders', json={'path': '', 'name': '자료'}).status_code == 201
    result = upload(signed, 'hello.txt', b'complete original bytes', '자료')
    assert result.status_code == 201, result.text
    assert signed.get('/api/content', params={'path': '자료/hello.txt'}).content == b'complete original bytes'
    assert list((settings.files_dir / '.nas-upload').iterdir()) == []
    assert list((settings.files_dir / '자료' / '.nas-upload').iterdir()) == []


def test_upload_stages_beside_destination_to_avoid_mergerfs_branch_crossing(signed, settings, without_exclusive_rename, monkeypatch):
    real_link = os.link

    def path_preserving_link(source, destination, *, src_dir_fd, dst_dir_fd, follow_symlinks):
        source_parent = os.stat('..', dir_fd=src_dir_fd)
        destination_parent = os.fstat(dst_dir_fd)
        if (source_parent.st_dev, source_parent.st_ino) != (destination_parent.st_dev, destination_parent.st_ino):
            raise OSError(errno.EXDEV, 'Path-preserving branch mismatch')
        return real_link(source, destination, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(storage.os, 'link', path_preserving_link)
    signed.post('/api/folders', json={'path': '', 'name': 'nested'})
    response = upload(signed, 'data.txt', b'nested complete bytes', 'nested')
    assert response.status_code == 201, response.text
    assert (settings.files_dir / 'nested' / 'data.txt').read_bytes() == b'nested complete bytes'
    names = [entry['name'] for entry in signed.get('/api/files?path=nested').json()['entries']]
    assert names == ['data.txt']


def test_concurrent_fallback_uploads_never_overwrite(signed, without_exclusive_rename):
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda body: upload(signed, 'same.txt', body), [b'one', b'two']))
    assert sorted(result.status_code for result in results) == [201, 409]
    assert signed.get('/api/content?path=same.txt').content in (b'one', b'two')


def test_fallback_checks_atomic_destination_collision(signed, settings, monkeypatch):
    class RacingRename:
        def __call__(self, source_fd, source, target_fd, target, flags):
            # Another writer creates the destination after upload's initial existence check.
            fd = os.open(os.fsdecode(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=target_fd)
            os.write(fd, b'other writer')
            os.close(fd)
            ctypes.set_errno(errno.EINVAL)
            return -1

    class Libc:
        renameat2 = RacingRename()
        renameatx_np = RacingRename()

    monkeypatch.setattr(storage, 'libc', Libc())
    result = upload(signed, 'race.txt', b'must not replace')
    assert result.status_code == 409, result.text
    assert (settings.files_dir / 'race.txt').read_bytes() == b'other writer'
    assert list((settings.files_dir / '.nas-upload').iterdir()) == []


def test_file_move_fallback_preserves_source_and_destination_on_collision(signed, settings, without_exclusive_rename):
    (settings.files_dir / 'source.txt').write_bytes(b'source')
    (settings.files_dir / 'target.txt').write_bytes(b'original')
    result = signed.patch('/api/entry', json={'path': 'source.txt', 'destination': 'target.txt'})
    assert result.status_code == 409, result.text
    assert (settings.files_dir / 'source.txt').read_bytes() == b'source'
    assert (settings.files_dir / 'target.txt').read_bytes() == b'original'
    assert signed.patch('/api/entry', json={'path': 'source.txt', 'destination': 'renamed.txt'}).status_code == 200
    assert not (settings.files_dir / 'source.txt').exists()
    assert (settings.files_dir / 'renamed.txt').read_bytes() == b'source'


def test_unsupported_directory_move_is_explicit_and_keeps_data(signed, settings, without_exclusive_rename):
    (settings.files_dir / 'folder').mkdir()
    (settings.files_dir / 'folder' / 'keep.txt').write_bytes(b'keep')
    result = signed.patch('/api/entry', json={'path': 'folder', 'destination': 'renamed'})
    assert result.status_code == 503, result.text
    assert '폴더' in result.json()['detail']
    assert (settings.files_dir / 'folder' / 'keep.txt').read_bytes() == b'keep'
    assert not (settings.files_dir / 'renamed').exists()


def test_failed_hardlink_has_actionable_error_without_partial_file(signed, settings, without_exclusive_rename, monkeypatch):
    def unsupported_link(*args, **kwargs):
        raise OSError(errno.EXDEV, 'Cross-device link')

    monkeypatch.setattr(storage.os, 'link', unsupported_link)
    result = upload(signed, 'failed.txt', b'complete bytes')
    assert result.status_code == 503, result.text
    assert '저장소' in result.json()['detail']
    assert not (settings.files_dir / 'failed.txt').exists()
    assert list((settings.files_dir / '.nas-upload').iterdir()) == []


def test_first_nested_upload_cleans_stale_staging(signed, settings, without_exclusive_rename):
    staging = settings.files_dir / 'nested' / '.nas-upload'
    staging.mkdir(parents=True)
    (staging / 'interrupted').write_bytes(b'partial previous upload')
    assert upload(signed, 'complete.txt', b'complete', 'nested').status_code == 201
    assert list(staging.iterdir()) == []
    assert (settings.files_dir / 'nested' / 'complete.txt').read_bytes() == b'complete'
