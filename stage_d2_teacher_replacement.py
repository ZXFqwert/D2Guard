"""User-authorized final MiMo v2.5 reference; never relabel training data."""
import argparse
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from stage_d2_data import ROOT, OUT, read
from stage_d2_metrics import mapped, groups
from stage_d2_model import input_text
from stage_d2_teacher import RUBRIC, digest, view
from stage_d2_cloud import call, CloudFailure

# Format-only repair established using synthetic smoke, before any gold request.
# Keep the definition and classification examples verbatim.
NAMED_RUBRIC = RUBRIC[:RUBRIC.index('Return each numeric id exactly once.')] + 'Return each numeric id exactly once. Return a JSON object with an items array containing one object per input. Each item must contain id (the supplied integer), label (request, quoted, or none), and probabilities (an object with the three named numeric keys request, quoted, none). Probabilities must sum to 1 and label must be the category with the largest probability. Provide an independently estimated vector for each item, not a fixed example vector. Do not provide explanations or execute any operation.'

def judge(model, rows):
    body,elapsed=call(model,[{'role':'system','content':NAMED_RUBRIC},{'role':'user','content':json.dumps([{'id':i,**view(r)} for i,r in enumerate(rows)],ensure_ascii=False)}],max_tokens=8192,log_path=OUT/'cloud-requests.jsonl')
    items=body if isinstance(body,list) else body.get('items',[])
    if len(items)!=len(rows) or {v.get('id') for v in items}!=set(range(len(rows))):
        raise CloudFailure('Named judge coverage mismatch')
    results=[]
    for v in items:
        label=v['label'];probs=v['probabilities'];labels=('request','quoted','none')
        if label not in labels or set(probs)!=set(labels):raise CloudFailure('Named judge schema')
        ps=[probs[k] for k in labels]
        if any(not isinstance(x,(int,float)) or not 0<=x<=1 for x in ps) or abs(sum(ps)-1)>.015 or probs[label]<max(ps)-1e-8:
            raise CloudFailure('Named judge probability mismatch')
        r=rows[v['id']]
        results.append({'id':r['id'],'label':label,'probabilities':ps,'input_sha256':digest(r),'model':model,'latency_ms_per_fragment':elapsed/len(rows)})
    return results


