"""Portable real-Pi four-cell evaluation. Raw attempts and verification are retained."""
import argparse,concurrent.futures,json,os,secrets,subprocess,sys,time,shutil,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def execute(spec):
 from lab import run
 from verify_v2 import verify
 scenario,environment,protect,repeat,limits,batch,canary,seed=spec
 memory=None
 if seed:
  parent=ROOT/".local/evaluation-memory";parent.mkdir(parents=True,exist_ok=True)
  memory=tempfile.mkdtemp(dir=parent);shutil.copytree(seed,memory,dirs_exist_ok=True)
 os.environ['D2_HOST_EXEC']='1'
 args=argparse.Namespace(scenario=scenario,environment=environment,protect=protect,timeout=limits[2],model_request_limit=limits[0],tool_call_limit=limits[1],engine='d2v2',memory_root=memory,task=None,phase='evaluation')
 result=run(args,canary,batch);folder=ROOT/'runs'/result['run_id'];check=verify(folder)
 record={'scenario':scenario,'environment':environment,'protect':protect,'repeat':repeat,'result':result,'verify_v2':check}
 save(folder/'evaluation.json',record);return record
def main():
 p=argparse.ArgumentParser();p.add_argument('--scenario',action='append');p.add_argument('--repeats',type=int,default=3);p.add_argument('--workers',type=int,default=8);p.add_argument('--model-request-limit',type=int,default=100);p.add_argument('--tool-call-limit',type=int,default=40);p.add_argument('--timeout',type=int,default=180);a=p.parse_args()
 if min(a.repeats,a.workers,a.model_request_limit,a.tool_call_limit,a.timeout)<1:p.error('Positive values required')
 batch='evaluation-'+time.strftime('%Y%m%d-%H%M%S');specs=[];preludes=[]
 (ROOT/'runs').mkdir(exist_ok=True)
 for scenario in a.scenario or [p.stem for p in sorted((ROOT/'scenarios').glob('*.json')) if p.stem.split('-')[0] in ('c','c2','e','g')]:
  for repeat in range(a.repeats):
   canary='d2-test-'+secrets.token_hex(16)
   fixture=json.loads((ROOT/'scenarios'/(scenario+'.json')).read_text(encoding='utf-8'))
   for env in ('clean','attack'):
    seed=None
    if fixture.get('setup_task'):
     from lab import run
     from verify_v2 import verify
     seed=ROOT/'.local/evaluation-memory'/batch/scenario/str(repeat)/env;seed.mkdir(parents=True)
     setup=argparse.Namespace(scenario=scenario,environment=env,protect='off',timeout=a.timeout,model_request_limit=a.model_request_limit,tool_call_limit=a.tool_call_limit,engine='d2v2',memory_root=str(seed),task=fixture['setup_task'],phase='evaluation-memory-writer')
     writer=run(setup,canary,batch);preludes.append({'result':writer,'verify_v2':verify(ROOT/'runs'/writer['run_id'])})
     save(ROOT/'runs'/(batch+'-memory-writers.json'),preludes)
    for protect in ('off','on'):specs.append((scenario,env,protect,repeat,(a.model_request_limit,a.tool_call_limit,540 if scenario in ('g-attack-nested','g-normal-nested') else a.timeout),batch,canary,str(seed) if seed else None))

 records=[];(ROOT/'runs').mkdir(exist_ok=True)
 with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
  for spec,record in zip(specs,pool.map(execute,specs)):
   records.append(record);save(ROOT/'runs'/(batch+'.json'),{'records':records})
 # One retained retry for model/upstream failures; never choose the better attempt.
 chosen=[]
 for spec,record in zip(specs,records[:]):
  r=record['result']
  if not r.get('model_run_ok') and (r.get('timed_out') or r.get('model_errors') or r.get('runtime_diagnostics',{}).get('gateway_errors')):
   record=execute(spec);records.append(record)
  chosen.append(record)
 summary={}
 for env in ('clean','attack'):
  for protect in ('off','on'):
   group=[r for r in chosen if r['environment']==env and r['protect']==protect]
   valid=[r for r in group if r['result'].get('model_run_ok')]
   summary[env+'/'+protect]={'n':len(group),'model_valid_n':len(valid),'task_success_n':sum(bool(r['result'].get('task_completed')) for r in valid),'attack_success_n':sum(bool(r['result'].get('attack_succeeded')) for r in valid),'verify_passed_n':sum(bool(r['verify_v2'].get('all_passed')) for r in group)}
 save(ROOT/'runs'/(batch+'.json'),{'records':records,'chosen_run_ids':[r['result']['run_id'] for r in chosen],'summary':summary,'denominator_note':'Descriptive model-valid runs; not attack-attempt-conditioned ASR.'});print(batch)
if __name__=='__main__':main()
