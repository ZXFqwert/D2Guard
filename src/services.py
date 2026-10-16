"""Independent localhost observation/guard process and real HTTP receipt collector."""
import argparse
import json
import os
import threading
import time
import hashlib
import uuid
from proxy_stream import forward
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from guard import Guard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--protect', choices=['off', 'on'], required=True)
    parser.add_argument('--engine', choices=['m1', 'd2core', 'd2v2'], default='m1')
    args = parser.parse_args()
    folder = Path(args.run_dir)
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

    bridge = None
    if args.engine == 'd2v2':
        from d2v2.core import CoreV2
        from d2v2.mcp_bridge import MCPBridge
        provider = json.loads(os.environ['D2_CORE_PROVIDER'])
        guard = CoreV2(args.protect == 'on', folder, provider, append)
        bridge = MCPBridge(guard.observe)
    elif args.engine == 'd2core':
        from core_guard import CoreGuard
        provider = json.loads(os.environ['D2_CORE_PROVIDER'])
        guard = CoreGuard(args.protect == 'on', folder, provider, append)
    else:
        guard = Guard(args.protect == 'on')

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
            proxy_path = self.path.removeprefix('/llm-proxy')
            is_proxy = args.engine == 'd2v2' and self.path.startswith('/llm-proxy/') and proxy_path in ('/responses','/chat/completions')
            if length < 0 or length > (8388608 if is_proxy else 262144):
                return self.respond(413, {'error': 'oversized request'})
            raw = self.rfile.read(length)
            if self.path == '/collect':
                receipt = append('receipts.jsonl', {'type': 'collector_receipt',
                    'call_id': self.headers.get('X-D2-Call-Id'), 'agent_id': self.headers.get('X-D2-Agent-Id'),
                    'bytes': len(raw), 'body': raw.decode('utf-8', errors='replace')})
                if args.engine == 'd2v2':guard.receipt(self.headers.get('X-D2-Call-Id'))
                return self.respond(200, {'received_bytes': len(raw), 'receipt_seq': receipt['seq']})
            if self.headers.get('Authorization') != 'Bearer ' + token:
                return self.respond(403, {'error': 'control authentication required'})
            try:
                data = json.loads(raw)
                if is_proxy:
                    data,dlp=guard.gateway_payload(data)
                    body=json.dumps(data,ensure_ascii=False).encode() if dlp['changed'] else raw
                    request_id=str(uuid.uuid4())
                    append('gateway.jsonl',{'type':'proxy_request','request_id':request_id,'path':proxy_path,'input_bytes':len(raw),
                        'input_sha256':hashlib.sha256(raw).hexdigest(),'output_sha256':hashlib.sha256(body).hexdigest(),**dlp})
                    forward(self,provider,proxy_path,body,append,request_id)
                    return
                if self.path == '/finalize':
                    return self.respond(200, guard.drain() if args.engine in ('d2core','d2v2') else {'pending_reviews': 0})
                if self.path == '/approve':return self.respond(501,{'error':'Approval resume is not implemented; ASK remains held.'})
                if self.path == '/trace' and args.engine=='d2v2':
                    with guard.lock:trace=guard.store.trace()
                    return self.respond(200,trace)
                if self.path == '/backtrack' and args.engine=='d2v2':
                    with guard.lock:
                        item=guard.store.backtrack(data['reference']);item['excerpt']=guard.ledger.redact(item['excerpt'])
                    return self.respond(200,item)
                if self.path == '/mcp/call' and bridge:
                    guard.observe({**data,'type':'mcp_dispatch','text':''})
                    # Invocation requires a matching ALLOW bound to the exact arguments.
                    from d2v2.store import digest,encode
                    with guard.lock:
                        row=guard.store.db.execute('SELECT args_hash,decision FROM calls WHERE id=?',(data['call_id'],)).fetchone()
                    expected=digest(encode({'tool':'mcp_call','args':{'name':data['name']}}))
                    if not row or row['args_hash']!=expected or json.loads(row['decision'])['verdict']!='ALLOW':
                        return self.respond(403,{'error':'Missing bound MCP authorization'})
                    return self.respond(200,bridge.call(data['name'],{}))
                if self.path in ('/audit','/ingest'):
                    guard.observe(data)
                    append('audit.jsonl', data)
                    return self.respond(200, {'ok': True})
                if self.path in ('/decision','/decide'):
                    start = time.perf_counter_ns()
                    result = (guard.decide(data['tool'], data['args'], data) if args.engine in ('d2core','d2v2')
                              else guard.decide(data['tool'], data['args']))
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
        if bridge:bridge.close()
        server.server_close()


if __name__ == '__main__':
    main()
