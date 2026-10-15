"""Keep the existing Arena application at /safe; proxy only /safe/desk to the new service.

Run from the legacy checkout using its existing Python environment.
No legacy source files or database schemas are modified.
"""
import importlib
import os
import sys
import asyncio
import urllib.request
import urllib.error

sys.path.insert(0, os.environ['D2GUARD_LEGACY_DIR'])
legacy = importlib.import_module('web_demo').app
TARGET = 'http://127.0.0.1:' + os.getenv('D2GUARD_UPSTREAM_PORT', '8766')
HOP = {b'host', b'connection', b'keep-alive', b'transfer-encoding', b'upgrade'}


async def app(scope, receive, send):
    path = scope.get('path', '')
    if scope['type'] != 'http' or not (path == '/safe/desk' or path.startswith('/safe/desk/')):
        return await legacy(scope, receive, send)
    body = bytearray()
    while True:
        msg = await receive()
        if msg['type'] == 'http.disconnect':
            return
        body.extend(msg.get('body', b''))
        if len(body) > 2 * 1024 * 1024:
            await send({'type': 'http.response.start', 'status': 413, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'Request too large'})
            return
        if not msg.get('more_body', False):
            break
    url = TARGET + path
    if scope.get('query_string'):
        url += '?' + scope['query_string'].decode('ascii')
    def proxy():
        request = urllib.request.Request(url, data=bytes(body) if body else None,
            method=scope['method'], headers={k.decode('latin1'): v.decode('latin1') for k, v in scope['headers'] if k.lower() not in HOP})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            response = opener.open(request, timeout=90)
        except urllib.error.HTTPError as error:
            response = error
        except urllib.error.URLError:
            return 503, [(b'content-type', b'text/plain; charset=utf-8')], '新版工作台正在启动，请稍后重试。'.encode()
        with response:
            headers = [(k.lower().encode('latin1'), v.encode('latin1')) for k, v in response.headers.items() if k.lower().encode() not in HOP]
            return response.status, headers, response.read()
    status, headers, result = await asyncio.to_thread(proxy)
    await send({'type': 'http.response.start', 'status': status, 'headers': headers})
    await send({'type': 'http.response.body', 'body': result})
