import concurrent.futures,json,time,shutil
from pathlib import Path
from stage_e_regression import OUT,read,save,launch,sha,ROOT
plan=read(OUT/'regression-plan.json');old=read(OUT/'regression.json')
shutil.copy2(OUT/'regression.json',OUT/'regression-before-resume.json')
manifest=read(OUT/'runtime-source-manifest.json')
if any(sha(ROOT/p)!=h for p,h in manifest.items()):raise ValueError('Frozen runtime changed')
indices=[i for i in range(len(plan['cells'])) if not (OUT/f'cells-{i}.json').exists()]
resume={'resumed_unix':time.time(),'remaining_indices':indices,'preserved_n':len(plan['cells'])-len(indices),'reason':'Single completed run exceeded existing 40-tool budget; seven rejected calls lack guard_decision. Keep failed verification; finish untouched cells with original deadline.','original_error':old.get('error')}
status={**old,'status':'running','resume':resume};status.pop('records',None);status.pop('error',None);status.pop('error_type',None)
status['completed']['cells']=len(plan['cells'])-len(indices);save('regression-progress.json',status)
try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  pending={};next_index=0
  while next_index<len(indices) or pending:
   while len(pending)<4 and next_index<len(indices):
    if time.time()+300>plan['deadline_unix']:raise TimeoutError('Original real-run deadline reached')
    i=indices[next_index];pending[pool.submit(launch,'cells',i)]=i;next_index+=1
   done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
   for f in done:
    pending.pop(f);r=f.result();status['completed']['cells']+=1;save('regression-progress.json',status)
 status['status']='completed'
except Exception as e:status.update(status='stopped',error=str(e),error_type=type(e).__name__)
finally:
 records={g:[read(p) for p in sorted(OUT.glob(g+'-*.json'))] for g in ('setup','smoke','cells')}
 status.update(records=records,seconds=time.time()-plan['started_unix'])
 status['verification_failed_run_ids']=[r['run_id'] for rows in records.values() for r in rows if not r['verify_v2']['all_passed']]
 save('regression.json',status);save('regression-progress.json',{k:v for k,v in status.items() if k!='records'})
 print(json.dumps({k:v for k,v in status.items() if k not in ('records','resume')}),flush=True)
