from io import BytesIO
import os
import zipfile

import pytest
from fastapi import HTTPException

from server import archives


def test_archive_requires_login(client):
    assert client.get('/api/archive?path=').status_code == 401
    assert client.head('/api/archive?path=').status_code == 401


def test_folder_archive_preserves_tree_unicode_empty_folders_and_bytes(signed, settings):
    folder = settings.files_dir / '자료'
    (folder / '하위' / '빈 폴더').mkdir(parents=True)
    (folder / 'hello.py').write_bytes(b'print("hello")\n')
    (folder / '하위' / '사진.jpg').write_bytes(bytes(range(256)) * 32)
    (folder / 'zero.txt').touch()
    response = signed.get('/api/archive', params={'path': '자료'})
    assert response.status_code == 200, response.text[:100]
    assert response.headers['content-type'] == 'application/zip'
    assert "%EC%9E%90%EB%A3%8C.zip" in response.headers['content-disposition']
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {'자료/', '자료/하위/', '자료/하위/빈 폴더/', '자료/hello.py', '자료/zero.txt', '자료/하위/사진.jpg'}
        assert archive.read('자료/hello.py') == b'print("hello")\n'
        assert archive.read('자료/하위/사진.jpg') == bytes(range(256)) * 32
        assert archive.read('자료/zero.txt') == b''
    assert (folder / 'hello.py').read_bytes() == b'print("hello")\n'


def test_archive_excludes_staging_symlinks_and_special_files(signed, settings, tmp_path):
    root = settings.files_dir
    (root / 'nested').mkdir()
    (root / 'nested' / '.nas-upload').mkdir()
    (root / 'nested' / '.nas-upload' / 'unfinished').write_text('partial')
    (root / '.nas-upload' / 'unfinished').write_text('partial')
    (root / 'nested' / 'safe.txt').write_text('safe')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.txt').write_text('secret')
    (root / 'link').symlink_to(outside, target_is_directory=True)
    (root / 'nested' / 'link.txt').symlink_to(outside / 'secret.txt')
    os.mkfifo(root / 'pipe')
    response = signed.get('/api/archive?path=')
    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {'내 파일/', '내 파일/nested/', '내 파일/nested/safe.txt'}


@pytest.mark.parametrize('path', ['../secret', '/etc', '.nas-upload', 'folder/../../secret'])
def test_archive_blocks_unsafe_requested_paths(signed, path):
    assert signed.get('/api/archive', params={'path': path}).status_code == 400


def test_archive_rejects_missing_folder_file_and_link(signed, settings, tmp_path):
    (settings.files_dir / 'file.txt').write_text('text')
    (settings.files_dir / 'link').symlink_to(tmp_path, target_is_directory=True)
    assert signed.get('/api/archive?path=missing').status_code == 404
    assert signed.get('/api/archive?path=file.txt').status_code == 404
    assert signed.get('/api/archive?path=link').status_code in (400, 404)


def test_head_validates_archive_without_generating_zip(signed, settings):
    (settings.files_dir / 'empty').mkdir()
    response = signed.head('/api/archive?path=empty')
    assert response.status_code == 200
    assert response.content == b''
    assert response.headers['content-type'] == 'application/zip'
    with zipfile.ZipFile(BytesIO(signed.get('/api/archive?path=empty').content)) as archive:
        assert archive.namelist() == ['empty/']


def test_archive_check_returns_json_without_a_zip(signed, settings):
    (settings.files_dir / '자료').mkdir()
    response = signed.get('/api/archive', params={'path': '자료', 'check': 'true'})
    assert response.status_code == 200
    assert response.json() == {'filename': '자료.zip'}
    assert 'content-disposition' not in response.headers


def test_archive_check_errors_include_actionable_detail(signed, settings):
    (settings.files_dir / r'..\escape.txt').touch()
    response = signed.get('/api/archive?check=true')
    assert response.status_code == 400
    assert '이름' in response.json()['detail']


def test_host_filenames_cannot_create_zip_slip_paths(signed, settings):
    (settings.files_dir / r'..\escape.txt').write_text('unsafe')
    response = signed.get('/api/archive?path=')
    assert response.status_code == 400
    assert 'ZIP' in response.json()['detail']


def test_archive_emits_bounded_chunks_with_valid_crc(signed, settings):
    data = os.urandom(3 * 1024 * 1024)
    (settings.files_dir / 'large.bin').write_bytes(data)
    storage = signed.app.state.storage
    label, entries = archives.snapshot(storage, '')
    stream = archives.archive_chunks(storage, '', label, entries)
    chunks = list(stream)
    assert len(chunks) > 10
    assert max(map(len, chunks)) < 512 * 1024
    with zipfile.ZipFile(BytesIO(b''.join(chunks))) as archive:
        assert archive.read('내 파일/large.bin') == data
        assert archive.testzip() is None


def test_symlink_swap_after_snapshot_does_not_escape_storage(signed, settings, tmp_path):
    (settings.files_dir / 'file.txt').write_text('original')
    outside = tmp_path / 'secret.txt'
    outside.write_text('private')
    storage = signed.app.state.storage
    label, entries = archives.snapshot(storage, '')
    (settings.files_dir / 'file.txt').unlink()
    (settings.files_dir / 'file.txt').symlink_to(outside)
    with pytest.raises(HTTPException):
        list(archives.archive_chunks(storage, '', label, entries))


def test_changed_file_aborts_archive_instead_of_silently_omitting_it(signed, settings):
    source = settings.files_dir / 'file.txt'
    source.write_text('original')
    storage = signed.app.state.storage
    label, entries = archives.snapshot(storage, '')
    source.write_text('changed file contents')
    with pytest.raises(RuntimeError, match='changed'):
        list(archives.archive_chunks(storage, '', label, entries))


def test_archive_entry_limit_returns_api_error_before_streaming(signed, settings, monkeypatch):
    monkeypatch.setattr(archives, 'MAX_ENTRIES', 3)
    for name in ('a', 'b', 'c'):
        (settings.files_dir / name).touch()
    assert signed.get('/api/archive?path=').status_code == 413


@pytest.mark.skipif(os.geteuid() == 0, reason='root can read mode-000 files')
def test_unreadable_file_is_rejected_before_zip_headers(signed, settings):
    source = settings.files_dir / 'unreadable.txt'
    source.write_text('private')
    source.chmod(0)
    try:
        assert signed.get('/api/archive?path=').status_code == 403
    finally:
        source.chmod(0o600)
