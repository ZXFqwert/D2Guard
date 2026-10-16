"""Independent localhost observation/guard process and real HTTP receipt collector."""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from guard import Guard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--protect', choices=['off', 'on'], required=True)
    args = parser.parse_args()
    folder = Path(args.run_dir)
    guard = Guard(args.protect == 'on')
    token = os.environ['D2_CONTROL_TOKEN']
    lock = threading.RLock()
    sequence = 0

    def append(filename, item):
        nonlocal sequence
        with lock:
            sequence += 1
            item = {**item, 'seq': sequence, 'timestamp_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns()}
            with (folder / filename).open('a', encoding='utf-8') as f:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
            return item

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, obj):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == '/docs/project':
                self.respond(200, {'name': 'Aster Tasks', 'storage': 'SQLite', 'export': 'CSV'})
            else:
                self.respond(404, {'error': 'unknown endpoint'})

        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 262144:
                return self.respond(413, {'error': 'oversized request'})
            raw = self.rfile.read(length)
            if self.path == '/collect':
                receipt = append('receipts.jsonl', {'type': 'collector_receipt',
                    'call_id': self.headers.get('X-D2-Call-Id'), 'agent_id': self.headers.get('X-D2-Agent-Id'),
                    'bytes': len(raw), 'body': raw.decode('utf-8', errors='replace')})
                return self.respond(200, {'received_bytes': len(raw), 'receipt_seq': receipt['seq']})
            if self.headers.get('Authorization') != 'Bearer ' + token:
                return self.respond(403, {'error': 'control authentication required'})
            try:
                data = json.loads(raw)
                if self.path == '/audit':
                    guard.observe(data)
                    append('audit.jsonl', data)
                    return self.respond(200, {'ok': True})
                if self.path == '/decision':
                    start = time.perf_counter_ns()
                    result = guard.decide(data['tool'], data['args'])
                    result['latency_ms'] = (time.perf_counter_ns() - start) / 1e6
                    append('audit.jsonl', {**data, 'type': 'guard_decision', **result})
                    return self.respond(200, result)
                self.respond(404, {'error': 'unknown endpoint'})
            except (ValueError, KeyError, TypeError):
                self.respond(400, {'error': 'invalid control request'})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    (folder / 'service.json').write_text(json.dumps({'origin': f'http://127.0.0.1:{server.server_port}',
        'pid': os.getpid()}), encoding='utf-8')
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
