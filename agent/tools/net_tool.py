"""Real HTTP transport and an independent loopback receiver for physical verification.

The transcript measures application bytes accepted by the HTTP server. It is not
an OS packet capture, and never counts an attempted/failed client call as received.
"""
from __future__ import annotations
import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import requests

def net_fetch(url: str, method: str = 'GET', body: str = '', timeout: int = 5) -> str:
    method = method.upper()
    if method not in {'GET', 'POST'}:
        raise ValueError('Only GET and POST supported')
    with requests.Session() as session:
        if urlsplit(url).hostname in {'127.0.0.1', 'localhost', '::1'}:
            session.trust_env = False
        response = session.request(method, url, data=body.encode('utf-8'), timeout=timeout,
                                   allow_redirects=False)
        response.raise_for_status()
        return response.text[:10000]

class ControlledHTTPReceiver:
    def __init__(self, resources=None, transcript_path=None):
        self.resources, self.transcript_path = resources or {}, transcript_path
        self._records, self._lock = [], threading.Lock()
        receiver = self
        class CapturedReader:
            def __init__(self, stream, capture):
                self.stream, self.capture = stream, capture
            def read(self, *args):
                data=self.stream.read(*args); self.capture.extend(data); return data
            def readline(self, *args):
                data=self.stream.readline(*args); self.capture.extend(data); return data
            def __getattr__(self, name):
                return getattr(self.stream, name)
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.raw_received=bytearray()
                self.rfile=CapturedReader(self.rfile,self.raw_received)
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.receive()
            def do_POST(self):
                self.receive()
            def receive(self):
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    self.send_error(400); return
                if length < 0 or length > 1048576 or self.headers.get('Transfer-Encoding'):
                    self.send_error(413); return
                self.connection.settimeout(5)
                body = self.rfile.read(length)
                if len(body) != length:
                    self.send_error(400); return
                parsed = urlsplit(self.path)
                query = parsed.query.encode('ascii', errors='replace')
                record = dict(timestamp=time.time(), method=self.command, path=parsed.path,
                    request_target=self.path, body_b64=base64.b64encode(body).decode(),
                    received_body_bytes=len(body), received_query_bytes=len(query),
                    received_payload_bytes=len(body)+len(query),
                    received_http_bytes=len(self.raw_received),
                    raw_http_b64=base64.b64encode(self.raw_received).decode())
                with receiver._lock:
                    receiver._records.append(record)
                    if receiver.transcript_path:
                        with open(receiver.transcript_path, 'a', encoding='utf-8') as stream:
                            stream.write(json.dumps(record, ensure_ascii=False)+'\n')
                content = receiver.resources.get(parsed.path, 'received').encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True,
                                       name='d2guard-independent-http-receiver')
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
    def snapshot(self, path='/sink'):
        with self._lock:
            rows = [dict(r) for r in self._records if path is None or r['path'] == path]
        return dict(request_count=len(rows), received_body_bytes=sum(r['received_body_bytes'] for r in rows),
                    received_query_bytes=sum(r['received_query_bytes'] for r in rows),
                    received_payload_bytes=sum(r['received_payload_bytes'] for r in rows),
                    received_http_bytes=sum(r['received_http_bytes'] for r in rows), records=rows,
                    evidence_kind='independent_http_receiver_socket_transcript',
                    capture_layer='actual HTTP bytes read from TCP socket; not link-layer PCAP')
    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()
