from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .config import Settings

router = APIRouter(prefix='/api')
hasher = PasswordHasher()
COOKIE = 'nas_session'


@contextmanager
def database(settings):
    db = sqlite3.connect(settings.app_dir / 'nas.sqlite3', timeout=15)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(settings: Settings):
    settings.app_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with database(settings) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS owner (
                id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL, password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
                address TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL);
        ''')


def create_owner(settings: Settings, username: str, password: str, reset=False):
    if not username.strip() or len(username) > 64:
        raise ValueError('사용자 이름은 1~64자로 입력하세요.')
    if not 12 <= len(password) <= 1024:
        raise ValueError('비밀번호는 12~1024자로 입력하세요.')
    initialize(settings)
    password_hash = hasher.hash(password)
    with database(settings) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM owner').fetchone() and not reset:
            raise ValueError('계정이 이미 있습니다. reset-owner 명령을 사용하세요.')
        db.execute('INSERT OR REPLACE INTO owner VALUES (1, ?, ?)', (username.strip(), password_hash))
        db.execute('DELETE FROM sessions')
        db.execute('DELETE FROM attempts')


@dataclass
class Session:
    username: str
    csrf: str
    token_hash: str


def authenticated(request: Request) -> Session:
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 128:
        raise HTTPException(401, '로그인이 필요합니다.')
    digest = hashlib.sha256(token.encode()).hexdigest()
    with database(request.app.state.settings) as db:
        row = db.execute('SELECT owner.username, sessions.csrf FROM sessions CROSS JOIN owner '
                         'WHERE token_hash=? AND expires_at>?', (digest, time.time())).fetchone()
    if not row:
        raise HTTPException(401, '로그인이 만료되었습니다. 다시 로그인하세요.')
    return Session(row['username'], row['csrf'], digest)


def same_origin(request: Request):
    origin = request.headers.get('origin')
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme != request.url.scheme or parsed.netloc != request.url.netloc:
            raise HTTPException(403, '허용되지 않은 요청 출처입니다.')


def mutation(request: Request, session: Session = Depends(authenticated)) -> Session:
    same_origin(request)
    if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf):
        raise HTTPException(403, '요청 확인에 실패했습니다. 화면을 새로고침하세요.')
    return session


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


@router.get('/status')
def status(request: Request):
    with database(request.app.state.settings) as db:
        return {'configured': db.execute('SELECT 1 FROM owner').fetchone() is not None}


@router.post('/login')
def login(credentials: Credentials, request: Request, response: Response):
    same_origin(request)
    settings = request.app.state.settings
    address = request.client.host if request.client else 'local'
    now = time.time()
    with database(settings) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM attempts WHERE started<?', (now - 900,))
        attempt = db.execute('SELECT count FROM attempts WHERE address=?', (address,)).fetchone()
        if attempt and attempt['count'] >= 10:
            raise HTTPException(429, '로그인 시도가 너무 많습니다. 15분 후 다시 시도하세요.', headers={'Retry-After': '900'})
        db.execute('INSERT INTO attempts VALUES (?, ?, 1) ON CONFLICT(address) DO UPDATE SET count=count+1', (address, now))
        owner = db.execute('SELECT * FROM owner').fetchone()
    verified = False
    if owner:
        try:
            verified = hasher.verify(owner['password_hash'], credentials.password)
        except VerificationError:
            pass
    if not owner or not verified or credentials.username != owner['username']:
        raise HTTPException(401, '사용자 이름 또는 비밀번호가 올바르지 않습니다.')
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with database(settings) as db:
        db.execute('DELETE FROM attempts WHERE address=?', (address,))
        db.execute('DELETE FROM sessions WHERE expires_at<=?', (now,))
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)',
                   (hashlib.sha256(token.encode()).hexdigest(), csrf, now + settings.session_seconds))
    response.set_cookie(COOKIE, token, max_age=settings.session_seconds, httponly=True,
                        secure=settings.secure_cookie, samesite='strict', path='/')
    return {'username': owner['username'], 'csrf': csrf}


@router.get('/session')
def session_info(session: Session = Depends(authenticated)):
    return {'username': session.username, 'csrf': session.csrf}


@router.post('/logout')
def logout(request: Request, response: Response, session: Session = Depends(mutation)):
    with database(request.app.state.settings) as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (session.token_hash,))
    response.delete_cookie(COOKIE, path='/')
    return {'ok': True}
