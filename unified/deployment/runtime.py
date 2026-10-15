"""Single-port host for desktop bundles and the independently deployed web edition."""
from pathlib import Path
import os
import sys
import threading
import time
from collections import defaultdict, deque

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'D2guard_core'))


def create_host(core=None, static_dir=None, prefix=None, managed=None):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.base import BaseHTTPMiddleware
    if core is None:
        from server import app as core
    prefix = (prefix if prefix is not None else os.getenv('D2GUARD_PREFIX', '')).rstrip('/')
    managed = managed if managed is not None else os.getenv('D2GUARD_MANAGED', '0') == '1'
    assets = Path(static_dir or os.getenv('D2GUARD_STATIC', str(ROOT / 'D2guard_desk' / 'dist')))
    host = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    origins = set(filter(None, os.getenv('D2GUARD_ORIGINS', '').split(',')))
    hits = defaultdict(deque)
    lock = threading.Lock()

    class Boundary(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            api = path.startswith(prefix + '/api/')
            if api:
                origin = request.headers.get('origin')
                own_origin = str(request.base_url).rstrip('/')
                if origin and origin not in origins | {own_origin, 'http://127.0.0.1:5173', 'http://localhost:5173'}:
                    return JSONResponse({'detail': '不允许的页面来源'}, status_code=403)
                if managed and request.method == 'POST' and path in {prefix + '/api/desktop/models/config', prefix + '/api/desktop/models/test'}:
                    return JSONResponse({'detail': '体验站模型由管理员配置；桌面版支持个人模型设置'}, status_code=403)
                if managed and request.method == 'POST':
                    # Bound global model/API demand; proxy identities are not trusted.
                    with lock:
                        now = time.monotonic()
                        queue = hits['requests']
                        while queue and queue[0] < now - 60:
                            queue.popleft()
                        if len(queue) >= 120:
                            return JSONResponse({'detail': '体验站请求较多，请稍后重试'}, status_code=429)
                        queue.append(now)
                # Origins already checked here; retain original core contracts untouched.
                request.scope['headers'] = [(k, v) for k, v in request.scope['headers'] if k.lower() != b'origin']
            response = await call_next(request)
            response.headers['X-Content-Type-Options'] = 'nosniff'
            if api:
                response.headers['Cache-Control'] = 'no-store'
            return response
    host.add_middleware(Boundary)

    @host.get(prefix + '/healthz')
    def health():
        return {'application': 'D2Guard', 'mode': 'web' if managed else 'desktop', 'ready': True}

    @host.get(prefix + '/openapi.json')
    def contract():
        return core.openapi()

    if prefix:
        @host.get(prefix)
        def trailing_slash():
            return RedirectResponse(prefix + '/', status_code=307)
    # Mount core only under the edition prefix, without exposing another copy.
    from starlette.routing import Mount
    host.router.routes.append(Mount(prefix + '/api', app=ApiPrefix(core)))
    host.mount(prefix + '/', StaticFiles(directory=assets, html=True), name='desktop')
    return host


class ApiPrefix:
    """Restore /api removed by Mount; payloads and response contracts are unchanged."""
    def __init__(self, core):
        self.core = core

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        root = scope.get('root_path', '')
        path = scope['path']
        suffix = path[len(root):] if path.startswith(root) else path
        scope['path'] = '/api' + suffix
        scope['raw_path'] = scope['path'].encode()
        scope['root_path'] = ''
        await self.core(scope, receive, send)


def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--parent-pid', type=int)
    args = parser.parse_args()
    if args.parent_pid:
        def watch_parent():
            if sys.platform == 'win32':
                import ctypes
                k = ctypes.windll.kernel32
                k.OpenProcess.restype = ctypes.c_void_p
                handle = k.OpenProcess(0x100000, False, args.parent_pid)
                if not handle:
                    os._exit(0)
                k.WaitForSingleObject(ctypes.c_void_p(handle), 0xFFFFFFFF)
                os._exit(0)
            while True:
                try:
                    os.kill(args.parent_pid, 0)
                except ProcessLookupError:
                    os._exit(0)
                time.sleep(2)
        threading.Thread(target=watch_parent, daemon=True).start()
    uvicorn.run(create_host(), host=args.host, port=args.port, access_log=False)


if __name__ == '__main__':
    main()
