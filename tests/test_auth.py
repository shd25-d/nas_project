import sqlite3
import time

from fastapi.testclient import TestClient

from server.main import create_app
from server.auth import create_owner


def test_setup_does_not_offer_public_registration(settings):
    with TestClient(create_app(settings)) as c:
        assert c.get('/api/session').status_code == 401
        assert c.get('/api/status').json() == {'configured': False}
        assert c.post('/api/register', json={'username': 'intruder'}).status_code == 404


def test_login_logout_and_csrf(client):
    assert client.get('/api/session').status_code == 401
    assert client.post('/api/login', json={'username': 'owner', 'password': 'wrong'}).status_code == 401
    response = client.post('/api/login', json={'username': 'owner', 'password': 'correct horse battery staple'})
    assert response.status_code == 200
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert client.get('/api/session').json()['username'] == 'owner'
    assert client.post('/api/logout').status_code == 403
    assert client.post('/api/logout', headers={'X-CSRF-Token': response.json()['csrf']}).status_code == 200
    assert client.get('/api/session').status_code == 401


def test_login_cross_origin_rejected(client):
    assert client.post('/api/login', headers={'Origin': 'https://attacker.invalid'},
                       json={'username': 'owner', 'password': 'correct horse battery staple'}).status_code == 403


def test_expired_sessions_fail_closed(signed, settings):
    with sqlite3.connect(settings.app_dir / 'nas.sqlite3') as db:
        db.execute('UPDATE sessions SET expires_at = ?', (time.time() - 1,))
    assert signed.get('/api/session').status_code == 401


def test_owner_survives_new_app_and_reset_revokes_sessions(signed, settings):
    with TestClient(create_app(settings)) as c:
        assert c.post('/api/login', json={'username': 'owner', 'password': 'correct horse battery staple'}).status_code == 200
    create_owner(settings, 'owner', 'a different long password', reset=True)
    assert signed.get('/api/session').status_code == 401
    assert signed.post('/api/login', json={'username': 'owner', 'password': 'a different long password'}).status_code == 200


def test_login_attempts_throttled(client):
    for _ in range(10):
        assert client.post('/api/login', json={'username': 'owner', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/login', json={'username': 'owner', 'password': 'wrong'}).status_code == 429
