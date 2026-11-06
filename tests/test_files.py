import concurrent.futures
from pathlib import Path

import pytest


def upload(client, name, content=b'hello', path=''):
    return client.post('/api/upload', params={'path': path, 'name': name}, content=content,
                       headers={'Content-Type': 'application/octet-stream'})


def test_no_file_bytes_without_auth(client, settings):
    settings.files_dir.mkdir(exist_ok=True)
    (settings.files_dir / 'secret.txt').write_text('private')
    for route in ['/api/files', '/api/content?path=secret.txt', '/api/preview?path=secret.txt']:
        assert client.get(route).status_code == 401


def test_roundtrip_and_folder_operations(signed, settings):
    assert signed.post('/api/folders', json={'path': '', 'name': '자료'}).status_code == 201
    assert upload(signed, '테스트.py', b'print("hello")\n', '자료').status_code == 201
    listing = signed.get('/api/files', params={'path': '자료'}).json()
    assert listing['entries'][0]['name'] == '테스트.py'
    assert listing['entries'][0]['size'] == 15
    assert signed.get('/api/content', params={'path': '자료/테스트.py', 'download': 'true'}).content == b'print("hello")\n'
    assert signed.patch('/api/entry', json={'path': '자료/테스트.py', 'destination': 'renamed.cpp'}).status_code == 200
    assert signed.delete('/api/entry', params={'path': '자료'}).status_code == 200
    assert signed.delete('/api/entry', params={'path': 'renamed.cpp'}).status_code == 200
    assert signed.get('/api/files').json()['entries'] == []


def test_collision_preserves_original(signed):
    assert upload(signed, 'a.txt', b'original').status_code == 201
    assert upload(signed, 'a.txt', b'replacement').status_code == 409
    assert upload(signed, 'b.txt', b'other').status_code == 201
    assert signed.patch('/api/entry', json={'path': 'b.txt', 'destination': 'a.txt'}).status_code == 409
    assert signed.get('/api/content?path=a.txt').content == b'original'
    assert signed.get('/api/content?path=b.txt').content == b'other'


def test_concurrent_uploads_cannot_overwrite(signed):
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda data: upload(signed, 'same.txt', data), [b'one', b'two']))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert signed.get('/api/content?path=same.txt').content in (b'one', b'two')


def test_upload_limits_and_hidden_staging_cleanup(signed, settings):
    assert upload(signed, 'big.txt', b'x' * (settings.max_upload_bytes + 1)).status_code == 413
    assert signed.get('/api/files').json()['entries'] == []
    assert list((settings.files_dir / '.nas-upload').iterdir()) == []


@pytest.mark.parametrize('path', ['../private', '/etc/passwd', 'a/../../x', '.nas-upload', 'a\\b', 'a//b'])
def test_paths_reject_escape_and_reserved_storage(signed, path):
    assert signed.get('/api/files', params={'path': path}).status_code == 400


def test_symlinks_are_not_followed(signed, settings, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'private.txt').write_text('secret')
    (settings.files_dir / 'escape').symlink_to(outside, target_is_directory=True)
    (settings.files_dir / 'file.txt').symlink_to(outside / 'private.txt')
    assert signed.get('/api/files').json()['entries'] == []
    for path in ['escape', 'escape/private.txt', 'file.txt']:
        assert signed.get('/api/content', params={'path': path}).status_code in (400, 404)
    assert upload(signed, 'new.txt', b'x', 'escape').status_code in (400, 404)
    assert not (outside / 'new.txt').exists()


def test_rename_and_delete_never_follow_directory_symlinks(signed, settings, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'keep').write_text('keep')
    (settings.files_dir / 'folder').mkdir()
    (settings.files_dir / 'folder' / 'link').symlink_to(outside, target_is_directory=True)
    assert signed.delete('/api/entry?path=folder').status_code == 200
    assert (outside / 'keep').read_text() == 'keep'


def test_range_and_head(signed):
    upload(signed, 'movie.mp4', b'0123456789')
    result = signed.get('/api/content?path=movie.mp4', headers={'Range': 'bytes=2-5'})
    assert result.status_code == 206
    assert result.content == b'2345'
    assert result.headers['content-range'] == 'bytes 2-5/10'
    assert signed.get('/api/content?path=movie.mp4', headers={'Range': 'bytes=-3'}).content == b'789'
    assert signed.get('/api/content?path=movie.mp4', headers={'Range': 'bytes=10-'}).status_code == 416
    result = signed.head('/api/content?path=movie.mp4')
    assert result.status_code == 200
    assert result.content == b''
    assert result.headers['content-length'] == '10'


def test_mutations_require_csrf(signed):
    signed.headers.pop('X-CSRF-Token')
    assert upload(signed, 'x.txt').status_code == 403
    assert signed.post('/api/folders', json={'path': '', 'name': 'x'}).status_code == 403


def test_root_and_self_descendant_moves_forbidden(signed):
    assert signed.delete('/api/entry?path=').status_code == 400
    signed.post('/api/folders', json={'path': '', 'name': 'parent'})
    assert signed.patch('/api/entry', json={'path': 'parent', 'destination': 'parent/child'}).status_code == 400


def test_html_download_is_not_executable(signed):
    upload(signed, 'page.html', b'<script>alert(1)</script>')
    response = signed.get('/api/content?path=page.html')
    assert response.headers['content-type'].startswith('application/octet-stream')
    assert response.headers['content-disposition'].startswith('attachment;')
