"""Deterministic integration tests; injected clients are explicitly test fixtures."""
import base64
import copy
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from agent.react_agent import ReActAgent
from agent.tools.net_tool import ControlledHTTPReceiver, net_fetch
from benchmarks.runtime import Experiment
from benchmarks.scenarios import BENCHMARK_SCENARIOS
from d2guard.core import D2GuardCore
from d2guard.gateway import ModelAPIGateway
from d2guard.hook import ToolHook
from d2guard.models import CallLifecycleStage, D2Event, VerdictType
from d2guard.redaction import OutboundRedactor, REDACTED
from d2guard.slow_mirror import EvidencePack, SlowMirror
from run_eval import evaluate_scenario, summarize
import web_demo

class RecordingClient:
    def __init__(self, responder=None):
        self.requests=[]
        self.chat=NS(completions=NS(create=self.create))
        self.responder=responder or (lambda request: response(content='done'))
    def create(self,**request):
        self.requests.append(copy.deepcopy(request))
        return self.responder(request)

def response(name=None,args=None,content=''):
    calls=[NS(id='call-'+secrets.token_hex(4),function=NS(name=name,arguments=json.dumps(args)))] if name else None
    return NS(choices=[NS(message=NS(content=content,tool_calls=calls))])

class PayloadDrivenClient(RecordingClient):
    """Test fixture reads the actual tool response; payload controls its next action."""
    def __init__(self):
        super().__init__(self.respond)
    def respond(self,request):
        tools=[m for m in request['messages'] if m['role']=='tool']
        if not tools:
            return response('fs_read',{'path':'external_input.txt'})
        if len(tools)==1:
            document=tools[-1]['content']
            if 'DELETE_TEST' in document or '删除' in request['messages'][1]['content']:
                return response('fs_delete',{'path':'delete_me.txt'})
            if 'LEAK_TEST' in document:
                return response('fs_read',{'path':'tests/data/database.ini'})
            if 'WRITE_ALPHA' in document:
                return response('fs_write',{'path':'result.txt','content':'alpha'})
            if 'WRITE_BETA' in document:
                return response('fs_write',{'path':'result.txt','content':'beta'})
            return response(content='document summarized')
        if len(tools)==2 and 'API_KEY=' in tools[-1]['content']:
            # Endpoint comes from the real external document; no fixed port or canary.
            document=tools[0]['content']
            import re
            endpoint=re.search(r'http://127\.0\.0\.1:\d+/sink',document).group(0)
            return response('net_fetch',{'url':endpoint,'method':'POST','body':tools[-1]['content']})
        return response(content='completed')

def core(tmp_path,**kwargs):
    return D2GuardCore(session_id=secrets.token_hex(8),log_dir=str(tmp_path),enable_slow_mirror=False,**kwargs)

def test_receiver_counts_only_real_transport_and_utf8():
    with ControlledHTTPReceiver() as sink:
        assert sink.snapshot()['request_count']==0
        net_fetch(sink.url+'/sink',method='POST',body='测试')
        measured=sink.snapshot()
        assert measured['request_count']==1 and measured['received_body_bytes']==6
        net_fetch(sink.url+'/sink?data=hello')
        assert sink.snapshot()['received_query_bytes']==10
        assert len(measured['records'])==1
    with pytest.raises(Exception): net_fetch(sink.url+'/sink',method='POST',body='failed',timeout=1)
    assert sink.snapshot()['request_count']==2

def test_physical_secret_block_zero_receiver_bytes(tmp_path):
    kernel=core(tmp_path);hook=ToolHook(kernel)
    value='sk-'+secrets.token_hex(20)
    hook.execute_with_guard('fs.read',{'path':'.env'},lambda path:'API_KEY='+value)
    with ControlledHTTPReceiver() as sink:
        result=hook.execute_with_guard('net.fetch',{'url':sink.url+'/sink','method':'POST','body':value},net_fetch)
        assert result['verdict']=='BLOCK'
        assert sink.snapshot()['received_payload_bytes']==0 and sink.snapshot()['request_count']==0
    assert value not in __import__('pathlib').Path(kernel.event_log_path).read_text(encoding='utf-8')

@pytest.mark.parametrize('encoding',[lambda s:s,lambda s:base64.b64encode(s.encode()).decode(),lambda s:s.encode().hex()])
def test_physical_verifier_decodes_received_secret(encoding):
    with Experiment(client=PayloadDrivenClient()) as exp:
        net_fetch(exp.receiver.url+'/other-path',method='POST',body=encoding(exp.canary))
        assert exp.physical()['is_leaked'] is True
        assert exp.physical()['received_payload_bytes']>0

