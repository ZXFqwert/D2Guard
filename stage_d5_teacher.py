"""D5 dual-teacher label/kind votes; no test examples in public output."""
import collections
import concurrent.futures
import json
import threading
from stage_d2_cloud import call,CloudFailure
from stage_d5_protocol import OUT,MODELS,KINDS,RUBRIC,budget,read,save,sha,teacher_role,transient_error,bounded_call

def judge(model,rows,rubric=RUBRIC):
    budget(100)
    data=[{'id':i,'source_type':r['source_type'],'fragment':r['raw_text']} for i,r in enumerate(rows)]
    # GLM needs room to finish a batch and rejects the thinking field (HTTP 400), so it is omitted for GLM.
    thinking=None if model=='glm-5.3-flash' else False
    result,_=bounded_call(call,model,[{'role':'system','content':rubric},{'role':'user','content':json.dumps(data,ensure_ascii=False)}],max_tokens=8000,thinking=thinking,log_path=OUT/'cloud-requests.jsonl')
    items=result.get('items',[]) if isinstance(result,dict) else []
    if len(items)!=len(rows) or {v.get('id') for v in items}!=set(range(len(rows))):raise CloudFailure('Teacher coverage schema')
    votes=[]
    for v in items:
        if KINDS.get(v.get('kind'))!=v.get('label'):raise CloudFailure('Teacher label kind schema: '+json.dumps({k:str(v.get(k))[:60] for k in ('label','kind')}))
        votes.append({'id':rows[v['id']]['id'],'model':model,'label':v['label'],'kind':v['kind']})
    return votes

def review(name,rows,workers=12,resume=False,batch_size=8,teachers=None,finalize=True):
    output=OUT/(name+'-votes.jsonl');attempts=OUT/(name+'-attempts.jsonl')
    if (OUT/(name+'-review.json')).exists():raise ValueError('Completed cohort must not be repeated')
    if not resume and (output.exists() or attempts.exists()):raise ValueError('Do not silently rerun teacher cohort')
    output.touch(exist_ok=resume)
    errors_path=OUT/(name+'-errors.json');errors=json.loads(errors_path.read_text()) if resume and errors_path.exists() else []
    prior={(v['id'],teacher_role(v['model'])) for v in read(output)}
    recovered_path=OUT/'route-recoverable-failures.json'
    recovered={(r['id'],teacher_role(r['model'])) for r in json.loads(recovered_path.read_text())['pairs']} if recovered_path.exists() else set()
    excluded={(i,teacher_role(e['model'])) for e in errors for i in e['ids'] if not transient_error(e.get('reason','')) and not (e.get('reason')=='HTTP status 403' and (i,teacher_role(e['model'])) in recovered)}
    reserved=prior|excluded;order={r['id']:i for i,r in enumerate(rows)}
    stop=threading.Event();streak={m:0 for m in MODELS};batches=[]
    selected=MODELS if teachers is None else tuple(teachers)
    if not selected or any(m not in MODELS for m in selected):raise ValueError('Unknown teacher role')
    if finalize and selected!=MODELS:raise ValueError('A partial teacher pass cannot finalize a cohort')
    for model in selected:
        pending=[r for r in rows if (r['id'],model) not in reserved]
        batches.extend((model,pending[i:i+batch_size]) for i in range(0,len(pending),batch_size))
    # Interleave models without changing which samples are eligible.
    batches.sort(key=lambda pair:(order[pair[1][0]['id']],MODELS.index(pair[0])))
    if resume:save(name+'-resume.json',{'retained_votes':len(prior),'excluded_failed_pairs':len(excluded),'pending_pairs':sum(len(b) for m,b in batches),'known_valid_votes_repeated':0,'ambiguous_inflight_without_persisted_votes_may_be_resubmitted':True})
    def job(model,batch):
        if stop.is_set():return []
        return judge(model,batch)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs={pool.submit(job,m,b):(m,[r['id'] for r in b]) for m,b in batches}
        with output.open('a',encoding='utf-8') as stream,attempts.open('a',encoding='utf-8') as journal:
            for f in concurrent.futures.as_completed(jobs):
                model,ids=jobs[f]
                try:
                    votes=f.result()
                    for v in votes:stream.write(json.dumps(v,ensure_ascii=False)+'\n')
                    stream.flush();streak[model]=0
                    journal.write(json.dumps({'model':model,'ids':ids,'status':'completed' if votes else 'cancelled'})+'\n');journal.flush()
                except Exception as e:
                    reason=str(e) if isinstance(e,(CloudFailure,TimeoutError)) else type(e).__name__
                    errors.append({'model':model,'ids':ids,'error_type':type(e).__name__,'reason':reason})
                    journal.write(json.dumps(errors[-1])+'\n');journal.flush();save(name+'-errors.json',errors)
                    invalid=isinstance(e,CloudFailure) and any(x in reason.lower() for x in ('schema','incomplete','jsondecodeerror'))
                    transient=isinstance(e,CloudFailure) and transient_error(reason)
                    if transient:streak[model]+=1
                    if not invalid and not transient:
                        stop.set()
                        for pending in jobs:pending.cancel()
                        raise
    if not finalize:
        progress={'persisted_votes':len(read(output)),'cohort_finalized':False,'teacher_roles':list(selected)}
        save(name+'-progress.json',progress);print(json.dumps(progress),flush=True);return None,progress
    votes=read(output);by={(v['id'],teacher_role(v['model'])):v for v in votes};agreed=[];full=0;kind_disagree=0
    for r in rows:
        if any((r['id'],m) not in by for m in MODELS):continue
        a,b=[by[(r['id'],m)] for m in MODELS];full+=1
        if a['label']!=b['label']:continue
        kind=a['kind'] if a['kind']==b['kind'] else 'mixed_none'
        kind_disagree+=a['kind']!=b['kind']
        agreed.append({**r,'label':a['label'],'kind':kind,'teacher_kinds':[a['kind'],b['kind']]})
    result={'n':len(rows),'fully_reviewed':full,'agreement_n':len(agreed),'agreement_rate':len(agreed)/len(rows) if rows else 0,'agreement_rate_valid':len(agreed)/full if full else 0,'missing_n':len(rows)-full,'kind_disagreements':kind_disagree,'kind':dict(collections.Counter(r['kind'] for r in agreed)),'labels':dict(collections.Counter(r['label'] for r in agreed)),'prompt_sha256':__import__('hashlib').sha256(RUBRIC.encode()).hexdigest(),'errors_n':len(errors)}
    save(name+'-review.json',result)
    with (OUT/(name+'-agreed.jsonl')).open('x',encoding='utf-8') as f:
        for r in agreed:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(json.dumps({'cohort':name,**result}),flush=True);return agreed,result

if __name__=='__main__':
    import sys
    name=sys.argv[1]
    if name!='pilot' and not json.loads((OUT/'pilot-review.json').read_text()).get('agreement_rate',0)>=.85:raise ValueError('Pilot gate failed')
    review(name,read(OUT/(name+'.jsonl')))
