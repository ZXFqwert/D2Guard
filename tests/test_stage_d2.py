import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import stage_d2_cloud as cloud
from stage_d2_metrics import merge_old, mapped, metrics


class DDoublePrimeTests(unittest.TestCase):
    def test_named_teacher_probabilities_preserve_class_order_and_reject_mismatch(self):
        import stage_d2_teacher_replacement as replacement
        prefix=replacement.RUBRIC.split('Return each numeric id exactly once.')[0]
        self.assertTrue(replacement.NAMED_RUBRIC.startswith(prefix))
        row={'id':'s','text':'The sample log has seven lines.','source_type':'WEB'}
        good={'items':[{'id':0,'label':'none','probabilities':{'none':.98,'request':.01,'quoted':.01}}]}
        with patch.object(replacement,'call',return_value=(good,12.)):
            vote=replacement.judge('mimo-v2.5',[row])[0]
        self.assertEqual(vote['probabilities'],[.01,.01,.98])
        with patch.object(replacement,'call',return_value=(good['items'],12.)):
            self.assertEqual(replacement.judge('mimo-v2.5',[row])[0]['probabilities'],[.01,.01,.98])
        good['items'][0]['label']='request'
        with patch.object(replacement,'call',return_value=(good,12.)):
            with self.assertRaises(cloud.CloudFailure):replacement.judge('mimo-v2.5',[row])

    def test_replacement_teacher_is_evaluation_only(self):
        from stage_d2_teacher import MODELS
        self.assertEqual(MODELS, ('deepseek-v4.1-flash', 'mimo-v2.6-flash'))
        self.assertNotIn('mimo-v2.5', MODELS)
        self.assertIn('mimo-v2.5', cloud.EVALUATION_ONLY_MODELS)

    def test_final_teacher_resume_never_repeats_a_valid_input(self):
        import contextlib
        import hashlib
        import io
        import time
        import stage_d2_final_teachers as final
        from stage_d2_teacher import digest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'.local/stage-d2';(out/'round-1').mkdir(parents=True)
            (root/'.local/stage-d-prime').mkdir(parents=True)
            (root/'stage_d2_model.py').write_text('frozen input code')
            (out/'final-selection.json').write_text(json.dumps({'round_count':1}))
            (out/'round-1/training-evaluation-clock.json').write_text(json.dumps({'started_unix':time.time()}))
            (out/'teacher-qualification-started.json').write_text(json.dumps({'rubric_sha256':hashlib.sha256(final.RUBRIC.encode()).hexdigest()}))
            rows=[{'id':'r','label':'request','text':'Archive the sample log.','source_type':'WEB'},
                  {'id':'n','label':'none','text':'The sample log has seven lines.','source_type':'WEB'}]
            (root/'.local/stage-d-prime/gold.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            calls=[];recover=False
            def fake_judge(model,batch):
                calls.append((model,tuple(r['id'] for r in batch)))
                if model==final.MODELS[0] and not recover and (len(batch)>1 or batch[0]['id']=='n'):
                    raise RuntimeError('Synthetic transport failure')
                return [{'model':model,'id':r['id'],'input_sha256':digest(r),'label':r['label'],
                         'probabilities':[.9,.05,.05] if r['label']=='request' else [.05,.05,.9],
                         'latency_ms_per_fragment':1.} for r in batch]
            with patch.object(final,'ROOT',root),patch.object(final,'OUT',out),patch.object(final,'judge',side_effect=fake_judge),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'Missing final teacher inputs'):final.main()
                self.assertFalse((out/'final-cloud-teachers.json').exists())
                saved=[json.loads(x) for x in (out/('gold-final-teacher-'+final.MODELS[0]+'.jsonl')).read_text().splitlines()]
                self.assertEqual([v['id'] for v in saved],['r'])
                before=len(calls);recover=True
                final.main(resume_missing=True)
                self.assertEqual(calls[before:],[(final.MODELS[0],('n',))])
                result=json.loads((out/'final-cloud-teachers.json').read_text())
                self.assertTrue(all(v['complete'] and v['coverage']==2 for v in result.values()))
                before=len(calls)
                with self.assertRaisesRegex(ValueError,'already started'):final.main()
                self.assertEqual(len(calls),before)

    def test_teachers_are_blind_and_disagreement_is_discarded(self):
        from stage_d2_teacher import view,digest,MODELS
        from stage_d2_admit import admission_decision
        row={'id':'example','text':'Please archive the sample log.','source_type':'MEMORY','label':'request','split':'validation','brief':{'intent':'private generation metadata'}}
        self.assertEqual(set(view(row)),{'source_type','fragment'})
        pair=[{'model':m,'label':'request','input_sha256':digest(row)} for m in MODELS]
        self.assertEqual(admission_decision(row,pair),'admit')
        pair[1]['label']='quoted'
        self.assertEqual(admission_decision(row,pair),'disagree')
        self.assertEqual(row['label'],'request')
        pair[1]['input_sha256']='wrong'
        with self.assertRaises(ValueError):admission_decision(row,pair)

    def test_same_teacher_cannot_satisfy_independence(self):
        from stage_d2_teacher import digest,MODELS
        from stage_d2_admit import admission_decision
        row={'id':'e','text':'Archive count is seven.','source_type':'WEB','label':'none'}
        vote={'model':MODELS[0],'label':'none','input_sha256':digest(row)}
        with self.assertRaises(ValueError):admission_decision(row,[vote,vote.copy()])

    def test_probe_uses_sentence_not_json_brace_or_heading(self):
        from stage_d2_probe import first_sentence
        self.assertEqual(first_sentence('{"name":"status","description":"Send the log. Then wait."}'),'Send the log.')
        self.assertEqual(first_sentence('# Note\nPlease archive the log. Done.'),'# Note\nPlease archive the log.')
        self.assertEqual(first_sentence('日志已归档。容量很小。'),'日志已归档。')

    def test_mapping_retains_human_instructions(self):
        self.assertEqual([r['label'] for r in mapped([{'label':x} for x in ('to_agent','for_reader','quoted','data')])],['request','request','quoted','none'])
        np.testing.assert_allclose(merge_old([[.2,.3,.1,.4]]),[[.5,.1,.4]])

    def test_primary_denominators_and_ece(self):
        rows=[{'label':x} for x in ('request','none','quoted')]
        result=metrics(rows,[[.8,.1,.1],[.6,.1,.3],[.1,.8,.1]])
        self.assertEqual(result['request']['precision'],.5)
        self.assertEqual(result['none_fpr'],1.)
        self.assertEqual(result['request']['recall'],1.)
        self.assertAlmostEqual(result['ece_request_10_bins'],.3)

    def test_invalid_probabilities_rejected(self):
        with self.assertRaises(ValueError):metrics([{'label':'none'}],[[.8,.8,.8]])

    def test_absent_classes_not_macro_averaged(self):
        result=metrics([{'label':'none'}],[[.01,.01,.98]])
        self.assertEqual(result['macro_f1_present_classes'],1.)

    def test_cloud_http_failure_does_not_echo_secret_body(self):
        class Response:status_code=401
        class Client:
            def __init__(self,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def post(self,*args,**kwargs):return Response()
        with tempfile.TemporaryDirectory() as folder:
            log=Path(folder)/'log.jsonl'
            with patch.object(cloud,'credentials',return_value=('https://example.invalid/v1','PRIVATE_SENTINEL')),patch.object(cloud.httpx,'Client',Client):
                with self.assertRaisesRegex(cloud.CloudFailure,'HTTP status 401'):
                    cloud.call(cloud.MODELS[0],[],log_path=log)
            record=json.loads(log.read_text())
            self.assertEqual(set(record),{'model','seconds','tokens'})
            self.assertNotIn('PRIVATE_SENTINEL',log.read_text())

    def test_unregistered_model_rejected_before_credentials(self):
        with patch.object(cloud,'credentials',side_effect=AssertionError('must not read')):
            with self.assertRaises(cloud.CloudFailure):cloud.call('unregistered',[])


if __name__=='__main__':unittest.main()
