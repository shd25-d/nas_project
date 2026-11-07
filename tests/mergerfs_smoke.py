"""Run inside a disposable Linux container with mergerfs and /dev/fuse, no host data."""
import ctypes
import errno
import http.cookiejar
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from server.auth import create_owner
from server.config import Settings


def main():
    print(subprocess.check_output(['mergerfs', '--version'], text=True).splitlines()[0], flush=True)
    with tempfile.TemporaryDirectory(prefix='moru-mergerfs-') as directory:
        root = Path(directory)
        disks = [root / 'disk-a', root / 'disk-b']
        pool = root / 'pool'
        for path in disks + [pool]:
            path.mkdir()
        # Put the only copy of the upload parent on disk-b, not the global staging branch.
        (disks[0] / 'files').mkdir()
        (disks[1] / 'files' / 'nested').mkdir(parents=True)
        subprocess.run(['mergerfs', '-o', 'category.create=epmfs,minfreespace=0',
                        ':'.join(map(str, disks)), str(pool)], check=True)
        server = None
        try:
            settings = Settings(files_dir=pool / 'files', app_dir=root / 'app')
            create_owner(settings, 'smoke', 'temporary test password')
            env = {**os.environ, 'NAS_FILES_DIR': str(settings.files_dir), 'NAS_APP_DIR': str(settings.app_dir)}
            with (root / 'server.log').open('w+') as log:
                server = subprocess.Popen(['uvicorn', 'server.main:create_app', '--factory', '--host', '127.0.0.1', '--port', '8766'], env=env, stdout=log, stderr=log)
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                base = 'http://127.0.0.1:8766/api'
                for _ in range(100):
                    try:
                        client.open(base + '/health', timeout=1).close()
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    log.seek(0)
                    raise RuntimeError(log.read())
                login = urllib.request.Request(base + '/login', data=json.dumps({'username': 'smoke', 'password': 'temporary test password'}).encode(), headers={'Content-Type': 'application/json'})
                with client.open(login) as response:
                    token = json.load(response)['csrf']
                body = b'mergerfs complete file\n' * 1024
                for parent, name in [('', 'root.txt'), ('nested', 'nested.txt')]:
                    request = urllib.request.Request(base + f'/upload?path={parent}&name={name}', data=body, headers={'Content-Type': 'application/octet-stream', 'X-CSRF-Token': token})
                    with client.open(request) as response:
                        assert response.status == 201
                    with client.open(base + f'/content?path={parent + "/" if parent else ""}{name}') as response:
                        assert response.read() == body
                assert (disks[1] / 'files' / 'nested' / 'nested.txt').read_bytes() == body
                with client.open(base + '/archive?path=nested') as response:
                    with zipfile.ZipFile(BytesIO(response.read())) as archive:
                        assert archive.namelist() == ['nested/', 'nested/nested.txt']
                        assert archive.read('nested/nested.txt') == body
                        assert archive.testzip() is None
                # Prove whether the real mounted filesystem rejects the native exclusive rename.
                fd = os.open(settings.files_dir, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    (settings.files_dir / 'probe.tmp').write_bytes(b'probe')
                    libc = ctypes.CDLL(None, use_errno=True)
                    result = libc.renameat2(fd, b'probe.tmp', fd, b'probe.done', 1)
                    code = ctypes.get_errno() if result else 0
                    print('Native RENAME_NOREPLACE errno:', code, errno.errorcode.get(code, 'supported'), flush=True)
                finally:
                    os.close(fd)
                try:
                    client.open(urllib.request.Request(base + '/upload?name=root.txt', data=b'must not overwrite', headers={'X-CSRF-Token': token}))
                except urllib.error.HTTPError as error:
                    assert error.code == 409
                else:
                    raise AssertionError('Existing destination was not rejected')
                assert (settings.files_dir / 'root.txt').read_bytes() == body
                print('PASS: real mergerfs, two branches, epmfs policy, root/nested upload and download, folder ZIP, byte equality, no-overwrite collision', flush=True)
        finally:
            if server:
                server.terminate()
                server.wait(timeout=10)
            subprocess.run(['fusermount', '-u', str(pool)], check=True)


if __name__ == '__main__':
    main()
