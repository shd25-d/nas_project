from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, files, previews
from .config import Settings
from .storage import Storage


def create_app(settings=None):
    settings = settings or Settings()
    if settings.app_dir == settings.files_dir or settings.files_dir in settings.app_dir.parents:
        raise ValueError('NAS_APP_DIR must be outside NAS_FILES_DIR')
    auth.initialize(settings)
    app = FastAPI(title='Moru NAS', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.storage = Storage(settings.files_dir)
    app.include_router(auth.router)
    app.include_router(files.router)
    app.include_router(previews.router)

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; worker-src 'self' blob:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(OSError)
    async def storage_error(request, error):
        return JSONResponse(status_code=500, content={'detail': '저장소 작업에 실패했습니다. 공간과 폴더 권한을 확인하세요.'})

    @app.get('/api/health')
    def health():
        return {'ok': True}

    # Keep unknown API routes as JSON 404s, never the SPA entry point.
    @app.api_route('/api/{rest:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'])
    def unknown_api(rest: str):
        return JSONResponse(status_code=404, content={'detail': '요청한 API를 찾을 수 없습니다.'})

    if settings.static_dir.is_dir():
        app.mount('/', StaticFiles(directory=settings.static_dir, html=True), name='web')

    return app