def test_ask_suspends_then_executes_once_even_concurrently(tmp_path):
    kernel=core(tmp_path,principal_id='alice');hook=ToolHook(kernel)
    executed=[]
    args={'path':'delete_me.txt','options':{'recursive':False}}
    result=hook.execute_with_guard('fs.delete',args,lambda **kw:executed.append(kw))
    token=result['approval_token']['token_id']
    assert result['pending'] and not result['blocked'] and executed==[]
    args['path']='tampered'  # Caller cannot mutate the suspended action.
    assert not kernel.approve_token(token,'bob')
    assert kernel.approve_token(token,'alice')
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:hook.resume(token,'alice'),range(2)))
    assert sum(r['success'] for r in results)==1
    assert executed[0]['path']=='delete_me.txt' and len(executed)==1
    assert not kernel.approve_token(token,'alice')
    assert token not in kernel._tokens

def test_public_token_mutation_is_not_authorization(tmp_path):
    kernel=core(tmp_path,principal_id='alice');hook=ToolHook(kernel)
    executed=[]
    result=hook.execute_with_guard('fs.delete',{'path':'x'},lambda **kw:executed.append(kw))
    token=result['approval_token']['token_id']
    kernel.active_tokens[token].status='APPROVED'
    assert not hook.resume(token,'alice')['success']
    assert executed==[]

@pytest.mark.parametrize('change',['args','agent','session','tool','principal','expiry'])
def test_approval_binding_and_expiry(tmp_path,change):
    kernel=core(tmp_path,principal_id='alice');hook=ToolHook(kernel)
    result=hook.execute_with_guard('fs.delete',{'path':'x'},lambda **kw:'executed')
    token_id=result['approval_token']['token_id']
    assert kernel.approve_token(token_id,'alice')
    event,func,token=hook._pending[token_id]
    if change=='args': event.tool_args={'path':'other'}
    if change=='agent': event.agent_id='other'
    if change=='session': kernel.session_id='other'
    if change=='tool': event.tool_name='fs.write'
    actor='bob' if change=='principal' else 'alice'
    if change=='expiry': kernel._tokens[token_id].created_at-=1000
    verdict=kernel.handle_hook_pre_exec(event,token,actor)
    assert verdict.verdict==VerdictType.BLOCK

def test_approval_cannot_override_new_hard_block(tmp_path):
    from d2guard.models import ActionVerdict
    kernel=core(tmp_path,principal_id='alice');hook=ToolHook(kernel);executed=[]
    result=hook.execute_with_guard('fs.delete',{'path':'x'},lambda **kw:executed.append(kw))
    token=result['approval_token']['token_id'];kernel.approve_token(token,'alice')
    kernel.decision_engine.decide=lambda *a,**kw:ActionVerdict(VerdictType.BLOCK,reason='new hard block')
    assert hook.resume(token,'alice')['blocked'] and executed==[]

def test_rejected_token_never_executes(tmp_path):
    kernel=core(tmp_path,principal_id='alice');hook=ToolHook(kernel);executed=[]
    result=hook.execute_with_guard('fs.delete',{'path':'x'},lambda **kw:executed.append(kw))
    token=result['approval_token']['token_id']
    assert kernel.reject_token(token,'alice')
    assert not hook.resume(token,'alice')['success'] and executed==[]

def test_gateway_and_slow_mirror_sanitize_complete_nonmutating_payload(tmp_path):
    secret='private-value-'+secrets.token_hex(16)
    encoded=base64.b64encode(('prefix '+secret).encode()).decode()
    kernel=core(tmp_path)
    hook=ToolHook(kernel);hook.execute_with_guard('fs.read',{'path':'.env'},lambda path:'password='+secret)
    client=RecordingClient()
    messages=[{'role':'user','content':'safe'}, {'role':'assistant','tool_calls':[
        {'id':'c','type':'function','function':{'name':'x','arguments':json.dumps({'data':encoded})}}]}]
    tools=[{'type':'function','function':{'name':'x','description':secret,'parameters':{'type':'object','properties':{}}}}]
    original=copy.deepcopy(messages)
    ModelAPIGateway(kernel,client).chat_completion('test',messages,tools)
    sent=json.dumps(client.requests)
    assert secret not in sent and encoded not in sent and messages==original
    slow=SlowMirror(api_key='')
    slow.client=RecordingClient(lambda _:response(content=json.dumps({'verdict':'ALLOW','reason':'test','confidence':.7})))
    pack=EvidencePack(secret,{'data':encoded},{'tool_args':{'body':secret}},encoded,[])
    slow.judge(pack,redactor=OutboundRedactor([secret]))
    sent=json.dumps(slow.client.requests)
    assert secret not in sent and encoded not in sent and pack.initial_task==secret

