"""One semantic view and recall-constrained validation-only calibration."""
import json
import time
import numpy as np
from stage_d2_model import QUESTION, softmax
from stage_d2_metrics import LABELS, metrics
from d2v2.semantic_view import semantic_view


def input_text(row):
    if 'raw_text' not in row:
        raise ValueError('D3 requires the recovered original raw_text')
    return semantic_view(row['raw_text'])


def views_for(tok,row):
    from d2v2.content_model import windows
    return windows(tok,input_text(row),row['source_type'],view_budget=384)


def items_for(tok,rows):
    from laya.train import items_from_rows
    from laya.common import build_sequence
    items=[];mapping=[]
    for row in rows:
        views=views_for(tok,row)
        new,skipped=items_from_rows(tok,[{'state':v,'questions':{'S1':QUESTION},'expected':{'S1':'ABC'[LABELS.index(row['label'])]}} for v in views],512,192)
        if skipped or len(new)!=len(views):raise ValueError('S1 item conversion skipped')
        for item in new:
            if build_sequence(tok,{},item['q'],512,192,state_ids=item['state_ids'],return_truncation_stats=True)[-1]['truncated']:
                raise ValueError('S1 view truncated')
        mapping.append((len(items),len(items)+len(new)));items+=new
    return items,mapping


def predict_laya(model,tok,rows,device):
    from laya.train import calibration_records
    start=time.monotonic();items,mapping=items_for(tok,rows)
    records=calibration_records(model,tok,items,device,512,192,batch_size=16)
    wp=softmax(np.array([r[1] for r in records]))
    z=np.array([np.log(np.maximum(wp[a:b].mean(0),1e-12)) for a,b in mapping])
    return z,(time.monotonic()-start)*1000/len(rows),[b-a for a,b in mapping]


def baseline_text(row):
    return json.dumps({'source_type':row['source_type'],'fragment':input_text(row)},ensure_ascii=False)


def predict_baseline(model,tok,rows,device):
    import torch
    start=time.monotonic();texts=[];mapping=[]
    for row in rows:
        views=views_for(tok,row);a=len(texts)
        texts.extend(json.dumps(v,ensure_ascii=False) for v in views);mapping.append((a,len(texts)))
    vectors=[];model.eval()
    for i in range(0,len(texts),16):
        batch=tok(texts[i:i+16],padding=True,truncation=False,return_tensors='pt').to(device)
        if batch['input_ids'].shape[1]>512:raise ValueError('Baseline sequence exceeds budget')
        with torch.inference_mode():z=model(**batch).logits.float().cpu().numpy()
        vectors.append(z)
    wp=softmax(np.concatenate(vectors));z=np.array([np.log(np.maximum(wp[a:b].mean(0),1e-12)) for a,b in mapping])
    return z,(time.monotonic()-start)*1000/len(rows),[b-a for a,b in mapping]


def threshold_for(rows,ps):
    truth=np.array([r['label']=='request' for r in rows]);none=np.array([r['label']=='none' for r in rows])
    if not truth.any() or not none.any():raise ValueError('Validation must contain request and none')
    feasible=[]
    for threshold in sorted(set([0.,1.,*map(float,ps[:,0])])):
        pred=ps[:,0]>=threshold;tp=int((pred&truth).sum());fp=int((pred&~truth).sum())
        precision=tp/(tp+fp) if tp+fp else 0.;recall=tp/truth.sum()
        fpr=float((pred&none).sum()/none.sum())
        if precision>=.90 and fpr<=.02:feasible.append((float(recall),threshold))
    if not feasible:return None,None
    _,threshold=max(feasible)
    return float(threshold),metrics(rows,ps,threshold)


def calibrate(rows,z):
    from laya.calibrate import fit_one_temperature
    targets=[[float(label==r['label']) for label in LABELS] for r in rows]
    temperature=fit_one_temperature(list(zip(z,targets)),min_n=900)
    ps=softmax(z/temperature);threshold,result=threshold_for(rows,ps)
    return float(temperature),threshold,result


def nll(rows,ps):
    y=np.array([LABELS.index(r['label']) for r in rows])
    return float(-np.log(np.maximum(ps[np.arange(len(rows)),y],1e-12)).mean())


def route_base(text):
    """Fixed script heuristic from semantic text; no oracle language metadata."""
    chars=[c for c in semantic_view(text) if c.isalpha()]
    nonlatin=sum(0x0400<=ord(c)<=0x052F or 0x3040<=ord(c)<=0x30FF or
                 0x3400<=ord(c)<=0x9FFF for c in chars)
    return 'multilingual' if chars and nonlatin/len(chars)>=.15 else 'english'


def ensemble(rows,probabilities):
    # Routing and averaging fixed before any new validation predictions.
    return np.asarray([(probabilities[route_base(r['raw_text'])][i]+
                        probabilities['modernbert'][i])/2 for i,r in enumerate(rows)])


def select_candidate(candidates):
    eligible=[(name,r) for name,r in candidates.items() if r['threshold'] is not None and r['posttrain_probe_passed']]
    if not eligible:return None
    return max(eligible,key=lambda pair:(pair[1]['validation']['request']['recall'],
        pair[1]['validation']['request']['f1'],-pair[1]['validation_nll']))[0]
