"""User-authorized GLM recovery with an early per-contract agreement gate."""
import collections
import hashlib
import json
import time
from stage_d5_protocol import OUT, MODELS, RUBRIC, read, save, teacher_role, active_rows
from stage_d5_teacher import review

QUEUES=('injected-quoted','injected-extra','injected','synthetic-request')

def agreement(name, rows, second='glm-5.3-flash'):
    by={(v['id'],teacher_role(v['model'])):v for v in read(OUT/(name+'-votes.jsonl'))}
    result={}
    for label in ('request','quoted','none'):
        subset=[r for r in rows if r.get('contract_label',r['label'])==label]
        complete=0;matched=0;pairs=collections.Counter()
        for r in subset:
            a=by.get((r['id'],MODELS[0]));b=by.get((r['id'],second))
            if a is None or b is None:continue
            complete+=1;pairs[a['label']+':'+b['label']]+=1
            matched+=a['label']==b['label']==label
        result[label]={'n':len(subset),'paired_n':complete,'three_way_n':matched,
                       'rate':matched/complete if complete else None,'teacher_pairs':dict(pairs)}
    return result

def gate_agreement(name, rows, second='glm-5.3-flash'):
    if name!='synthetic-request':return agreement(name,rows,second)
    # Latest D5 explicitly permits relabeling legacy request rows to none.
    # Historical generation contracts are provenance, not the new-definition truth.
    by={(v['id'],teacher_role(v['model'])):v for v in read(OUT/(name+'-votes.jsonl'))}
    result={}
    for label in ('request','quoted','none'):
        subset=[r for r in rows if by.get((r['id'],MODELS[0]),{}).get('label')==label]
        complete=0;matched=0;pairs=collections.Counter()
        for r in subset:
            a=by[(r['id'],MODELS[0])];b=by.get((r['id'],second))
            if b is None:continue
            complete+=1;pairs[a['label']+':'+b['label']]+=1;matched+=a['label']==b['label']
        result[label]={'n':len(subset),'paired_n':complete,'teacher_agreement_n':matched,
                       'rate':matched/complete if complete else None,'teacher_pairs':dict(pairs),
                       'basis':'new-definition dual agreement; old contract retained only as provenance'}
    return result

def early_rows(name,rows):
    by={(v['id'],teacher_role(v['model'])):v for v in read(OUT/(name+'-votes.jsonl'))}
    # Never inspect test examples to make an early continuation decision.
    available=[r for r in rows if r.get('split')=='train' and (r['id'],MODELS[0]) in by]
    groups={label:sorted([r for r in available if (by[(r['id'],MODELS[0])]['label'] if name=='synthetic-request' else r.get('contract_label',r['label']))==label],
        key=lambda r:hashlib.sha256(('glm-early-v1:'+r['id']).encode()).hexdigest())
        for label in ('request','quoted','none')}
    selected=[]
    while len(selected)<200 and any(groups.values()):
        for label in groups:
            if groups[label] and len(selected)<200:selected.append(groups[label].pop(0))
    return selected

def main():
    assert hashlib.sha256(RUBRIC.encode()).hexdigest()=='475571e4a12e528f8aaeba4e52b6f8481f49696e90fdcf02a7946e21a0a2e91f'
    allrows={name:active_rows(name,read(OUT/(name+'.jsonl'))) for name in QUEUES}
    before={name:agreement(name,rows,'mimo-v2.5') for name,rows in allrows.items()}
    save('glm-before-agreement.json',before)
    gates=json.loads((OUT/'glm-early-gates.json').read_text()) if (OUT/'glm-early-gates.json').exists() else {}
    for name,rows in allrows.items():
        if name!='synthetic-request' and gates.get(name,{}).get('passed'):continue
        sample=early_rows(name,rows)
        if not sample:raise ValueError('No training-side early-check rows')
        save(name+'-glm-early-sample.json',{'ids':[r['id'] for r in sample],'selection':'SHA256 within classes, training only; new contracts for injected, retained new-definition DeepSeek labels for legacy synthetic; no selection on GLM outcomes'})
        review(name,sample,resume=True,teachers=('glm-5.3-flash',),finalize=False,workers=8,batch_size=8)
        counts=gate_agreement(name,sample)
        enough=all(v['paired_n']>0 for v in counts.values() if v['n'])
        passed=enough and all(v['rate'] is not None and v['rate']>=.70 for v in counts.values() if v['n'])
        gates[name]={'passed':passed,'counts':counts,'coverage_passed':enough,'policy':'D5-latest-labels-v2'}
        save('glm-early-gates.json',gates);print(json.dumps({'queue':name,**gates[name]}),flush=True)
        if not passed:
            save('stage-stop.json',{'error_type':'TeacherEarlyAgreementGate','reason':'User-registered early per-contract agreement <70% or no paired observations for a present class','queue':name,'stopped_unix':time.time(),'training_clock_started':False,'gate':gates[name]})
            return
    for name,rows in allrows.items():
        review(name,rows,resume=True,teachers=('glm-5.3-flash',),finalize=False,workers=8,batch_size=8)
    for name,rows in allrows.items():
        review(name,rows,resume=True,teachers=None,finalize=True,workers=8,batch_size=8)
    save('glm-after-agreement.json',{name:agreement(name,rows) for name,rows in allrows.items()})

if __name__=='__main__':main()
