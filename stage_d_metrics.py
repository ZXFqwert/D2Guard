"""Fixed four-class metrics; no fitting or threshold selection on evaluation."""
import math
from stage_d_data import LABELS


def metrics(rows):
    confusion=[[0]*4 for _ in LABELS];bins=[[] for _ in range(10)]
    for row in rows:
        probs=[row['probabilities'][k] for k in LABELS]
        if any(not math.isfinite(p) or p<0 or p>1 for p in probs) or abs(sum(probs)-1)>.01:
            raise ValueError('Invalid evaluation probabilities')
        truth=LABELS.index(row['label']);pred=max(range(4),key=lambda i:probs[i])
        confusion[truth][pred]+=1;confidence=probs[pred]
        bins[min(9,int(confidence*10))].append((confidence,int(truth==pred)))
    f1s=[];classes={}
    for i,label in enumerate(LABELS):
        tp=confusion[i][i];support=sum(confusion[i]);predicted=sum(r[i] for r in confusion)
        f1=2*tp/(support+predicted) if support+predicted else 0.0
        f1s.append(f1);classes[label]={'support':support,'predicted':predicted,'f1':f1}
    n=len(rows)
    return {'n':n,'accuracy':sum(confusion[i][i] for i in range(4))/n if n else None,
        'macro_f1_fixed_four_classes':sum(f1s)/4 if n else None,
        'ece_10_equal_width_bins':sum(abs(sum(c for c,y in b)-sum(y for c,y in b)) for b in bins)/n if n else None,
        'classes':classes,'confusion_matrix':confusion,'class_order':list(LABELS)}


def stratified_metrics(rows):
    return {'overall':metrics(rows),'languages':{lang:metrics([r for r in rows if r['language']==lang])
            for lang in sorted({r['language'] for r in rows})}}
