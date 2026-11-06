from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app
from server.auth import create_owner


@pytest.fixture
def settings(tmp_path):
    return Settings(files_dir=tmp_path / 'files', app_dir=tmp_path / 'app',
                    static_dir=tmp_path / 'static', max_upload_bytes=1024 * 1024)


@pytest.fixture
def client(settings):
    create_owner(settings, 'owner', 'correct horse battery staple')
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def signed(client):
    response = client.post('/api/login', json={'username': 'owner', 'password': 'correct horse battery staple'})
    assert response.status_code == 200
    client.headers['X-CSRF-Token'] = response.json()['csrf']
    return client
