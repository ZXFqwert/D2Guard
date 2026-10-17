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
            with patch('d2v2.core.CoreV2',core_factory),patch('services.ThreadingHTTPServer',server_factory),patch.dict(os.environ,{'D2_CONTROL_TOKEN':'unit-control','D2_CORE_PROVIDER':'{"api_key":""}','D2_MEMORY_ROOT':str(Path(directory)/'.local/memory')}),patch('sys.argv',['services.py','--run-dir',directory,'--protect','on','--engine','d2v2']):
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
                        request={'token':decision['approval_token'],'call_id':'c','tool':'fs_write','args':args}
                        self.assertEqual(client.post('/approve',json=request,headers={'Authorization':'Bearer wrong'}).status_code,403)
                        approved=post('/approve',request);self.assertEqual(approved['approval_status'],'approved_once')
                        self.assertEqual(client.post('/approve',json=request).status_code,400)
                        post('/audit',{'event_id':'start','type':'tool_started','call_id':'c'})
                finally:
                    if servers:servers[0].shutdown()
                    thread.join(10)
                    for core in cores:core.drain(2);core.store.db.close()
                self.assertFalse(thread.is_alive());self.assertFalse(errors)
