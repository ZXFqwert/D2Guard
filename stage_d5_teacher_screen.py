"""D5 replacement-teacher screen on the reviewer-checked 72-row diag set (frozen v1 rubric).

Candidates are added to the evaluation-only allowlist at runtime only; stage_d2_cloud.py is
unchanged. Returned model names must equal the requested /models id; mismatches are reported as errors.
Logs keep model, seconds, tokens only.
"""
import collections
import concurrent.futures
import hashlib
import json
import sys
import time
import stage_d2_cloud as c
from stage_d5_teacher_diag import DIAG,LOG,load_set,judge,RUBRIC

CANDIDATES=('glm-5.3-flash','mimo-v2.6-flash','qwen3.8-max','glm-5.3','kimi-k3')
BATCHES=((8,2400),(1,600))

def screen(names,workers=8):
    c.EVALUATION_ONLY_MODELS=c.EVALUATION_ONLY_MODELS+tuple(n for n in names if n not in c.EVALUATION_ONLY_MODELS)
    for n in names:c.RETURNED_NAMES[n]={n}  # exact /models id; a differing returned name fails and is reported
    identity=DIAG/'returned-models.json'
    before=json.loads(identity.read_text(encoding='utf-8')) if identity.exists() else {}
    rows=load_set();order=sorted(rows,key=lambda r:hashlib.md5(r['id'].encode()).hexdigest())
    jobs=[(f'{m}_v1_b{b}',m,order[i:i+b],mt) for m in names for b,mt in BATCHES for i in range(0,len(order),b)]
    votes=collections.defaultdict(dict);errors=collections.Counter();mismatch=collections.Counter();seconds=collections.defaultdict(list)
    def timed(m,batch,mt):
        t=time.monotonic();out=judge(m,batch,RUBRIC,None,mt);return out,time.monotonic()-t
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        fs={pool.submit(timed,m,batch,mt):v for v,m,batch,mt in jobs}
        for f in concurrent.futures.as_completed(fs):
            v=fs[f]
            try:out,s=f.result();votes[v].update(out);seconds[v].append(s)
            except Exception as e:errors[v]+=1;mismatch[v]+='Returned model name differs' in str(e);print(v,'error',str(e)[:120],flush=True)
    after=json.loads(identity.read_text(encoding='utf-8')) if identity.exists() else {}
    gold={r['id']:r['gold'] for r in rows};report={}
    for v,m,_,_ in dict.fromkeys((j[0],j[1],None,None) for j in jobs):
        got=votes[v];per={}
        for k in ('request','quoted','none'):
            ids=[i for i,g in gold.items() if g==k];cnt=collections.Counter(got.get(i,'missing') for i in ids)
            per[k]={'correct':cnt[k],'n':len(ids),'missing':cnt['missing'],'pred':dict(cnt)}
        returned={r:n-before.get(m,{}).get(r,0) for r,n in after.get(m,{}).items() if n-before.get(m,{}).get(r,0)>0}
        report[v]={'model':m,'accuracy':sum(got.get(i)==g for i,g in gold.items())/len(gold),'per_class':per,
                   'errors':errors[v],'name_mismatch_errors':mismatch[v],'mean_seconds':sum(seconds[v])/len(seconds[v]) if seconds[v] else None,
                   'returned_names_for_model':returned}
    (DIAG/'screen-votes.json').write_text(json.dumps(votes,ensure_ascii=False,indent=1),encoding='utf-8')
    (DIAG/'screen-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    screen(tuple(sys.argv[1:]) or CANDIDATES)