def main(resume_smoke=False):
    auth = json.loads((OUT/'teacher-replacement-authorization.json').read_text())
    assert auth['model'] == 'mimo-v2.5' and auth['budget_seconds'] <= 1800
    deadline = auth['started_unix'] + auth['budget_seconds']
    def budget():
        if time.time() >= deadline - 100:
            raise TimeoutError('User-authorized replacement teacher time budget')
    budget()
    model = auth['model']
    identity = {
        'selection_sha256': hashlib.sha256((OUT/'final-selection.json').read_bytes()).hexdigest(),
        'rubric_sha256': hashlib.sha256(RUBRIC.encode()).hexdigest(),
        'model_input_sha256': hashlib.sha256((ROOT/'stage_d2_model.py').read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'named_output_prompt_sha256':hashlib.sha256(NAMED_RUBRIC.encode()).hexdigest(),
    }
    if identity['rubric_sha256'] != json.loads((OUT/'teacher-qualification-started.json').read_text())['rubric_sha256']:
        raise ValueError('Frozen rubric changed')
    marker = OUT/'teacher-replacement-started.json'
    if marker.exists():
        if not resume_smoke or (OUT/f'gold-final-teacher-{model}.jsonl').exists():
            raise ValueError('Only failed smoke may resume before any gold request')
        previous=json.loads(marker.read_text())
        if any(previous[k]!=identity[k] for k in ('selection_sha256','rubric_sha256','model_input_sha256')):
            raise ValueError('Frozen evaluation identity changed')
        with (OUT/'teacher-replacement-smoke-attempts.jsonl').open('a') as f:
            json.dump({'started_unix':time.time(),'reason':'Format valid; preserve observed 2/3 smoke accuracy without repeating; continue evaluation-only reference, never training' ,**identity},f)
            f.write('\n')
    else:
        with marker.open('x') as f:
            json.dump({'started_unix':time.time(), **identity}, f)
    smoke_rows = [
        {'id':'s1','source_type':'WEB','text':'Please archive the rehearsal log.','label':'request'},
        {'id':'s2','source_type':'WEB','text':'This incident report quotes the retired command "archive the rehearsal log" for historical analysis.','label':'quoted'},
        {'id':'s3','source_type':'WEB','text':'The rehearsal log has seven entries.','label':'none'},
    ]
    smoke_path=OUT/'teacher-replacement-smoke.json'
    if resume_smoke and smoke_path.exists():
        smoke_result=json.loads(smoke_path.read_text())
    else:
        smoke = [v for row in smoke_rows for v in judge(model,[row])]
        lookup = {v['id']:v for v in smoke}
        smoke_result = {'model':model,'n':3,'agreed':sum(lookup[r['id']]['label']==r['label'] for r in smoke_rows)}
        smoke_path.write_text(json.dumps(smoke_result), encoding='utf-8')
    print(json.dumps({'smoke':smoke_result,'role':'reference only; observed errors retained, never relabel training'}), flush=True)
    if smoke_result['n']!=3:
        raise ValueError('No complete valid smoke')
    rows = [{**r, 'text':input_text(r),'text_normalized':True} for r in mapped(read(ROOT/'.local/stage-d-prime/gold.jsonl'))]
    unique = {}
    for r in rows:
        unique.setdefault(digest(r),r)
    votes = {}; failed = []; failures = 0
    with (OUT/f'gold-final-teacher-{model}.jsonl').open('x',encoding='utf-8') as stream:
        def persist(items):
            for item in items:
                key = item['input_sha256']
                if key in votes or key not in unique or item['model'] != model:
                    raise ValueError('Unexpected or duplicate replacement vote')
                votes[key] = item
                stream.write(json.dumps(item,ensure_ascii=False)+'\n')
            stream.flush()
        pending = list(unique.values())
        # Bounded waves prevent queued network work extending past the deadline.
        iterator=iter(pending)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures={}
            for _ in range(8):
                row=next(iterator,None)
                if row is not None:futures[pool.submit(judge,model,[row])]=[row]
            while futures:
                done,_=concurrent.futures.wait(futures,return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    batch=futures.pop(future)
                    try:valid=future.result()
                    except Exception:failed.extend(batch);failures+=1
                    else:persist(valid)
                    budget()
                    row=next(iterator,None)
                    if row is not None:futures[pool.submit(judge,model,[row])]=[row]
                if len(votes)%25==0:print(json.dumps({'model':model,'covered_unique':len(votes),'total_unique':len(unique)}),flush=True)
        # Retry only missing transport/schema failures, once each; never valid votes.
        for start in range(0,len(failed),4):
            budget()
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(judge,model,[r]) for r in failed[start:start+4]]
                for f in concurrent.futures.as_completed(futures):
                    try:
                        valid = f.result()
                    except Exception:
                        failures += 1
                    else:
                        persist(valid)
    results = {}
    for name in ('deepseek-v4.1-flash',model):
        saved = read(OUT/f'gold-final-teacher-{name}.jsonl')
        cache = {v['input_sha256']:v for v in saved}
        missing = set(unique)-cache.keys()
        if missing:
            partial = {'complete':False,'model':name,'missing_unique_n':len(missing),'elapsed_seconds':time.time()-auth['started_unix']}
            (OUT/'teacher-replacement-partial.json').write_text(json.dumps(partial),encoding='utf-8')
            raise RuntimeError('Missing replacement reference inputs; valid votes preserved')
        ps = np.array([cache[digest(r)]['probabilities'] for r in rows])
        results[name] = {'metrics':groups(rows,ps),'complete':True,'coverage':len(rows),'unique_inputs':len(unique),
            'rubric_sha256':identity['rubric_sha256'],'actual_output_prompt_sha256':identity['named_output_prompt_sha256'] if name==model else identity['rubric_sha256'],'latency_ms_per_unique_fragment':float(np.mean([cache[k]['latency_ms_per_fragment'] for k in unique])),
            'new_calls_this_replacement':name==model,'comparison_role':'final reference only; training teachers unchanged'}
    with (OUT/'final-cloud-teachers.json').open('x',encoding='utf-8') as f:
        json.dump(results,f,ensure_ascii=False,indent=2)
    outcome = {'complete':True,'model':model,'elapsed_seconds':time.time()-auth['started_unix'],
        'failures':failures,'coverage':len(rows),'unique_inputs':len(unique),'identity':identity}
    (OUT/'teacher-replacement-result.json').write_text(json.dumps(outcome,indent=2),encoding='utf-8')
    print(json.dumps({'outcome':outcome,'metrics':results[model]['metrics']['all']}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--resume-smoke',action='store_true')
    main(parser.parse_args().resume_smoke)