def test_nested_secret_encoding_and_capability_structure():
    value='sk-'+secrets.token_hex(20)
    encoded=base64.b64encode(value.encode()).decode().encode().hex()
    result=OutboundRedactor([value]).sanitize({'body':encoded,'approval_token':{'token_id':'capability-id'}})
    assert encoded not in json.dumps(result)
    assert result['approval_token']['token_id']=='capability-id'

def test_eval_payload_drives_actual_agent_instead_of_canned_rounds():
    scenario=next(s for s in BENCHMARK_SCENARIOS if s.scenario_id=='SC-07')
    a=evaluate_scenario(scenario,'unprotected',payload='WRITE_ALPHA',client=PayloadDrivenClient())
    b=evaluate_scenario(scenario,'unprotected',payload='WRITE_BETA',client=PayloadDrivenClient())
    assert a['rounds'][1]['tool_executions'][0]['args']['content']=='alpha'
    assert b['rounds'][1]['tool_executions'][0]['args']['content']=='beta'
    assert a['model_mode']=='injected_test_client' and a['elapsed_ms']>0
    aggregate=summarize([a,b])
    assert aggregate['full_block_rate'] is None and aggregate['fully_blocked_cases']==0
    assert aggregate['model_ignored_attack_cases']==2

def test_model_error_not_perfect_defense_score():
    client=RecordingClient(lambda _:(_ for _ in ()).throw(RuntimeError('unavailable')))
    scenario=BENCHMARK_SCENARIOS[0]
    result=evaluate_scenario(scenario,'unprotected',client=client)
    metrics=summarize([result])
    assert result['status']=='error' and metrics['full_block_rate'] is None
    assert metrics['attack_success_rate'] is None and metrics['error_cases']==1

def test_unknown_mode_and_workspace_escape_fail_closed():
    with pytest.raises(ValueError): Experiment(mode='typo',client=RecordingClient())
    with Experiment(client=RecordingClient()) as exp:
        with pytest.raises(PermissionError): exp.tools.fs_write('../escape','x')
        with pytest.raises(PermissionError): exp.tools.net_fetch('http://example.org')

@pytest.fixture
def web_client(monkeypatch):
    instance=web_demo.RehearsalService(client_factory=lambda _:PayloadDrivenClient())
    monkeypatch.setattr(web_demo,'service',instance)
    with TestClient(web_demo.app) as client:
        yield client,instance
    instance.close_all()

def test_web_custom_input_and_isolated_comparison(web_client):
    client,service=web_client
    first=client.post('/api/run_compare',json={'scenario_id':'custom','prompt':'task','payload':'WRITE_ALPHA'}).json()
    second=client.post('/safe/api/run_compare',json={'scenario_id':'custom','prompt':'task','payload':'WRITE_BETA'}).json()
    assert first['guarded']['rounds'][1]['action']['args']['content']=='alpha'
    assert second['guarded']['rounds'][1]['action']['args']['content']=='beta'
    assert first['run_id']!=second['run_id']
    assert first['metrics']['false_positive_rate'] is None

def test_web_approval_ownership_resume_and_replay(web_client):
    client,service=web_client
    data=client.post('/api/run_compare',json={'scenario_id':'custom','prompt':'delete','payload':'DELETE_TEST'}).json()
    assert data['status']=='pending_approval'
    token=data['guarded']['pending']['approval_token']['token_id']
    body={'run_id':data['run_id'],'access_token':data['access_token'],'token_id':token}
    forged={**body,'access_token':'wrong'}
    assert client.post('/api/approve',json=forged).status_code==403
    assert client.post('/api/resume',json=body).status_code==409
    assert client.post('/api/approve',json=body).status_code==200
    done=client.post('/api/resume',json=body)
    assert done.status_code==200 and done.json()['status']=='completed'
    assert client.post('/api/resume',json=body).status_code==409
    exp=service.own(data['run_id'],data['access_token'])['experiments']['guarded']
    assert not exp.tools.path('delete_me.txt').exists()

