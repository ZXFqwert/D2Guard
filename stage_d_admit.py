"""Admit consensus data only after a recorded human dispute disposition."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
from stage_d_data import ROOT,LABELS,LANGS,read_jsonl,write_jsonl,surfaces,sha,frozen_evaluation,leakage_check
from stage_d_review import review,apply_adjudications
from train_stage_d import validate_support


def balance_surfaces(rows):
    groups=collections.defaultdict(list);retained=[];excluded=[]
    for row in rows:
        features=tuple(sorted(surfaces(row['text'])))
        if not features:retained.append(row)
        else:groups[(row['split'],features)].append(row)
    for group in groups.values():
        by_label={label:[r for r in group if r['label']==label] for label in LABELS}
        count=min(map(len,by_label.values()))
        for label,items in by_label.items():
            ordered=sorted(items,key=lambda r:sha('stage-d-balance-20261017:'+r['id']))
            retained.extend(ordered[:count]);excluded.extend(ordered[count:])
    return sorted(retained,key=lambda r:r['id']),excluded


def admit(a):
    policy=json.loads(a.policy.read_text(encoding='utf8'))
    delegated=policy.get('disagreement_policy')=='user_delegated_adjudication'
    if not delegated and (policy.get('disagreement_policy')!='exclude' or policy.get('reviewer')!='human_user' or not policy.get('source')):
        raise ValueError('A recorded human dispute disposition or delegated adjudication is required')
    provenance=json.loads(a.provenance.read_text(encoding='utf8'))
    rows=read_jsonl(a.data);annotations=read_jsonl(a.annotations)
    agreed,disputes,summary=review(rows,annotations,a.models)
    expected=hashlib.sha256(a.data.read_bytes()).hexdigest()
    adjudicated_exclusions=[]
    if delegated:
        admitted_candidates,adjudicated_exclusions=apply_adjudications(rows,disputes,policy,expected)
    else:admitted_candidates=agreed
    budget_drops=[]
    if getattr(a,'token_budget',None):
        budget=json.loads(a.token_budget.read_text(encoding='utf8'))
        if budget.get('candidate_sha256')!=expected or not budget.get('tokenizer_sha256'):
            raise ValueError('Token budget audit does not match the corpus/tokenizer')
        eligible=set(budget['eligible_ids'])
        budget_drops=[r['id'] for r in admitted_candidates if r['id'] not in eligible]
        admitted_candidates=[r for r in admitted_candidates if r['id'] in eligible]
    balanced,balance_drops=balance_surfaces(admitted_candidates)
    frozen,gold,files=frozen_evaluation();leak=leakage_check(balanced,frozen,files)
    errors=[]
    try:validate_support(balanced)
    except ValueError as exc:errors.append(str(exc))
    for split in ('train','validation','heldout'):
        for label in LABELS:
            languages={r['language'] for r in balanced if r['split']==split and r['label']==label}
            if languages!=set(LANGS):errors.append(f'Missing language/class support: {split}/{label}: '+','.join(sorted(set(LANGS)-languages)))
    family_review=provenance.get('reviewed') is True and provenance.get('candidate_sha256')==expected
    if not family_review:errors.append('Current corpus family provenance has not been reviewed')
    if not leak['passed']:errors.append('Final leakage/balance check failed')
    write_jsonl(Path(str(a.output)+'.disputes.jsonl'),disputes)
    write_jsonl(Path(str(a.output)+'.candidate-consensus.jsonl'),balanced)
    result={**leak,'passed':not errors,'admission_errors':errors,
        'candidate_rows':len(rows),'three_way_agreement_rows':len(agreed),'original_disputed_rows':len(disputes),
        'disputed_rows_excluded':sum(r['id'] in {x['id'] for x in disputes} for r in adjudicated_exclusions) if delegated else len(disputes),
        'adjudicated_rows':len(rows) if delegated else 0,'adjudicated_exclusions':adjudicated_exclusions,
        'token_budget_excluded_ids':budget_drops,
        'surface_balance_rows_excluded':len(balance_drops),'surface_balance_excluded_ids':[r['id'] for r in balance_drops],
        'candidate_sha256':expected,'teacher_actual_models':list(summary['actual_teachers'].values()),
        'family_provenance_reviewed':family_review,'annotation_review_completed':True,
        'unresolved_rows_in_admitted':0,'dispute_policy':policy,'approved_input_sha256':None,
        'admitted_rows':len(balanced) if not errors else 0}
    if not errors:
        data=Path(str(a.output)+'.approved.jsonl')
        if data.exists():raise ValueError('Never overwrite an admitted dataset')
        write_jsonl(data,balanced);result['approved_input_sha256']=hashlib.sha256(data.read_bytes()).hexdigest()
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ('passed','candidate_rows','three_way_agreement_rows','disputed_rows_excluded','surface_balance_rows_excluded','admitted_rows','admission_errors')},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('data','annotations','policy','provenance','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--token-budget',type=Path)
    p.add_argument('--models',nargs='+',required=True);admit(p.parse_args())
