"""Real Docker persistence test; uses disposable host directories, account and project."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time

import httpx

from tests.test_previews import make_docx


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='moru-container-') as directory:
        temporary = Path(directory)
        (temporary / 'files').mkdir()
        (temporary / 'app').mkdir()
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        env = {**os.environ, 'NAS_FILES_PATH': str(temporary / 'files'), 'NAS_APP_PATH': str(temporary / 'app'),
               'NAS_UID': str(os.getuid()), 'NAS_GID': str(os.getgid()), 'NAS_BIND_IP': '127.0.0.1',
               'NAS_PORT': str(port), 'NAS_SECURE_COOKIE': 'false'}
        override = temporary / 'override.json'
        override.write_text(json.dumps({'services': {'nas': {'image': 'nas_project-nas:latest'}}}))
        command = ['docker', 'compose', '-f', str(root / 'compose.yaml'), '-f', str(override),
                   '-p', 'moru-smoke-' + secrets.token_hex(4)]

        def run(*args):
            result = subprocess.run(command + list(args), env=env, cwd=root, text=True, capture_output=True)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return result.stdout

        def ready(client):
            for _ in range(100):
                try:
                    if client.get('/api/health').status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.2)
            raise RuntimeError('Container readiness timed out')

        try:
            run('up', '-d', '--no-build')
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=20) as client:
                ready(client)
                assert client.get('/').status_code == 200
                assert client.get('/api/files').status_code == 401
                assert run('exec', '-T', 'nas', 'id', '-u').strip() != '0'
                run('exec', '-T', 'nas', 'python', '-c',
                    "from server.auth import create_owner; from server.config import Settings; create_owner(Settings(), 'smoke', 'temporary test password')")
                login = client.post('/api/login', json={'username': 'smoke', 'password': 'temporary test password'})
                assert login.status_code == 200, login.text
                client.headers['X-CSRF-Token'] = login.json()['csrf']
                assert client.post('/api/folders', json={'path': '', 'name': '자료'}).status_code == 201
                original = bytes(range(256)) * 8192
                response = client.post('/api/upload', params={'path': '자료', 'name': 'binary.bin'},
                                       content=(original[i:i + 65536] for i in range(0, len(original), 65536)))
                assert response.status_code == 201, response.text
                assert client.get('/api/content', params={'path': '자료/binary.bin'}).content == original
                assert client.post('/api/upload?name=sample.docx', content=make_docx('Container DOCX')).status_code == 201
                response = client.get('/api/preview?path=sample.docx')
                assert response.status_code == 200 and 'Container DOCX' in response.json()['html'], response.text
                assert client.get('/pdfjs/cmaps/Adobe-Japan1-UCS2.bcmap').status_code == 200
                run('restart', 'nas')
                ready(client)
                assert client.get('/api/session').status_code == 200
                assert client.get('/api/content', params={'path': '자료/binary.bin'}).content == original
                part = client.get('/api/content', params={'path': '자료/binary.bin'}, headers={'Range': 'bytes=7-25'})
                assert part.status_code == 206 and part.content == original[7:26]
                assert client.patch('/api/entry', json={'path': '資料', 'destination': 'missing'}).status_code == 404
                assert client.patch('/api/entry', json={'path': '자료/binary.bin', 'destination': 'renamed.bin'}).status_code == 200
                assert client.delete('/api/entry?path=renamed.bin').status_code == 200
                assert client.get('/api/content?path=renamed.bin').status_code == 404
                print('PASS: non-root Docker app, login, 2 MiB streamed upload/download, DOCX, local PDF assets, rename/delete, Range, account and file persistence across restart')
        finally:
            print(run('down', '--remove-orphans').strip())


if __name__ == '__main__':
    main()
