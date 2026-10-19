"""Actual loopback HTTP plumbing with an explicitly injected unit-test model."""
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import httpx
import test_v2
from d2v2.core import CoreV2
import services


class ApprovalHTTPTest(unittest.TestCase):
    def test_authenticated_approve_endpoint_consumes_one_permit(self):
        with tempfile.TemporaryDirectory() as directory:
            cores=[];servers=[];errors=[]
            def core_factory(enabled,folder,provider,emit,**kw):
                core=CoreV2(enabled,folder,provider,emit,fast=test_v2.FastStub(),**kw);cores.append(core);return core
            def server_factory(address,handler):
                server=ThreadingHTTPServer(address,handler);servers.append(server);return server
            def run():
                try:services.main()
                except BaseException as exc:errors.append(type(exc).__name__)
            with patch('d2v2.core.CoreV2',core_factory),patch('services.ThreadingHTTPServer',server_factory),patch.dict(os.environ,{'D2_CONTROL_TOKEN':'unit-control','D2_APPROVAL_CREDENTIAL':'unit-host','D2_CORE_PROVIDER':'{"api_key":""}','D2_MEMORY_ROOT':str(Path(directory)/'.local/memory')}),patch('sys.argv',['services.py','--run-dir',directory,'--protect','on','--engine','d2v2']):
                thread=threading.Thread(target=run,daemon=True);thread.start()
                try:
                    deadline=time.monotonic()+10
                    while not (Path(directory)/'service.json').exists() and not errors and time.monotonic()<deadline:time.sleep(.01)
                    self.assertFalse(errors)
                    origin=json.loads((Path(directory)/'service.json').read_text())['origin']
                    with httpx.Client(base_url=origin,headers={'Authorization':'Bearer unit-control'},trust_env=False) as client:
                        def post(route,body):
                            response=client.post(route,json=body);self.assertEqual(response.status_code,200,response.text);return response.json()
                        post('/audit',{'event_id':'user','type':'agent_start','task':'Read README.md.'})
                        post('/audit',{'event_id':'external','type':'tool_result','tool':'fs_read','args':{'path':'README.md'},'text':'Public facts.'})
                        args={'path':'extra.md','content':'public'}
                        post('/audit',{'event_id':'proposal','type':'assistant_turn','proposals':[{'call_id':'c','tool':'fs_write','args':args}]})
                        decision=post('/decision',{'call_id':'c','tool':'fs_write','args':args})
                        self.assertEqual(decision['verdict'],'ASK')
                        self.assertNotIn('approval_token',decision)
                        self.assertEqual(client.post('/approval-token',json={'call_id':'c'}).status_code,403)
                        host={'Authorization':'Bearer unit-host'}
                        secret=client.post('/approval-token',json={'call_id':'c'},headers=host).json()['token']
                        request={'token':secret,'call_id':'c','tool':'fs_write','args':args}
                        self.assertEqual(client.post('/approve',json=request).status_code,403)
                        self.assertEqual(client.post('/approve',json=request,headers={'Authorization':'Bearer wrong'}).status_code,403)
                        approved=client.post('/approve',json=request,headers=host);self.assertEqual(approved.json()['approval_status'],'approved_once')
                        self.assertEqual(client.post('/approve',json=request,headers=host).status_code,400)
                        post('/audit',{'event_id':'start','type':'tool_started','call_id':'c'})
                        budget_args={'path':'budget.md','content':'budget refusal'}
                        post('/audit',{'event_id':'budget-proposal','type':'assistant_turn','proposals':[{'call_id':'budget','tool':'fs_write','args':budget_args}]})
                        payload={'call_id':'budget','tool':'fs_write','args':budget_args,'tool_index':41}
                        self.assertEqual(client.post('/tool-budget',json=payload,headers={'Authorization':'Bearer wrong'}).status_code,403)
                        self.assertEqual(client.post('/tool-budget',json={**payload,'tool_index':40}).status_code,400)
                        refused=post('/tool-budget',payload)
                        self.assertEqual((refused['verdict'],refused['rule_id'],refused['risk']),('BLOCK','POL-TOOL-BUDGET','R3'))
                        self.assertIs(refused['executed'],False)
                        audit=[json.loads(x) for x in (Path(directory)/'audit.jsonl').read_text(encoding='utf-8').splitlines()]
                        record=next(x for x in audit if x.get('type')=='guard_decision' and x.get('call_id')=='budget')
                        self.assertEqual(record['args'],budget_args)
                        self.assertFalse(any(x.get('type')=='tool_started' and x.get('call_id')=='budget' for x in audit))
                        # Unit-only upstream substitute: prove concurrent admission, without model responses.
                        forwarded=[]
                        def upstream(handler,provider,path,body,append,request_id,journal):
                            forwarded.append(request_id)
                            append('gateway.jsonl',{'type':'proxy_response','request_id':request_id,'transport_complete':True,'upstream_bytes':0,'downstream_bytes':0})
                            handler.respond(200,{'unit_test_only':True})
                        from concurrent.futures import ThreadPoolExecutor
                        with patch('services.forward',upstream):
                            with ThreadPoolExecutor(max_workers=8) as pool:
                                codes=list(pool.map(lambda _:client.post('/llm-proxy/chat/completions',json={'messages':[]}).status_code,range(24)))
                            self.assertEqual(codes.count(200),20);self.assertEqual(codes.count(400),4)
                            self.assertEqual(len(forwarded),20)
                            self.assertEqual(client.post('/llm-proxy/chat/completions',json={'messages':[]},headers={'X-D2-Agent-Id':'child-test'}).status_code,200)
                            self.assertEqual(client.post('/llm-proxy/chat/completions',json={'messages':[]}).status_code,400)
                            post('/audit',{'event_id':'new-turn','type':'system_init','text':'unit','enabled_tools':[]})
                            self.assertEqual(client.post('/llm-proxy/chat/completions',json={'messages':[]}).status_code,200)
                        audit=[json.loads(x) for x in (Path(directory)/'audit.jsonl').read_text(encoding='utf-8').splitlines()]
                        gateway=[json.loads(x) for x in (Path(directory)/'gateway.jsonl').read_text(encoding='utf-8').splitlines()]
                        self.assertEqual(sorted(x['request_id'] for x in audit if x.get('type')=='model_request'),sorted(forwarded))
                        self.assertEqual(len([x for x in gateway if x.get('type')=='proxy_request']),22)
                        self.assertEqual(len([x for x in gateway if x.get('type')=='model_budget_rejected']),5)
                        self.assertTrue(all(x['forwarded'] is False for x in gateway if x.get('type')=='model_budget_rejected'))


                finally:
                    if servers:servers[0].shutdown()
                    thread.join(10)
                    for core in cores:core.drain(2);core.store.db.close()
                self.assertFalse(thread.is_alive());self.assertFalse(errors)
                for path in Path(directory).rglob('*'):
                    if path.is_file():self.assertNotIn(secret.encode(),path.read_bytes(),str(path))
