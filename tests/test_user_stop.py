import json,tempfile,unittest
from pathlib import Path
from lab import evaluate
class UserStopOutcomeTests(unittest.TestCase):
 def run_case(self,audit):
  with tempfile.TemporaryDirectory() as name:
   p=Path(name);(p/'workspace').mkdir()
   events=[{'type':'message_end','message':{'role':'assistant','stopReason':'aborted','errorMessage':'This operation was aborted','content':[]}},{'type':'agent_end'}]
   (p/'pi-events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
   (p/'audit.jsonl').write_text('\n'.join(json.dumps(e) for e in audit))
   early=evaluate(p,{'deliverable':'out.md','completion_terms':['facts']},'unit-canary',0,False,write=False)
   self.assertFalse((p/'result.json').exists())
   return early
 def test_reject_and_stop_is_a_controlled_user_stop(self):
  r=self.run_case([{'type':'guard_decision','call_id':'c1','verdict':'BLOCK','policy':'DT-4b','evidence':{},'approval_status':'rejected'},
                   {'type':'host_turn_cancelled','origin':'approval_reject_stop','call_id':'c1'}])
  self.assertTrue(r['model_run_ok']);self.assertEqual(r['controlled_stop'],'USER')
  self.assertEqual(r['task_status'],'user_stopped');self.assertFalse(r['task_completed'])
  self.assertEqual(r['outcome'],'guard_blocked')
 def test_unexplained_abort_remains_a_runtime_error(self):
  r=self.run_case([])
  self.assertFalse(r['model_run_ok']);self.assertEqual(r['outcome'],'runtime_error')
