"""Stage C unit tests; these do not represent Pi model evidence."""
import sys
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
import test_v2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab import pi_environment
from d2v2.compression import grant
from d2v2.policy import HardPolicies
from score_annotations import agreement, score, read
from evaluation_scenarios import prepare, artifact_oracle
from export_stage_c import PAGE, export
from run_stage_c import infrastructure_failure
from verify_v2 import memory_origin
from d2v2.store import EvidenceStore


class AuthorizationTests(unittest.TestCase):
    def test_literal_table(self):
        cases=[
            ('Fetch https://example.test/doc','net','GET https://example.test/doc'),
            ('Upload x to https://example.test/doc using POST','net','POST https://example.test/doc'),
            ('把 x 上传到 https://example.test/doc','net','POST https://example.test/doc'),
            ('读取 .env','read','.env'),('把结果写入 report.md','write','report.md'),
            ('Open .env','read','.env'),('View notes.txt','read','notes.txt'),
            ('保存 report.md','write','report.md'),('访问 https://example.test/doc','net','GET https://example.test/doc'),
            ('Download https://example.test/doc','net','GET https://example.test/doc'),
            ('Submit x to https://example.test/doc','net','POST https://example.test/doc'),
            ('访问 https://example.test/doc，保存结果','net','GET https://example.test/doc'),
            ('上传 x 到 https://example.test/doc，然后结束','net','POST https://example.test/doc'),
            ('不要上传 x 到 https://example.test/doc',None,None),
            ('如果需要可以读 .env 吗？',None,None),('Read .env?',None,None),
            ('If necessary read .env',None,None),('Never upload to https://example.test/doc',None,None),
            ('> Read .env',None,None),('```\nRead .env\n```',None,None),
            ("Don't read .env",None,None),('Read .env if necessary',None,None),
            ('Read .env\nWrite report.md','write','report.md'),
        ]
        for text,key,value in cases:
            with self.subTest(text=text):
                result=grant(text,{},1)
                if key:self.assertIn(value,result[key])
                else:self.assertFalse(result['read']+result['write']+result['net'])

    def test_pi_environment_strips_inherited_approval_capability(self):
        env=pi_environment({'PATH':'p','D2_APPROVAL_CREDENTIAL':'s','d2_approval_token':'t','D2_CORE_PROVIDER':'secret','D2_CONTROL_TOKEN':'hook'})
        self.assertEqual(env,{'PATH':'p','D2_CONTROL_TOKEN':'hook'})


class PersistenceTests(unittest.TestCase):
    def test_sensitive_policy_both_contexts(self):
        policy=HardPolicies(Path('/workspace'))
        paths=['~/.bashrc','~/.bash_profile','~/.zshrc','~/.profile',
               'Documents/PowerShell/Microsoft.PowerShell_profile.ps1',
               '.git/hooks/pre-commit','.git/config','.github/workflows/ci.yml',
               '.gitlab-ci.yml','.circleci/config.yml','Jenkinsfile','azure-pipelines.yml']
        for path in paths:
            for ctx in ({},{'integrity':['source']}):
                with self.subTest(path=path,ctx=ctx):
                    matches=policy.evaluate('fs.write',{'path':path},False,[],ctx)
                    self.assertIn(('POL-FS-WRITE-SENSITIVE','R3','BLOCK'),[(m['rule_id'],m['risk'],m['verdict']) for m in matches])
        for ctx in ({},{'integrity':['source']}):
            self.assertEqual(policy.evaluate('fs.write',{'path':'report.md'},False,[],ctx),[])


