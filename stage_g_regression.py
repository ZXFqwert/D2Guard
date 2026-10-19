"""Real Pi stage-G smoke/matrix, explicit budgets and immutable per-cell records."""
import argparse,concurrent.futures,hashlib,json,os,secrets,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'.local/stage-g'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def worker(group,index):
 from lab import run
 from verify_v2 import verify
 from stage_f_audit import audit_run
 from d2v2.trace import build_trace,upstream_sources
 plan=read(OUT/'regression-plan.json');cell=plan[group][index]
 if time.time()>plan['deadline_unix']:raise TimeoutError('Real run deadline exceeded')
 os.environ.pop('D2_S1_DISABLE',None);os.environ.pop('D2_S1_CONFIG',None)
 memory=None
 scenario=read(ROOT/'scenarios'/(cell['scenario']+'.json'))
 if scenario.get('source_channel')=='memory':
  import shutil
  memory=OUT/'memory-cells'/f'{group}-{index}'
  shutil.copytree(ROOT/'.local/stage-e/memory'/(cell['scenario']+'-'+cell['environment']),memory)
 args=argparse.Namespace(scenario=cell['scenario'],environment=cell['environment'],protect=cell['protect'],timeout=cell.get('timeout',180),model_request_limit=20,tool_call_limit=40,engine='d2v2',memory_root=str(memory) if memory else None,task=None,phase='stage-g-'+group)
 result=run(args,plan['canary'],plan['batch_id']+'-'+group);folder=ROOT/'runs'/result['run_id']
 verified=verify(folder);trace=build_trace(folder)
 held=[{'call_id':c['call_id'],'agent':c['agent'],'verdict':c['verdict'],'rule_id':c['rule_id'],'evidence_refs':c.get('evidence_refs'),'upstream_sources':upstream_sources(trace['graph'],c['call_id'])} for c in trace['calls'] if c.get('verdict') in ('ASK','BLOCK')]
 save(OUT/f'{group}-{index}.json',dict(cell=cell,run_id=result['run_id'],result=result,verify_v2=verified,held=held,trace_audit=audit_run(folder),agents=trace['agents']))
def launch(group,index):
 path=OUT/f'{group}-{index}.json'
 if path.exists():return read(path)
 with (OUT/f'{group}-{index}.log').open('w') as f:
  p=subprocess.run([sys.executable,__file__,'worker',group,str(index)],stdout=f,stderr=subprocess.STDOUT,timeout=1200)
 if p.returncode:raise RuntimeError(f'Worker {group}-{index} failed; retained without rerun')
 return read(path)
def main(group):
 OUT.mkdir(parents=True,exist_ok=True)
 if not (OUT/'regression-plan.json').exists():
  names=sorted(p.stem for p in (ROOT/'scenarios').glob('g-*.json'))
  smoke=[dict(scenario=n,environment=e,protect=p) for n in names for e,p in [('clean','on'),('attack','off')]]
  cells=[dict(scenario=n,environment=e,protect=p,repeat=r) for n in names for e in ('clean','attack') for p in ('off','on') for r in (1,2)]
  regression=[dict(scenario=p.stem,environment='attack',protect='on') for p in sorted((ROOT/'scenarios').glob('e-*.json'))]
  save(OUT/'regression-plan.json',dict(batch_id='stage-g-'+time.strftime('%Y%m%d-%H%M%S'),started_unix=time.time(),deadline_unix=time.time()+5400,canary='D2-CANARY-'+secrets.token_hex(16),smoke=smoke,cells=cells,regression=regression))
 plan=read(OUT/'regression-plan.json');status={'group':group,'started_unix':time.time(),'completed':0,'planned':len(plan[group]),'status':'running'}
 save(OUT/(group+'-progress.json'),status)
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   pending={};index=0;failed=False
   while pending or index<len(plan[group]):
    while not failed and len(pending)<3 and index<len(plan[group]):
     pending[pool.submit(launch,group,index)]=index;index+=1
    if not pending:break
    done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
    for future in done:
     pending.pop(future)
     try:
      record=future.result();status['completed']+=1;save(OUT/(group+'-progress.json'),status)
      if not record['verify_v2']['all_passed']:
       status.setdefault('failed_runs',[]).append(record['run_id'])
       if group.startswith('smoke'):raise RuntimeError('Verification failed: '+record['run_id'])
     except Exception:
      failed=True
      raise
  status['status']='completed'
 except Exception as exc:status.update(status='stopped',error=str(exc))
 status['elapsed_seconds']=time.time()-status['started_unix'];save(OUT/(group+'-progress.json'),status)
if __name__=='__main__':
 if sys.argv[1]=='worker':worker(sys.argv[2],int(sys.argv[3]))
 else:main(sys.argv[1])
