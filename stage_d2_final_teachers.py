"""Final normalized teacher comparison, unlocked only by final model selection."""
import argparse,concurrent.futures,hashlib,json,time
from pathlib import Path
import numpy as np
from stage_d2_data import ROOT,OUT,read
from stage_d2_teacher import MODELS,RUBRIC,judge,digest
from stage_d2_model import input_text
from stage_d2_metrics import mapped,groups


def main(resume_missing=False):
    lock=OUT/'final-selection.json';selection=json.loads(lock.read_text())
    round_number=selection['round_count'];deadline=json.loads((OUT/f'round-{round_number}/training-evaluation-clock.json').read_text())['started_unix']+5400
    if time.time()>=deadline:raise TimeoutError('Final evaluation budget exhausted')
    rubric_hash=hashlib.sha256(RUBRIC.encode()).hexdigest()
    if rubric_hash!=json.loads((OUT/'teacher-qualification-started.json').read_text())['rubric_sha256']:raise ValueError('Prompt changed; old qualification cannot be reused')
    marker=OUT/'gold-teachers-started.json'
    identity={'selection_sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),'rubric_sha256':rubric_hash,
              'model_input_source_sha256':hashlib.sha256((ROOT/'stage_d2_model.py').read_bytes()).hexdigest()}
    if marker.exists():
        if not resume_missing:raise ValueError('Final teacher evaluation already started; only explicit missing-input resume is allowed')
        previous=json.loads(marker.read_text())
        if any(previous.get(k)!=v for k,v in identity.items()):raise ValueError('Frozen teacher evaluation identity changed')
    else:
        if resume_missing:raise ValueError('No final teacher evaluation to resume')
        with marker.open('x') as f:json.dump({'started_unix':time.time(),**identity,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},f)
    rows=[{**r,'text':input_text(r),'text_normalized':True} for r in mapped(read(ROOT/'.local/stage-d-prime/gold.jsonl'))]
    unique={}
    for row in rows:unique.setdefault(digest(row),row)
    results={}
    for model in MODELS:
        votes=[]
        for prefix in ('qualification-','qualification-repair-','qualification-final-repair-','qualification-json-repair-'):
            votes+=read(OUT/(prefix+model+'.jsonl'))
        cache={r['input_sha256']:r for r in votes};diagnostic_keys=set(cache)
        target=OUT/('gold-final-teacher-'+model+'.jsonl')
        saved=read(target) if resume_missing else []
        if any(v['model']!=model or v['input_sha256'] not in unique for v in saved):raise ValueError('Unexpected saved final teacher vote')
        if len({v['input_sha256'] for v in saved})!=len(saved):raise ValueError('Duplicate final teacher votes')
        cache.update({v['input_sha256']:v for v in saved});persisted={v['input_sha256'] for v in saved}
        missing=[r for key,r in unique.items() if key not in cache];failed=[];failure_n=0
        with target.open('a' if resume_missing else 'x',encoding='utf-8') as stream:
            def persist(items):
                for vote in items:
                    key=vote['input_sha256']
                    if key not in unique or vote['model']!=model:raise ValueError('Teacher vote identity mismatch')
                    if key in persisted:raise ValueError('Never replace an already valid final teacher vote')
                    cache[key]=vote;persisted.add(key)
                    stream.write(json.dumps(vote,ensure_ascii=False)+'\n')
                stream.flush()
            persist([cache[k] for k in unique if k in cache and k not in persisted])
            if missing and time.time()>=deadline-100:raise TimeoutError('Insufficient final teacher request budget')
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures={pool.submit(judge,model,missing[i:i+8]):missing[i:i+8] for i in range(0,len(missing),8)}
                for future in concurrent.futures.as_completed(futures):
                    if time.time()>=deadline-100:
                        for pending in futures:pending.cancel()
                        raise TimeoutError('Final teacher evaluation budget')
                    try:valid=future.result()
                    except Exception:
                        failed+=futures[future];failure_n+=1
                    else:persist(valid)
            # Only schema/transport failures, never a previously valid answer.
            for row in failed:
                if time.time()>=deadline-100:raise TimeoutError('Final teacher evaluation budget')
                try:valid=judge(model,[row])
                except Exception:failure_n+=1
                else:persist(valid)
        uncovered=[k for k in unique if k not in cache]
        if uncovered:
            results[model]={'complete':False,'missing_unique_n':len(uncovered),'failure_n_this_attempt':failure_n}
            print(json.dumps({'teacher':model,'complete':False,'missing_unique_n':len(uncovered)}),flush=True)
            continue
        ps=np.array([cache[digest(r)]['probabilities'] for r in rows]);metrics=groups(rows,ps)
        results[model]={'metrics':metrics,'complete':True,'coverage':len(rows),'unique_inputs':len(unique),'new_normalized_inputs':sum(k not in diagnostic_keys for k in unique),
           'reused_exact_inputs':sum(k in diagnostic_keys for k in unique),'rubric_sha256':rubric_hash,'failure_n_this_attempt':failure_n,
           'latency_ms_per_unique_fragment':float(np.mean([cache[k]['latency_ms_per_fragment'] for k in unique]))}
        print(json.dumps({'teacher':model,'final_gold':metrics['all'],'new_inputs':len(missing)}),flush=True)
    if not all(v['complete'] for v in results.values()):
        (OUT/'final-teachers-partial.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        raise RuntimeError('Missing final teacher inputs; preserved valid votes must never be repeated')
    with (OUT/'final-cloud-teachers.json').open('x',encoding='utf-8') as f:json.dump(results,f,ensure_ascii=False,indent=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--resume-missing',action='store_true')
    main(parser.parse_args().resume_missing)
