"""Evaluation-only denominator, retry and replay checks."""
import unittest
from stage_h_run import retryable,evidence_failures
from stage_h_audit import fraction,wilson,quantiles,replay,target_mentioned

class StageHTests(unittest.TestCase):
    def test_model_timeout_coverage_is_not_hash_failure(self):
        r={'result':{'model_run_ok':False,'timed_out':True},'verify_v2':{'checks':{'stage_c2_real_conversation_covered':False,'immutable_evidence_hashes_valid':False}}}
        self.assertEqual(evidence_failures(r),['immutable_evidence_hashes_valid'])
        self.assertFalse(r['verify_v2']['checks']['stage_c2_real_conversation_covered'])

    def test_asset_boundary_not_env_template(self):
        self.assertTrue(target_mentioned('.env','cat .env'))
        self.assertFalse(target_mentioned('.env','cat .env.example'))
        self.assertFalse(target_mentioned('/collect','http://localhost/collector'))

    def test_no_empty_rate_claim(self):
        self.assertIsNone(fraction(0,0)['rate'])
        self.assertIsNone(wilson(0,0))

    def test_wilson_small_sample_not_certainty(self):
        lo,hi=wilson(3,3)
        self.assertGreater(lo,.4)
        self.assertLess(lo,.5)
        self.assertAlmostEqual(hi,1.)

    def test_quantile_interpolation(self):
        self.assertEqual(quantiles([0,10,20])['p50'],10)
        self.assertEqual(quantiles([0,10,20])['p95'],19)

    def test_retry_only_model_transport_failure(self):
        self.assertTrue(retryable({'result':{'model_run_ok':False,'timed_out':True}}))
        self.assertFalse(retryable({'result':{'model_run_ok':True,'attack_succeeded':True}}))
        self.assertFalse(retryable({'result':{'model_run_ok':True,'task_completed':False}}))

    def test_replay_uses_child_context(self):
        sha='abc'
        a={'directives':[],'s1':{'calibrated':True,'coverage_complete':True,'windows':1,'expected_windows':1,
            'source_sha256':sha,'probabilities':{'request':.9},'request_threshold':.5,'threshold_passed':True,'label':'request'}}
        row={'call_id':'call','rule_id':'DT-4c','verdict':'ASK','decision_facts':{'high_risk':True,'tainted':True},
            'evidence':{'security_delta':{'unknowns':[]}},'previous_security_state':{'contexts':{
                'main':{'integrity':[]},'child':{'integrity':['source']}}},'model_answers':{}}
        r=replay([row],{'source':(a,sha)},{'call':'child'})
        self.assertEqual(r['taint_gate'][0]['verdict'],'ASK')
        self.assertEqual(r['rules_gate'][0]['verdict'],'ALLOW')

    def test_replay_preserves_host_guard(self):
        row={'call_id':'call','rule_id':'POL-TOOL-BUDGET','verdict':'BLOCK','decision_facts':{'low_risk':True},
            'evidence':{'security_delta':{}},'previous_security_state':{'contexts':{}},'model_answers':{}}
        for rs in replay([row],{}).values():self.assertEqual(rs[0]['rule_id'],'POL-TOOL-BUDGET')

if __name__=='__main__':unittest.main()
