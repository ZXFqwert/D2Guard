import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server
from d2trace import alignment,mask,build_trace
class ConsoleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'runs').mkdir();(self.root/'scenarios').mkdir()
  self.p=patch.object(server,'HERE',self.root);self.p.start();self.c=server.Console(self.root,'python')
 def tearDown(self):self.p.stop();self.tmp.cleanup()
 def test_find_run_binds_subprocess_and_manifest(self):
  good='20261019-111111-abcdef';other='20261019-111112-fedcba'
  for rid in (good,other):
   d=self.root/'runs'/rid;d.mkdir();(d/'manifest.json').write_text(json.dumps({'scenario':'test-run','environment':'attack','protection':'on','guard_engine':'d2v2'}))
  log=self.root/'job.log';log.write_text('RUN '+good+' environment=attack protection=on\n')
  job={'scenario':'test-run','environment':'attack','_log':log};step={'protect':'on','_before':set(),'_log_offset':0}
  self.c._find_run(job,step);self.assertEqual(step['run_id'],good)
  step={'protect':'off','_before':set(),'_log_offset':0};self.c._find_run(job,step);self.assertNotIn('run_id',step)
 def test_filter_modes_and_batches(self):
  rows=[{'id':str(i),'scenario':'s','engine':'d2v2','complete':True,'environment':'clean','protection':'on','decision_mode':m,'batch_id':'batch','verdicts':{},'rules':{}} for i,m in enumerate(('add_risk','rules_gate','taint_gate'))]
  with patch.object(self.c,'refresh_index',return_value=rows):
   self.assertEqual(self.c.overview({'decision_mode':['taint_gate']})['kpi']['runs'],1)
   self.assertEqual(self.c.list_runs({'decision_mode':['rules_gate'],'batch_id':['batch']})['total'],1)
 def test_alignment_does_not_invent_low_risk_or_malice(self):
  self.assertEqual(alignment({'verdict':'ALLOW','executed':True,'decision_facts':{'high_risk':True}}),'off_plan_allowed')
  self.assertEqual(alignment({'verdict':'ASK','rule_id':'DT-4b','executed':False}),'confirmation_stopped')
  self.assertEqual(alignment({'verdict':'BLOCK','rule_id':'POL-TOOL-BUDGET','executed':False}),'budget_stopped')
  self.assertEqual(alignment({'verdict':'ASK','executed':False,'decision_facts':{'request_tainted':True,'high_risk':True}}),'induced_stopped')
  self.assertEqual(alignment({'verdict':'ALLOW','executed':True,'decision_facts':{'request_tainted':True,'low_risk':True},'induced_by':[{'by':'evidence'}]}),'off_plan_low')
  self.assertEqual(alignment({'executed':False}),'pending')
 def test_execution_requires_started_event(self):
  folder=self.root/'runs'/'20261019-111111-abcdef';folder.mkdir()
  (folder/'manifest.json').write_text(json.dumps({'scenario':'s','guard_engine':'d2v2'}))
  events=[]
  for cid,started in [('executed',True),('budget',False)]:
   events.append({'type':'tool_proposed','call_id':cid,'tool':'fs_read','args':{'path':'README.md'}})
   events.append({'type':'guard_decision','call_id':cid,'tool':'fs_read','verdict':'ALLOW' if started else 'BLOCK','rule_id':'DT-3' if started else 'POL-TOOL-BUDGET'})
   if started:events.append({'type':'tool_started','call_id':cid})
   events.append({'type':'tool_result','call_id':cid,'is_error':not started,'text':'test'})
  (folder/'audit.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
  trace=build_trace(folder);calls={c['call_id']:c for c in trace['calls']}
  self.assertTrue(calls['executed']['executed']);self.assertFalse(calls['budget']['executed'])
 def test_unchanged_incomplete_run_is_not_reparsed(self):
  folder=self.root/'runs'/'20261019-111111-abcdef';folder.mkdir()
  (folder/'manifest.json').write_text(json.dumps({'scenario':'s','guard_engine':'d2v2'}))
  self.c.refresh_index();self.c._scanned=0
  with patch.object(self.c,'_summary',wraps=self.c._summary) as summary:
   self.c.refresh_index();summary.assert_not_called()
  (folder/'result.json').write_text(json.dumps({'task_completed':True}));self.c._scanned=0
  self.assertTrue(self.c.refresh_index()[0]['complete'])
 def test_real_command_contract_and_job_binding(self):
  rid='20261019-111111-abcdef';log=self.root/'job.log'
  job={'scenario':'test-run','environment':'attack','_log':log,'steps':[{'protect':'on','status':'queued','run_id':None}]}
  def call(cmd,**kwargs):
   self.assertEqual(cmd[cmd.index('--engine')+1],'d2v2');self.assertIn('--interactive-approval',cmd);self.assertNotIn('--timeout',cmd)
   self.assertEqual(kwargs['env'].get('D2_S1_CONFIG'),server.os.environ.get('D2_S1_CONFIG'))
   self.assertTrue(kwargs['env']['D2_FIXTURE_CANARY'].startswith('d2-test-'))
   folder=self.root/'runs'/rid;folder.mkdir()
   (folder/'manifest.json').write_text(json.dumps({'scenario':'test-run','environment':'attack','protection':'on','guard_engine':'d2v2'}))
   (folder/'result.json').write_text(json.dumps({'model_run_ok':True}))
   kwargs['stdout'].write('RUN '+rid+' environment=attack protection=on\n');kwargs['stdout'].flush()
   return 0
  with patch.object(server.subprocess,'call',side_effect=call):self.c._run_job(job)
  self.assertEqual(job['status'],'finished');self.assertEqual(job['steps'][0]['run_id'],rid)
 def test_new_rule_ids_round_trip_without_relabeling(self):
  folder=self.root/'runs'/'20261019-111111-abcdef';folder.mkdir()
  (folder/'manifest.json').write_text(json.dumps({'scenario':'s','guard_engine':'d2v2'}))
  audit=[];decisions=[{'type':'core_started','decision_mode':'taint_gate'}]
  expected={'DT-4c-S1':'ALLOW','DT-4c-EGRESS':'ASK','POL-TOOL-BUDGET':'BLOCK'}
  for rule,verdict in expected.items():
   audit.append({'type':'guard_decision','call_id':rule,'tool':'fs_write','args':{'path':'x'},'verdict':verdict,'rule_id':rule})
   decisions.append({'type':'decision','call_id':rule,'verdict':verdict,'rule_id':rule,'risk':'R3' if verdict=='BLOCK' else 'R2','decision_facts':{},'evidence':{}})
  (folder/'audit.jsonl').write_text('\n'.join(json.dumps(e) for e in audit))
  (folder/'decisions.jsonl').write_text('\n'.join(json.dumps(e) for e in decisions))
  summary=self.c._summary(folder,{})
  self.assertEqual(summary['rules'],{k:1 for k in expected});self.assertEqual(summary['decision_mode'],'taint_gate')
  trace=build_trace(folder)
  self.assertEqual({c['rule_id']:c['verdict'] for c in trace['calls']},expected)
 def test_mask_both_synthetic_formats(self):
  self.assertNotIn('abcdef',mask('d2-test-abcdef D2-CANARY-abcdef'))
if __name__=='__main__':unittest.main()
