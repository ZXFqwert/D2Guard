import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import server


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch.object(server,'HERE',Path(self.tmp.name)):
            self.console=server.Console(self.tmp.name,'python')
        self.pending={'status':'running','approvals':[{'run_id':'run','call_id':'call','tool':'fs_write','args':{'path':'public.txt'}}]}

    def tearDown(self):self.tmp.cleanup()

    def test_browser_cannot_substitute_tool_or_arguments(self):
        with patch.object(self.console,'job',return_value=self.pending), patch.object(self.console,'_host_control',return_value={'approval_status':'approved_once'}) as host:
            code,_=self.console.resolve_approval('job',{'run_id':'run','call_id':'call','choice':'approve','tool':'exec','args':{'command':'wrong'}})
        self.assertEqual(code,200)
        host.assert_called_once_with('run','/resolve-approval',{'call_id':'call','choice':'approve'})

    def test_stale_or_wrong_run_cannot_be_resolved(self):
        with patch.object(self.console,'job',return_value=self.pending),patch.object(self.console,'_host_control') as host:
            for body in ({'run_id':'other','call_id':'call','choice':'approve'}, {'run_id':'run','call_id':'other','choice':'reject'}):
                self.assertEqual(self.console.resolve_approval('job',body)[0],409)
            host.assert_not_called()

    def test_unreachable_channel_still_shows_the_waiting_call(self):
        run=Path(self.tmp.name)/'runs'/'20261020-120000-000001';run.mkdir(parents=True)
        events=[{'type':'tool_proposed','call_id':'c1','agent_id':'main','tool':'fs_read','args':{'path':'.env'}},
                {'type':'guard_decision','call_id':'c1','verdict':'ASK','policy':'DT-4b','reason':'sensitive'},
                {'type':'approval_waiting','call_id':'c1'},
                {'type':'tool_proposed','call_id':'c0','agent_id':'main','tool':'exec','args':{}},
                {'type':'approval_waiting','call_id':'c0'},{'type':'guard_decision','origin':'host_approval','call_id':'c0'}]
        (run/'audit.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
        self.console.jobs['j']={'id':'j','status':'running','_log':Path(self.tmp.name)/'j.log',
            'steps':[{'protect':'on','status':'running','run_id':run.name}],'started':0}
        with patch.object(self.console,'_host_control',side_effect=OSError('refused')):
            job=self.console.job('j')
        self.assertEqual([a['call_id'] for a in job['approvals']],['c1'])
        self.assertTrue(job['approvals'][0]['channel_error'])
        self.assertIn('refused',job['approval_error'])

    def test_lanes_run_at_the_same_time(self):
        barrier=threading.Barrier(2,timeout=5)
        job={'id':'p','scenario':'s','environment':'attack','status':'running','_log':Path(self.tmp.name)/'p.log',
             'steps':[{'protect':p,'status':'queued','run_id':None} for p in ('off','on')]}
        def call(cmd,**kwargs):
            barrier.wait()  # breaks (and fails the lane) if the lanes ran one after another
            return 0
        with patch.object(server.subprocess,'call',side_effect=call):self.console._run_job(job)
        self.assertFalse(barrier.broken)

    def test_host_denial_is_not_reported_as_success(self):
        with patch.object(self.console,'job',return_value=self.pending),patch.object(self.console,'_host_control',side_effect=ValueError('expired')):
            self.assertEqual(self.console.resolve_approval('job',{'run_id':'run','call_id':'call','choice':'approve'})[0],409)


if __name__=='__main__':unittest.main()
