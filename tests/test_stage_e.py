import copy
import hashlib
import itertools
import unittest
import tempfile
from d2v2.core import CoreV2
from d2v2.decision import decide, required_questions
from d2v2.request_taint import context_request_taint, source_request_taint


def analysis(label='none'):
    return {'directives':[], 'structural_gap':False, 's1':{
        'label':label,'calibrated':True,'coverage_complete':True,'windows':1,
        'expected_windows':1,'source_sha256':'sha','request_threshold':0.5,
        'probabilities':{'request':0.9 if label=='request' else 0.1},
        'threshold_passed':label=='request'}}


class StageETests(unittest.TestCase):
    def test_negative_and_request(self):
        for label in ('none','quoted','request'):
            taint,_=context_request_taint([('s',analysis(label),'sha')])
            facts={'high_risk':True,'tainted':True,'decision_mode':'taint_gate','request_tainted':taint,'unknowns':True}
            self.assertEqual(decide(facts,{})[:2],('ASK','DT-4c') if label=='request' else ('ALLOW','DT-4c-S1'))
            self.assertEqual(required_questions(facts),())

    def test_all_sources_not_only_latest(self):
        sources=[('attack',analysis('request'),'sha')]+[(str(i),analysis(),'sha') for i in range(70)]
        self.assertTrue(context_request_taint(sources)[0])
        self.assertEqual(len(context_request_taint(sources)[1]),71)

    def test_failure_closed(self):
        variants=[None,{}, {'structural_gap':True}]
        for key,value in [('calibrated',False),('error_type','TimeoutError'),('coverage_complete',False),('expected_windows',2),('windows',0),('source_sha256','wrong'),('request_threshold',float('nan')),('threshold_passed',True),('label','data'),('probabilities',{'request':float('nan')})]:
            a=analysis();a['s1'][key]=value;variants.append(a)
        for a in variants:
            with self.subTest(a=a):self.assertTrue(source_request_taint(a,source_sha='sha')[0])

    def test_rule_request_cannot_be_cleared(self):
        a=analysis();a['directives']=[{'action_relations':[{'stance':'requested'}]}]
        original=copy.deepcopy(a)
        for mode in ('taint_gate','rules_gate'):self.assertTrue(source_request_taint(a,mode,'sha')[0])
        self.assertEqual(a,original)
        self.assertFalse(source_request_taint(analysis(),'rules_gate','sha')[0])

    def test_earlier_rows_identical(self):
        rows=[({'hard_policy':'POL-TEST'},'BLOCK','POL-TEST'),
              ({'secret_hit':True,'untrusted_sink':True},'BLOCK','DT-2a'),
              ({'context_secret':True,'untrusted_sink':True},'ASK','DT-2b'),
              ({'soft_policy':'POL-SOFT'},'ASK','POL-SOFT'),
              ({'literal_scope':True},'ALLOW','DT-3'),
              ({'sensitive':True,'directive':True},'ASK','DT-4a'),
              ({'sensitive':True},'ASK','DT-4b')]
        for (row,verdict,rule),mode,taint in itertools.product(rows,('add_risk','taint_gate','rules_gate'),(True,False)):
            facts={'high_risk':True,'tainted':True,'unknowns':True,**row,'decision_mode':mode,'request_tainted':taint}
            self.assertEqual(decide(facts,{})[:2],(verdict,rule))
        for mode in ('add_risk','taint_gate','rules_gate'):
            self.assertEqual(decide({'sensitive':True,'decision_mode':mode},{'A1':{'calibrated':True,'threshold_passed':True,'label':'direct'}})[:2],('ALLOW','DT-4b'))

    def test_add_risk_unchanged(self):
        self.assertEqual(decide({'high_risk':True,'tainted':True,'unknowns':True,'request_tainted':False},{})[:2],('ASK','DT-5'))
        self.assertEqual(decide({'high_risk':True,'tainted':False,'decision_mode':'taint_gate'},{})[:2],('ALLOW','DT-4e'))

    def test_runtime_ingestion_and_failure(self):
        class Fast:
            def count_tokens(self,text):return len(text.split())
            def answer_questions(self,views):return {}
        class Content:
            def __init__(self,label):self.label=label
            def classify(self,text,source):
                if self.label=='error':raise TimeoutError('test failure')
                a=analysis(self.label)['s1'];a['source_sha256']=hashlib.sha256(text.encode()).hexdigest();return a
        for label in ('none','quoted','request','error'):
            with self.subTest(label=label),tempfile.TemporaryDirectory() as folder:
                core=CoreV2(True,folder,{'api_key':''},lambda *args:None,fast=Fast(),content_fast=Content(label),decision_mode='taint_gate')
                core.observe({'event_id':'u','type':'agent_start','task':'Read README.md and prepare release documentation.','agent_id':'main'})
                core.observe({'event_id':'r','type':'tool_result','tool':'fs_read','args':{'path':'README.md'},'text':'Aster Tasks uses SQLite.','agent_id':'main'})
                args={'path':'report.md','content':'Aster Tasks uses SQLite.'}
                core.observe({'event_id':'a','type':'assistant_turn','agent_id':'main','text':'','proposals':[{'call_id':'w','tool':'fs_write','args':args}]})
                result=core.decide('fs_write',args,{'call_id':'w','agent_id':'main'})
                self.assertEqual(result['verdict'],'ALLOW' if label in {'none','quoted'} else 'ASK')
                self.assertTrue(core.store.context('main')['integrity'])
                self.assertEqual(result['decision_facts']['request_tainted'],label in {'request','error'})
                core.drain(2);core.store.db.close()
