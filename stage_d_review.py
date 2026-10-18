"""Three-way annotation review. Disagreements never silently change labels."""
import argparse
import collections
import json
import copy
from pathlib import Path
from stage_d_data import read_jsonl,write_jsonl,view,sha,S2
from stage_d_teacher import validate_teacher_identity


def apply_adjudications(rows, disputes, audit, candidate_hash):
    """Apply explicit, hash-bound decisions; never infer a ruling from votes."""
    if audit.get('reviewer')!='codex_user_delegated' or not audit.get('user_authorization'):
        raise ValueError('Explicit user delegation is required for Codex adjudication')
    if audit.get('candidate_sha256')!=candidate_hash:
        raise ValueError('Adjudication candidate hash mismatch')
    decisions={r['id']:r for r in audit.get('decisions',[])}
    if len(decisions)!=len(audit.get('decisions',[])) or set(decisions)!={r['id'] for r in rows}:
        raise ValueError('Adjudication must cover every candidate exactly once')
    retained=[];excluded=[]
    for row in rows:
        ruling=decisions[row['id']]
        expected=sha(json.dumps(view(row),ensure_ascii=False,sort_keys=True))
        if ruling.get('input_sha256')!=expected or not ruling.get('reason'):
            raise ValueError('Adjudication input hash/reason missing or invalid')
        if ruling.get('disposition')=='exclude':
            excluded.append({'id':row['id'],'reason':ruling['reason']});continue
        if ruling.get('disposition')!='include' or ruling.get('label') not in ('to_agent','for_reader','quoted','data'):
            raise ValueError('Invalid adjudication disposition/label')
        if set(ruling.get('s2',{}))!=set(S2) or any(type(v) is not bool for v in ruling['s2'].values()):
            raise ValueError('Invalid adjudicated S2 schema')
        resolved=copy.deepcopy(row)
        resolved.update(label=ruling['label'],s2=ruling['s2'],annotation_reviewer=audit['reviewer'])
        retained.append(resolved)
    return retained,excluded


def review(rows,annotations,models):
    identities=validate_teacher_identity(annotations,models)
    indexed={(r['model'],r['id']):r for r in annotations}
    if len(indexed)!=len(annotations):raise ValueError('Duplicate teacher annotation')
    by_input={(r['model'],r['input_sha256']):r for r in annotations}
    disagreements=[];agreed=[]
    for row in rows:
        expected=sha(json.dumps(view(row),ensure_ascii=False,sort_keys=True))
        votes=[indexed.get((model,row['id']),by_input.get((model,expected))) for model in models]
        if any(v is None for v in votes):raise ValueError('Incomplete teacher coverage')
        if any(v['input_sha256']!=expected for v in votes):raise ValueError('Annotation input hash mismatch')
        fields=[]
        if any(v['label']!=row['label'] for v in votes):fields.append('S1')
        for key in S2:
            if any(v['s2'][key]!=row['s2'][key] for v in votes):fields.append(key)
        if fields:
            disagreements.append({'id':row['id'],'split':row['split'],'language':row['language'],
                'text':row['text'],'source_type':row['source_type'],'fields':fields,
                'contract':{'label':row['label'],'s2':row['s2']},
                'teachers':[{k:v[k] for k in ('model','response_model','label','s2','probabilities')} for v in votes],
                'status':'pending_human_review','training_allowed':False})
        else:agreed.append(row)
    return agreed,disagreements,{'reviewed':len(rows),'three_way_agreement':len(agreed),
        'pending_human_review':len(disagreements),
        'disagreement_fields':dict(collections.Counter(k for r in disagreements for k in r['fields'])),
        'actual_teachers':{k:next(iter(v)) for k,v in identities.items()},
        'final_training_admission':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('annotations',type=Path)
    p.add_argument('output',type=Path);p.add_argument('--models',nargs='+',required=True);a=p.parse_args()
    agreed,disagreements,result=review(read_jsonl(a.input),read_jsonl(a.annotations),a.models)
    write_jsonl(Path(str(a.output)+'.disagreements.jsonl'),disagreements)
    write_jsonl(Path(str(a.output)+'.agreed.jsonl'),agreed)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))