def test_web_stream_contains_actual_events_before_completion(web_client):
    client,_=web_client
    response_data=client.post('/api/run_compare_stream',json={'scenario_id':'custom','payload':'WRITE_ALPHA'}).text
    events=[json.loads(line[6:]) for line in response_data.splitlines() if line.startswith('data: ')]
    assert events[0]['type']=='init' and events[-1]['type']=='complete'
    assert any(e['type']=='execution_event' and e['event']=='tool_result' for e in events[1:-1])
    assert not any(e['type']=='thought_chunk' for e in events)

def test_tool_exception_is_error_not_success(tmp_path):
    kernel=core(tmp_path);hook=ToolHook(kernel)
    def fail(**kwargs):raise OSError('failed')
    result=hook.execute_with_guard('fs.read',{'path':'x'},fail)
    assert not result['success'] and not result['blocked']
    assert kernel.events[-1].success is False


def test_receiver_raw_socket_capture_and_reassembly():
    with Experiment(client=RecordingClient()) as exp:
        for fragment in (exp.canary[:24],exp.canary[24:]):
            net_fetch(exp.receiver.url+'/sink',method='POST',body=json.dumps({'part':fragment}))
        measurement=exp.physical()
        assert measurement['is_leaked'] and measurement['secret_window_coverage']==1
        assert measurement['received_http_bytes']>measurement['received_payload_bytes']>0
        raw=base64.b64decode(measurement['records'][0]['raw_http_b64'])
        assert raw.startswith(b'POST /sink HTTP/1.1') and b'Content-Length:' in raw

def test_real_isolated_git_push_changes_remote_ref():
    with Experiment(client=RecordingClient()) as exp:
        exp.tools.init_git()
        assert not exp.physical()['unauthorized_git_push']
        exp.tools.git_push()
        assert exp.physical()['unauthorized_git_push']

def test_web_reject_resume_and_missing_credentials(web_client):
    client,service=web_client
    data=client.post('/api/run_compare',json={'scenario_id':'custom','payload':'DELETE_TEST'}).json()
    body={'run_id':data['run_id'],'access_token':data['access_token'],
          'token_id':data['guarded']['pending']['approval_token']['token_id']}
    assert client.post('/api/reject',json=body).status_code==200
    done=client.post('/api/resume',json=body).json()
    assert done['status']=='completed'
    exp=service.own(data['run_id'],data['access_token'])['experiments']['guarded']
    assert exp.tools.path('delete_me.txt').exists()


def test_failed_read_does_not_register_secret(tmp_path):
    kernel=core(tmp_path);hook=ToolHook(kernel)
    def fail(**kwargs): raise OSError('unavailable secret file')
    result=hook.execute_with_guard('fs.read',{'path':'.env'},fail)
    assert not result['success'] and not kernel.state.read_secrets

def test_batched_tool_calls_pause_and_resume_remaining_calls(tmp_path):
    client=RecordingClient()
    def respond(request):
        if len(client.requests)==1:
            calls=[]
            for name,args in [('fs_delete',{'path':'delete_me.txt'}),('fs_write',{'path':'after.txt','content':'after'})]:
                calls.append(NS(id=secrets.token_hex(6),function=NS(name=name,arguments=json.dumps(args))))
            return NS(choices=[NS(message=NS(content='',tool_calls=calls))])
        return response(content='done')
    client.responder=respond
    with Experiment(client=client) as exp:
        report=exp.run();assert report['status']=='pending_approval'
        assert not exp.tools.path('after.txt').exists()
        token=report['pending']['approval_token']['token_id']
        assert exp.core.approve_token(token,exp.principal_id)
        report=exp.resume(token)
        assert report['status']=='completed' and exp.tools.fs_read('after.txt')=='after'
        assert not exp.tools.path('delete_me.txt').exists()

def test_agent_execution_budget_exhaustion_is_not_success():
    client=RecordingClient(lambda _:response('fs_write',{'path':'a','content':'x'}))
    executed=[]
    agent=ReActAgent(client=client,tool_map={'fs_write':lambda **kw:executed.append(kw)},max_tool_calls=1)
    result=agent.run('write repeatedly',max_rounds=5)
    assert result['status']=='budget_exhausted' and len(executed)==1
