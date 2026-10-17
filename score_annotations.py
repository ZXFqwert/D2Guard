"""Cohen's kappa and E1 against human-provided gold; never infer gold labels."""
import argparse
from collections import Counter
import json
from pathlib import Path


def read(path):
    result={}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        r=json.loads(line);key=(r['item_id'],r['variant'])
        if key in result:raise ValueError('Duplicate item/variant annotation')
        if r.get('label') not in {None,'ALLOW','ASK','BLOCK','to_agent','task_data','unclear','for_reader','quoted','data'}:raise ValueError('Unknown label')
        result[key]=r
    return result


def agreement(pairs):
    n=len(pairs)
    if not n:return {'n':0,'agreement':None,'cohen_kappa':None,'undefined_reason':'no_complete_pairs'}
    left=Counter(a for a,b in pairs);right=Counter(b for a,b in pairs)
    po=sum(a==b for a,b in pairs)/n;pe=sum(left[x]*right[x] for x in left)/n**2
    return {'n':n,'agreement':po,'cohen_kappa':(po-pe)/(1-pe) if pe<1 else None,
            'undefined_reason':'constant_marginals' if pe==1 else None}


def compare(a,b,variant,other_variant=None):
    other_variant=other_variant or variant
    ids={i for i,v in a if v==variant}|{i for i,v in b if v==other_variant}
    pairs=[];missing=[];diff=[]
    for i in sorted(ids):
        x=a.get((i,variant));y=b.get((i,other_variant))
        if not x or not y or x.get('label') is None or y.get('label') is None:missing.append(i);continue
        pairs.append((x['label'],y['label']))
        if x['label']!=y['label']:
            diff.append({'item_id':i,'left':x['label'],'right':y['label'],
                         'reason':x.get('reason') or y.get('reason') or 'unclassified',
                         'left_note':x.get('note'),'right_note':y.get('note')})
    return {**agreement(pairs),'missing_items':missing,'disagreements':diff,
            'disagreements_by_reason':dict(Counter(d['reason'] for d in diff))}


def score(a,b,gold=None,state_raters=None):
    result={'evaluation_only':True,'gold_generated':False,'E0':{v:compare(a,b,v) for v in ('full','fragment')},'E1':None}
    if gold is not None:
        result['E1']={name:compare(rater,gold,'state','gold') for name,rater in (state_raters if state_raters is not None else {'rater_a':a,'rater_b':b}).items()}
        for value in result['E1'].values():value['meets_95_percent_observed']=None if value['agreement'] is None else value['agreement']>=.95
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('rater_a',type=Path);p.add_argument('rater_b',type=Path);p.add_argument('--gold',type=Path);p.add_argument('--output',type=Path);p.add_argument('--state-raters',type=Path,nargs='+')
    a=p.parse_args();result=score(read(a.rater_a),read(a.rater_b),read(a.gold) if a.gold else None,{str(p):read(p) for p in a.state_raters} if a.state_raters else None)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.output:a.output.write_text(text,encoding='utf-8')
    print(text)