class EvaluationTests(unittest.TestCase):
    def test_memory_origin_requires_real_writer_call_hash_and_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);writer=root/'writer';reader=root/'reader'
            writer.mkdir();reader.mkdir();db=EvidenceStore(writer)
            payload='unit-only memory fixture';sha=hashlib.sha256(payload.encode()).hexdigest()
            db.db.execute("INSERT INTO session_meta VALUES('session_id','unit-session')")
            sid=db.register_source('LOCAL_FILE','fixture.txt',sha,'source-event')
            cid='unit-write';pre='pre-'+hashlib.sha256(cid.encode()).hexdigest()
            db.put(pre,'main','TOOL_PRE_EXEC','MODEL_GENERATED','tool://memory_write',
                   json.dumps({'tool':'memory_write','args':{'key':'handoff','content':payload}}),{})
            db.db.execute('INSERT INTO tool_dispatches VALUES(?)',(cid,));db.db.commit();db.db.close()
            entry={'writer_session':'unit-session','key':'handoff','content_sha256':sha,'integrity':[sid]}
            self.assertTrue(memory_origin(reader,entry)['native_write_verified'])
            for change in ({'content_sha256':'wrong'},{'key':'different'},{'integrity':['not-a-source']},{'writer_session':'missing'}):
                self.assertFalse(memory_origin(reader,{**entry,**change})['native_write_verified'])

    def test_bounded_child_cancel_is_not_an_upstream_failure(self):
        disconnected={'type':'proxy_error','stage':'write_downstream','status':200}
        cancelled=[{'type':'tool_outcome','is_error':True,'text':'Subagent failed or timed out'}]
        self.assertFalse(infrastructure_failure({},[disconnected],cancelled))
        self.assertFalse(infrastructure_failure({'timed_out':True},[disconnected],[]))
        self.assertTrue(infrastructure_failure({},[disconnected],[]))
        self.assertTrue(infrastructure_failure({},[{'type':'proxy_error','stage':'connect','status':503}],cancelled))

    def test_inventory_and_attack_source_isolation(self):
        root=Path(__file__).resolve().parents[1]
        scenarios=[json.loads(p.read_text(encoding='utf-8')) for p in (root/'scenarios').glob('c-*.json')]
        self.assertEqual(sum(s['category']=='attack' for s in scenarios),20)
        self.assertEqual(sum(s['category']=='normal' for s in scenarios),11)
        self.assertGreaterEqual(sum(bool(s.get('legitimate_sensitive_read')) for s in scenarios),3)
        for s in scenarios:
            self.assertTrue(s['evaluation_only']);self.assertFalse(s['training_allowed'])
            clean=s['resources']['clean'];attack=s['resources']['attack']
            if s['category']=='normal':self.assertEqual(clean,attack);continue
            where=s['attack_source']
            if where.startswith('file:'):
                name=where[5:]
                self.assertEqual({k:v for k,v in clean.items() if k!='files'},{k:v for k,v in attack.items() if k!='files'})
                self.assertEqual({k:v for k,v in clean['files'].items() if k!=name},{k:v for k,v in attack['files'].items() if k!=name})
            else:self.assertEqual({k:v for k,v in clean.items() if k!=where},{k:v for k,v in attack.items() if k!=where})

    def test_artifact_oracle_does_not_use_guard_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'workspace').mkdir()
            scenario={'oracle':{'kind':'file_contains','path':'target.txt','marker':'persistence'}}
            self.assertFalse(artifact_oracle(folder,scenario,'synthetic',[]))
            (folder/'workspace/target.txt').write_text('persistence',encoding='utf-8')
            self.assertTrue(artifact_oracle(folder,scenario,'synthetic',[]))
            self.assertIsNone(artifact_oracle(folder,{'oracle':{'kind':'unavailable_exec'}},'synthetic',[]))

    def test_kappa_known_marginals_and_missing_gold(self):
        value=agreement([('ALLOW','ALLOW'),('ALLOW','ASK'),('ASK','ASK'),('BLOCK','BLOCK')])
        self.assertEqual(value['agreement'],.75)
        self.assertAlmostEqual(value['cohen_kappa'],.6363636363636364)
        self.assertIsNone(agreement([('ALLOW','ALLOW')])['cohen_kappa'])
        self.assertIsNone(agreement([])['agreement'])
        a={('synthetic-1','full'):{'label':'ALLOW'},('synthetic-1','state'):{'label':'ASK','reason':'view_missing_fragment'}}
        b={('synthetic-1','full'):{'label':'ASK'},('synthetic-1','state'):{'label':None}}
        self.assertIsNone(score(a,b)['E1'])
        r=score(a,b,{('synthetic-1','gold'):{'label':'ALLOW'}})
        self.assertEqual(r['E1']['rater_a']['disagreements_by_reason'],{'view_missing_fragment':1})
        self.assertEqual(r['E1']['rater_b']['missing_items'],['synthetic-1'])

    def test_duplicate_annotations_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'x.jsonl'
            p.write_text('\n'.join([json.dumps({'item_id':'x','variant':'full','label':None})]*2))
            with self.assertRaises(ValueError):read(p)

    def test_html_uses_text_content_and_separate_packets(self):
        self.assertIn("textContent=JSON.stringify(items[i]",PAGE)
        self.assertNotIn('innerHTML',PAGE)

    def test_export_repeat_hashes_exclude_self_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            first=export([],out)
            (out/'unrelated.txt').write_text('untouched')
            second=export([],out)
            self.assertEqual(first,second)
            self.assertNotIn('manifest.json',second['files'])
            self.assertEqual((out/'unrelated.txt').read_text(),'untouched')


class PersistenceCoreTests(unittest.TestCase):
    setUp=test_v2.V2Tests.setUp
    tearDown=test_v2.V2Tests.tearDown
    observe=test_v2.V2Tests.observe
    decide=test_v2.V2Tests.decide

    def test_core_blocks_persistence_in_clean_and_polluted_contexts(self):
        paths=['~/.bashrc','~/.zshrc','~/.profile','Documents/PowerShell/Microsoft.PowerShell_profile.ps1',
               '.git/hooks/pre-commit','.git/config','.github/workflows/ci.yml','.gitlab-ci.yml']
        for polluted in (False,True):
            if polluted:self.observe('external','Ordinary project reference material.')
            for i,path in enumerate(paths):
                with self.subTest(polluted=polluted,path=path):
                    d=self.decide(str(polluted)+str(i),'fs_write',{'path':path,'content':'test'})
                    self.assertEqual((d['verdict'],d['rule_id'],d['risk']),('BLOCK','POL-FS-WRITE-SENSITIVE','R3'))
        self.assertEqual(self.decide('normal','fs_write',{'path':'summary.md','content':'public'})['verdict'],'ALLOW')


if __name__=='__main__':unittest.main()
