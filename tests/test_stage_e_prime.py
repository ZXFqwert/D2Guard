import json,tempfile,unittest
from d2v2.core import CoreV2
from d2v2.decision import decide
from test_v2 import FastStub

class StageEPrimeTests(unittest.TestCase):
 def test_egress_and_priority(self):
  for mode in ('taint_gate','rules_gate'):
   base={'decision_mode':mode,'high_risk':True,'tainted':True,'request_tainted':False,'untrusted_sink':True}
   for extra,want in [({},('ASK','DT-4c-EGRESS','R2')),({'literal_scope':True,'network_granted':True},('ALLOW','DT-3','R0')),({'untrusted_sink':False},('ALLOW','DT-4c-S1' if mode=='taint_gate' else 'DT-4c-RULE','R1')),({'request_tainted':True},('ASK','DT-4c','R2')),({'secret_hit':True},('BLOCK','DT-2a','R3')),({'context_secret':True},('ASK','DT-2b','R2')),({'sensitive':True},('ASK','DT-4b','R2')),({'sensitive':True,'directive':True},('ASK','DT-4a','R2')),({'hard_policy':'HARD'},('BLOCK','HARD','R3'))]:
    self.assertEqual(decide({**base,**extra},{})[:3],want)
 def test_budget_records_exact_bound_call_even_protection_off(self):
  for enabled in (False,True):
   with tempfile.TemporaryDirectory() as folder:
    events=[];core=CoreV2(enabled,folder,{'api_key':''},lambda n,e:events.append((n,e)),fast=FastStub())
    core.observe({'event_id':'u','type':'agent_start','task':'Write report.md.'})
    args={'path':'report.md','content':'预算测试'}
    core.observe({'event_id':'p','type':'assistant_turn','proposals':[{'call_id':'x','tool':'fs_write','args':args}]})
    result=core.decide('fs_write',args,{'call_id':'x','host_tool_budget_exceeded':True,'tool_index':41})
    self.assertEqual((result['verdict'],result['rule_id'],result['risk']),('BLOCK','POL-TOOL-BUDGET','R3'))
    self.assertIs(result['executed'],False);self.assertIs(result['execution_allowed'],False)
    row=core.store.db.execute('SELECT decision,status FROM calls WHERE id=?',('x',)).fetchone()
    self.assertEqual(row['status'],'BLOCK');self.assertEqual(json.loads(row['decision'])['rule_id'],'POL-TOOL-BUDGET')
    self.assertTrue(any(n=='decisions.jsonl' and e.get('call_id')=='x' for n,e in events))
    core.drain(2);core.store.db.close()
