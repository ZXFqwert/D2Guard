"""Exactly two fits; shared 60-minute training/evaluation wall clock."""
import json
import os
import subprocess
import sys
import time
from stage_d5_protocol import ROOT,OUT,save,sha

def main():
    gate=json.loads((OUT/'admission.json').read_text());probe=json.loads((OUT/'probe.json').read_text())
    if not gate['passed'] or not probe['pretrain_passed']:raise ValueError('Admission or shortcut gate failed')
    if (OUT/'training-clock.json').exists():raise ValueError('Training round already started')
    save('training-clock.json',{'started_unix':time.time()})
    files=[*ROOT.glob('stage_d5_*.py'),ROOT/'train_stage_d5.py',ROOT/'evaluate_stage_d5.py',OUT/'admitted.jsonl',OUT/'new-validation-frozen.jsonl',OUT/'real-test-frozen.jsonl',OUT/'host-test-frozen.jsonl']
    files += [*ROOT.glob('stage_d*.py'),*ROOT.glob('train_stage_d*.py'),*(ROOT/'src').rglob('*.py')]
    manifest={str(p.relative_to(ROOT)):sha(p) for p in files};save('training-source-manifest.json',{'sha256':manifest,'round':1})
    env={**os.environ,'CUDA_VISIBLE_DEVICES':'0','OMP_NUM_THREADS':'4','PYTHONPATH':'src'};status={'status':'running','completed':[]}
    def run(name,args):
        for path,expected in manifest.items():
            if sha(ROOT/path)!=expected:raise ValueError('Frozen source/data changed during fitting')
        status['active']=name;save('training-runner.json',status)
        remaining=min(json.loads((OUT/'training-clock.json').read_text())['started_unix']+3600,json.loads((OUT/'protocol.json').read_text())['stage_deadline_unix'])-time.time()
        if remaining<=0:raise TimeoutError('Registered shared training/evaluation limit')
        with (OUT/(name+'.log')).open('x',encoding='utf-8') as stream:subprocess.run([sys.executable,'-u',*args],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=remaining,check=True)
        status['completed'].append(name);save('training-runner.json',status)
    try:
        for base in ('multilingual','english'):
            run(base+'-smoke',['train_stage_d5.py',base,'--smoke'])
            smoke=json.loads((OUT/(base+'-smoke.json')).read_text())
            if not smoke['passed'] or not smoke['original_unchanged']:raise RuntimeError('Forward/backward smoke failed')
        for base in ('multilingual','english'):run(base+'-fit',['train_stage_d5.py',base])
        run('frozen-evaluation',['evaluate_stage_d5.py'])
        status['status']='completed'
    except Exception as e:status.update(status='stopped',error_type=type(e).__name__,reason=str(e));raise
    finally:status['finished_unix']=time.time();save('training-runner.json',status)

if __name__=='__main__':main()
