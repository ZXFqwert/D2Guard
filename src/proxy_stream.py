"""Stream fixed-upstream responses with payload-free transport diagnostics."""
import hashlib
import time
import uuid
import threading

import httpx


class TransportJournal:
    """Exactly one transport terminal, including host-confirmed budget cancellation."""
    def __init__(self,append):
        self.emit=append;self.lock=threading.RLock();self.active={};self.finished=set()

    def start(self,item):
        with self.lock:
            self.active[item['request_id']]={'agent_id':item['agent_id'],'started':time.perf_counter(),
                'upstream_bytes':0,'downstream_bytes':0,'chunks':0}
            return self.emit('gateway.jsonl',item)

    def progress(self,rid,received,sent,chunks):
        with self.lock:
            if rid in self.active:self.active[rid].update(upstream_bytes=received,downstream_bytes=sent,chunks=chunks)

    def append(self,filename,item):
        with self.lock:
            rid=item['request_id']
            if rid in self.finished:return None
            current=self.active.pop(rid,{})
            self.finished.add(rid)
            return self.emit(filename,{**item,'agent_id':current.get('agent_id','unknown')})

    def cancel(self,agent,reason='cancelled_by_budget'):
        with self.lock:
            ids=[rid for rid,value in self.active.items() if agent=='*' or value['agent_id']==agent]
            for rid in ids:
                current=self.active[rid]
                self.append('gateway.jsonl',{'type':'proxy_cancelled','request_id':rid,'reason':reason,
                    'transport_complete':False,'elapsed_ms':(time.perf_counter()-current['started'])*1000,
                    **{k:current[k] for k in ('upstream_bytes','downstream_bytes','chunks')}})
            return ids


def forward(handler, provider, path, body, append, request_id=None, journal=None):
    request_id = request_id or str(uuid.uuid4())
    start = time.perf_counter()
    stage = 'connect_upstream'
    headers_sent = False
    status = None
    received = sent = chunks = 0
    response_hash = hashlib.sha256()
    try:
        with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
            with client.stream('POST', provider['base_url'].rstrip('/')+path,
                               headers={'Authorization':'Bearer '+provider['api_key'],
                                        'Content-Type':'application/json'}, content=body) as upstream:
                status = upstream.status_code
                stage = 'send_headers'
                handler.send_response(status)
                handler.send_header('Content-Type', upstream.headers.get('content-type','application/json'))
                handler.send_header('Connection','close')
                # Once writing headers starts, a second HTTP response is unsafe.
                headers_sent = True
                handler.end_headers()
                iterator = upstream.iter_bytes()
                while True:
                    stage = 'read_upstream'
                    try:
                        chunk = next(iterator)
                    except StopIteration:
                        break
                    received += len(chunk)
                    if journal:journal.progress(request_id,received,sent,chunks)
                    response_hash.update(chunk)
                    stage = 'write_downstream'
                    handler.wfile.write(chunk)
                    handler.wfile.flush()
                    sent += len(chunk)
                    chunks += 1
                    if journal:journal.progress(request_id,received,sent,chunks)
                append('gateway.jsonl', {'type':'proxy_response','request_id':request_id,
                    'status':status, 'upstream_bytes':received, 'downstream_bytes':sent,
                    'chunks':chunks, 'response_sha256':response_hash.hexdigest(),
                    'elapsed_ms':(time.perf_counter()-start)*1000, 'transport_complete':True})
    except (httpx.HTTPError, OSError) as exc:
        # Do not persist exception text: it may contain request URLs or content.
        append('gateway.jsonl', {'type':'proxy_error','request_id':request_id,
            'error_type':type(exc).__name__, 'errno':getattr(exc,'errno',None),
            'winerror':getattr(exc,'winerror',None), 'stage':stage, 'status':status,
            'headers_sent':headers_sent, 'upstream_bytes':received,
            'downstream_bytes':sent, 'chunks':chunks,
            'response_sha256':response_hash.hexdigest(),
            'elapsed_ms':(time.perf_counter()-start)*1000, 'transport_complete':False})
        if not headers_sent:
            try:
                handler.respond(502, {'error':'upstream transport failed','request_id':request_id})
            except OSError:
                pass
    finally:
        handler.close_connection = True
