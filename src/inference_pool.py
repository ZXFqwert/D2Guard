"""Host-only resident inference. No session state or classification result cache."""
import argparse
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def identity(laya_path, s1_path):
    paths = [Path(laya_path)] + ([Path(s1_path)] if s1_path else [])
    root = Path(__file__).resolve().parent
    paths += [root/'original_laya.py', *sorted((root/'d2v2').glob('*.py')), root/'inference_pool.py']
    return hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in paths)).hexdigest()


class Client:
    def __init__(self, descriptor, laya_path, s1_path):
        self.config = json.loads(Path(descriptor).read_text(encoding='utf-8'))
        self.identity = identity(laya_path, s1_path)
        self.info = self.call('metadata')

    def call(self, operation, **arguments):
        request = urllib.request.Request(self.config['origin'], method='POST',
            data=json.dumps({'identity': self.identity, 'operation': operation, **arguments}, ensure_ascii=False).encode(),
            headers={'Authorization': 'Bearer '+self.config['token'], 'Content-Type': 'application/json'})
        with DIRECT.open(request, timeout=120) as response:
            value = json.load(response)
        if 'error' in value:
            raise RuntimeError('Resident inference failed: '+value['error'])
        return value['result']


class RemoteFast:
    calibrated_questions = frozenset()

    def __init__(self, client):
        self.client = client
        self.metadata = {**client.info['fast'], 'resident': True}
        self.last_trace = {}

    def count_tokens(self, text):
        return self.client.call('count_tokens', text=text)

    def token_offsets(self, text):
        return self.client.call('token_offsets', text=text)

    def token_span(self, raw, char_span):
        offsets = self.token_offsets(raw)
        indices = [i for i,(a,b) in enumerate(offsets) if a < char_span[1] and b > char_span[0]]
        return [indices[0],indices[-1]+1] if indices else [0,0]

    def answer_questions(self, views):
        result = self.client.call('answer_questions', views=views)
        self.last_trace = result['trace']
        return result['answers']


class RemoteContent:
    def __init__(self, client):
        self.client = client
        self.metadata = client.info['content']
        self.add_risk_enabled = client.info['add_risk_enabled']

    def classify(self, text, source_type):
        return self.client.call('classify', text=text, source_type=source_type)


class ResidentProcess:
    """One model process owned by a console, including on Windows."""
    def __init__(self, root, python):
        from process_tree import ProcessTree
        self.root = Path(root)
        self.descriptor = self.root/'.local'/('inference-'+secrets.token_hex(8)+'.json')
        self.log = self.descriptor.with_suffix('.log').open('w', encoding='utf-8')
        self.tree = ProcessTree()
        s1 = os.environ.get('D2_S1_CONFIG') or str(self.root/'.local/s1.json')
        command = [python, str(self.root/'src/inference_pool.py'), '--laya', str(self.root/'.local/laya.json'),
                   '--descriptor', str(self.descriptor)]
        if os.environ.get('D2_S1_DISABLE') != '1':
            command += ['--s1', s1]
        self.process = self.tree.popen(command, cwd=self.root, stdout=self.log, stderr=self.log)

    def status(self):
        if self.process.poll() is not None:
            return {'phase': 'failed', 'error': '快镜初始化失败，请查看本机 .local/inference-*.log'}
        if self.descriptor.exists():
            data = json.loads(self.descriptor.read_text(encoding='utf-8'))
            return {'phase': 'ready', 'startup_seconds': data['startup_seconds']}
        return {'phase': 'loading'}

    def wait(self):
        deadline = time.monotonic()+240
        while time.monotonic() < deadline:
            status = self.status()
            if status['phase'] == 'ready':
                return str(self.descriptor)
            if status['phase'] == 'failed':
                raise RuntimeError(status['error'])
            time.sleep(.1)
        raise RuntimeError('快镜初始化超时')

    def close(self):
        self.tree.close()
        self.process.wait(timeout=10)
        self.log.close()
        self.descriptor.unlink(missing_ok=True)


def serve(laya_path, s1_path, descriptor):
    from original_laya import OriginalLaya
    from d2v2.request_model import RequestContentModel
    started = time.monotonic()
    fingerprint = identity(laya_path, s1_path)
    fast = OriginalLaya(laya_path, lazy=True)
    content = RequestContentModel(s1_path) if s1_path else None
    # Exercise the real tokenizer and classifier once, before advertising readiness.
    fast.count_tokens('Read README.md.')
    if content:
        content.classify('Project documentation describes SQLite storage.', 'file')
    lock = threading.Lock()
    token = secrets.token_hex(32)
    info = {'fast': fast.metadata, 'content': content.metadata if content else None,
            'add_risk_enabled': bool(content and content.add_risk_enabled),
            'identity': fingerprint, 'startup_seconds': round(time.monotonic()-started, 3)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            status, result = 200, None
            try:
                if self.headers.get('Authorization') != 'Bearer '+token:
                    status = 403
                    raise ValueError('authentication_required')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4_000_000:
                    raise ValueError('invalid_size')
                data = json.loads(self.rfile.read(length))
                if data.get('identity') != fingerprint:
                    raise ValueError('configuration_changed_restart_console')
                with lock:
                    op = data['operation']
                    if op == 'metadata':
                        result = info
                    elif op in ('count_tokens', 'token_offsets'):
                        result = getattr(fast, op)(data['text'])
                    elif op == 'classify' and content:
                        result = content.classify(data['text'], data['source_type'])
                    elif op == 'answer_questions':
                        result = {'answers': fast.answer_questions(data['views']), 'trace': fast.last_trace}
                    else:
                        raise ValueError('unknown_operation')
                payload = {'result': result}
            except Exception as exc:
                payload = {'error': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}
                status = status if status != 200 else 503
            encoded = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    path = Path(descriptor)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'origin': f'http://127.0.0.1:{server.server_port}',
                               'token': token, 'pid': os.getpid(), **info}), encoding='utf-8')
    temp.replace(path)
    print(json.dumps({'ready': True, 'startup_seconds': info['startup_seconds']}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        path.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--laya', required=True)
    parser.add_argument('--s1')
    parser.add_argument('--descriptor', required=True)
    args = parser.parse_args()
    serve(args.laya, args.s1, args.descriptor)
