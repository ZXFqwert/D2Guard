import unittest
from stage_d4_protocol import choose_threshold

class ThresholdTests(unittest.TestCase):
    def test_default_even_when_lower_gives_more_recall(self):
        rows=[{'label':'request'}]*20+[{'label':'none'}]
        p=[[.8,.1,.1]]*19+[[.4,.1,.5],[.45,.1,.45]]
        t,m=choose_threshold(rows,p)
        self.assertEqual(t,.5)
        self.assertEqual(m['request']['recall'],.95)

    def test_highest_threshold_reaching_recall(self):
        rows=[{'label':'request'}]*20
        p=[[.8,.1,.1]]*18+[[.4,.1,.5],[.3,.1,.6]]
        t,m=choose_threshold(rows,p)
        self.assertAlmostEqual(t,.4)
        self.assertEqual(m['request']['recall'],.95)

    def test_missing_positive_support_rejected(self):
        with self.assertRaises(ValueError):choose_threshold([{'label':'none'}],[[.2,.1,.7]])

class SliceTests(unittest.TestCase):
    def test_preserves_long_document_without_implicit_truncation(self):
        from tokenizers import Tokenizer,models,pre_tokenizers
        from stage_d4_collect import slices
        words=['word'+str(i) for i in range(1000)]
        tok=Tokenizer(models.WordLevel({'[UNK]':0,**{w:i+1 for i,w in enumerate(words)}},unk_token='[UNK]'))
        tok.pre_tokenizer=pre_tokenizers.Whitespace()
        tok.no_truncation();tok.no_padding()
        parts=list(slices(tok,' '.join(words),'LOCAL_FILE'))
        self.assertGreater(len(parts),1)
        self.assertEqual(' '.join(parts).split(),words)
        import json
        for part in parts:
            self.assertLessEqual(len(tok.encode(json.dumps({'source_type':'LOCAL_FILE','fragment':part}),add_special_tokens=False).ids),384)

class ActivationTests(unittest.TestCase):
    def test_default_off_and_explicit_off_overrides_production(self):
        from lab import s1_configuration
        self.assertIsNone(s1_configuration({},self.path))
        p=self.path/'.local/stage-d4/s1-enabled-config.json';p.parent.mkdir(parents=True);p.write_text('{}')
        self.assertEqual(s1_configuration({},self.path),str(p))
        self.assertIsNone(s1_configuration({'D2_S1_DISABLE':'1','D2_S1_CONFIG':'experiment'},self.path))
    def setUp(self):
        import tempfile,json,hashlib,time
        from pathlib import Path
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.config={'schema':'d4-request-v1','decision_mode':'add_risk','selected':'multilingual','threshold':.5,'activation':'experiment'}
        metric={'request':{'recall':.96,'precision':.98},'none_fpr':.01,'ece_request_10_bins':.03}
        candidate={'sha256':{'model.safetensors':'frozen'},'temperature':1.9981657266616821,'posttrain_probe_passed':True}
        values={'prior_selection':{'selected':'multilingual','candidates':{'multilingual':candidate},'new_validation_sha256':'validation'},
            'threshold_proof':{'model_sha256':candidate['sha256'],'temperature':candidate['temperature'],'validation_sha256':'validation','threshold':.5,'validation':metric},
            'admission':{'passed':True},'probe':{'pretrain_passed':True},'evaluation':{'threshold':.5,'status':'completed','model_unchanged':True},
            'fresh_admission':{'passed':True,'category':{'documentation':600},'repository_n':30,'distinct_mcp_servers':100,'distinct_command_outputs':100},
            'offline':{'stages':{s:{'s1_on':{'interception_recall':.9},'s1_off':{'interception_recall':.9}} for s in ('c','c2')}},
            'benign':{'metrics':{'all':metric}},'heldout':{'metrics':{s:{'all':metric} for s in ('adjusted_semantic','adjusted_combined')}},
            'gold':{'metrics':{'all':metric}},'regression_plan':{'started_unix':time.time()-1,'deadline_unix':time.time()+60,'planned_n':68}}
        for name,value in values.items():
            p=self.path/(name+'.json');p.write_text(json.dumps(value));self.config[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

    def test_bounded_experiment_accepted(self):
        from d2v2.request_model import accepted
        self.assertIn('multilingual',accepted(self.config)['candidates'])

    def test_changed_threshold_rejected(self):
        from d2v2.request_model import accepted
        self.config['threshold']=.072
        with self.assertRaises(ValueError):accepted(self.config)

    def test_changed_evidence_rejected(self):
        from d2v2.request_model import accepted
        (self.path/'benign.json').write_text('{}')
        with self.assertRaises(ValueError):accepted(self.config)

    def test_experiment_does_not_imply_production(self):
        from d2v2.request_model import accepted
        self.config['activation']='production'
        with self.assertRaises((KeyError,ValueError)):accepted(self.config)

    def test_expired_experiment_rejected(self):
        from d2v2.request_model import accepted
        import json,hashlib
        p=self.path/'regression_plan.json';p.write_text(json.dumps({'started_unix':1,'deadline_unix':2,'planned_n':68}))
        self.config['regression_plan']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):accepted(self.config)

if __name__=='__main__':unittest.main()
