"""Independent localhost observation/guard process and real HTTP receipt collector."""
import argparse
import json
import os
import threading
import time
import hashlib
import uuid
from urllib.parse import urlsplit,unquote
from proxy_stream import forward, TransportJournal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from guard import Guard
from experiment_budget import environment_limits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--protect', choices=['off', 'on'], required=True)
    parser.add_argument('--engine', choices=['m1', 'd2core', 'd2v2'], default='m1')
    args = parser.parse_args()
    folder = Path(args.run_dir)
    token = os.environ['D2_CONTROL_TOKEN']
    fixture_path=folder/'fixture.json'
    fixture=json.loads(fixture_path.read_text(encoding='utf-8')) if fixture_path.exists() else {}
    approval_credential = os.environ.get('D2_APPROVAL_CREDENTIAL')
    if args.engine == 'd2v2' and (not approval_credential or approval_credential == token):
        raise ValueError('An independent host approval credential is required')
    lock = threading.RLock()
    sequence = 0
    limits = environment_limits()
    model_limit, tool_limit = limits["model_requests"], limits["tool_calls"]
    model_counts = {}
    model_epochs = {}

    def append(filename, item):
        nonlocal sequence
        with lock:
            sequence += 1
            item = {**item, 'seq': sequence, 'timestamp_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns()}
            with (folder / filename).open('a', encoding='utf-8') as f:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
            return item

    journal=TransportJournal(append)
    bridge = None
    if args.engine == 'd2v2':
        from d2v2.core import CoreV2
        from d2v2.mcp_bridge import MCPBridge
        provider = json.loads(os.environ['D2_CORE_PROVIDER'])
        guard = CoreV2(args.protect == 'on', folder, provider, append, memory_root=os.environ.get('D2_MEMORY_ROOT'))
        bridge = MCPBridge(guard.observe,fixture=fixture)
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
            if urlsplit(self.path).path == '/collect':
                query=unquote(urlsplit(self.path).query)
                receipt=append('receipts.jsonl',{'type':'collector_receipt','method':'GET','call_id':self.headers.get('X-D2-Call-Id'),'agent_id':self.headers.get('X-D2-Agent-Id'),'bytes':len(query.encode()),'body':query})
                if args.engine=='d2v2':guard.receipt(self.headers.get('X-D2-Call-Id'))
                return self.respond(200,{'received_bytes':receipt['bytes']})
            if self.path == '/docs/project':
                self.respond(200, fixture.get('web',{'name': 'Aster Tasks', 'storage': 'SQLite', 'export': 'CSV'}))
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
            host_route = self.path in {'/approve', '/approval-token'}
            expected = approval_credential if host_route else token
            if not expected or self.headers.get('Authorization') != 'Bearer ' + expected:
                return self.respond(403, {'error': 'control authentication required'})
            try:
                data = json.loads(raw)
                if is_proxy:
                    agent = self.headers.get('X-D2-Agent-Id','main')
                    with lock:
                        count = model_counts.get(agent,0)
                        epoch = model_epochs.get(agent,0)
                        request_id = str(uuid.uuid4())
                        if model_limit is not None and count >= model_limit:
                            rejection = {'type':'model_budget_rejected','request_id':request_id,'agent_id':agent,
                                'budget_epoch':epoch,'request_index':count+1,'limit':model_limit,'forwarded':False,'status':400}
                            append('audit.jsonl',rejection)
                            append('gateway.jsonl',rejection)
                            return self.respond(400,{'error':{'type':'model_request_budget_exhausted',
                                'code':'POL-MODEL-BUDGET','message':'Experiment model request budget exhausted'}})
                        model_counts[agent] = count+1
                        append('audit.jsonl',{'type':'model_request','origin':'gateway','request_id':request_id,
                            'agent_id':agent,'budget_epoch':epoch,'request_index':count+1,'limit':model_limit})
                    data,dlp=guard.gateway_payload(data)
                    body=json.dumps(data,ensure_ascii=False).encode() if dlp['changed'] else raw
                    journal.start({'type':'proxy_request','request_id':request_id,'agent_id':self.headers.get('X-D2-Agent-Id','main'),'path':proxy_path,'budget_epoch':epoch,'request_index':count+1,'limit':model_limit,'input_bytes':len(raw),
                        'input_sha256':hashlib.sha256(raw).hexdigest(),'output_sha256':hashlib.sha256(body).hexdigest(),**dlp})
                    forward(self,provider,proxy_path,body,journal.append,request_id,journal)
                    return
                if self.path == '/budget-cancel':
                    event={**data,'type':'budget_cancel','reason':'cancelled_by_budget'}
                    guard.observe(event);append('audit.jsonl',event)
                    ids=journal.cancel(data.get('cancel_agent_id',data.get('agent_id','main')))
                    return self.respond(200,{'cancelled_requests':ids})
                if self.path == '/finalize':
                    return self.respond(200, guard.drain() if args.engine in ('d2core','d2v2') else {'pending_reviews': 0})
                if self.path == '/approve' and args.engine=='d2v2':
                    return self.respond(200,guard.approve(data['token'],data['call_id'],data['tool'],data['args'],data.get('agent_id','main')))
                if self.path == '/approval-token' and args.engine=='d2v2':
                    with guard.lock:
                        return self.respond(200,{'token':guard.approvals.host_token(data['call_id'])})
                if self.path == '/memory/call' and args.engine=='d2v2':
                    guard.observe({**data,'type':'memory_dispatch','text':''})
                    try:
                        result=guard.dispatch_memory(data['tool'],data['args'],data['call_id'],data.get('agent_id','main'))
                    except FileNotFoundError:
                        result={'text':'Memory entry not found: '+str(data['args'].get('key','')), 'is_error':True, 'error_code':'MEMORY_NOT_FOUND'}
                    except OSError:
                        result={'text':'Memory storage is unavailable', 'is_error':True, 'error_code':'MEMORY_IO_ERROR'}
                    return self.respond(200,result)
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
                if self.path == '/mcp/tools' and bridge:
                    guard.observe({**data,'type':'mcp_description','server_id':'local-docs',
                                   'tool_name':'project_facts','text':json.dumps(bridge.tools,ensure_ascii=False)})
                    return self.respond(200,{'tools':bridge.tools})
                if self.path in ('/audit','/ingest'):
                    if args.engine=='d2v2' and data.get('type')=='system_init':
                        with lock:
                            agent=data.get('agent_id','main')
                            model_counts[agent]=0
                            model_epochs[agent]=model_epochs.get(agent,0)+1
                    guard.observe(data)
                    append('audit.jsonl', data)
                    return self.respond(200, {'ok': True})
                if self.path in ('/decision','/decide','/tool-budget'):
                    data.pop('host_tool_budget_exceeded',None)
                    data.pop('host_tool_budget_limit',None)
                    if self.path=='/tool-budget':
                        if tool_limit is None or type(data.get('tool_index')) is not int or data['tool_index']<=tool_limit:
                            raise ValueError('Tool budget not exceeded')
                        data['host_tool_budget_exceeded']=True
                        data['host_tool_budget_limit']=tool_limit
                    start = time.perf_counter_ns()
                    result = (guard.decide(data['tool'], data['args'], data) if args.engine in ('d2core','d2v2')
                              else guard.decide(data['tool'], data['args']))
                    if self.path=='/tool-budget' and args.engine!='d2v2':
                        result.update(verdict='BLOCK',would_verdict='BLOCK',policy='POL-TOOL-BUDGET',rule_id='POL-TOOL-BUDGET',risk='R3',executed=False,execution_allowed=False,reason='Experiment tool budget exhausted',tool_index=data['tool_index'],tool_budget=tool_limit)
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
