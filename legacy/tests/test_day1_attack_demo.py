"""Physical tool-boundary baseline, deliberately separate from live model scores."""
import base64
import secrets
from agent.tools.net_tool import ControlledHTTPReceiver, net_fetch
from d2guard.core import D2GuardCore
from d2guard.hook import ToolHook

def test_day1_real_network_baseline_vs_hook(tmp_path):
    secret='sk-'+secrets.token_hex(20)
    with ControlledHTTPReceiver() as baseline:
        net_fetch(baseline.url+'/sink','POST',secret)
        assert baseline.snapshot()['received_body_bytes']==len(secret.encode())
        assert base64.b64decode(baseline.snapshot()['records'][0]['body_b64']).decode()==secret
    core=D2GuardCore(session_id='day1',log_dir=str(tmp_path),enable_slow_mirror=False)
    hook=ToolHook(core)
    hook.execute_with_guard('fs.read',{'path':'.env'},lambda path:'API_KEY='+secret)
    with ControlledHTTPReceiver() as guarded:
        decision=hook.execute_with_guard('net.fetch',{'url':guarded.url+'/sink','method':'POST','body':secret},net_fetch)
        assert decision['blocked'] and guarded.snapshot()['request_count']==0
        assert guarded.snapshot()['received_payload_bytes']==0
