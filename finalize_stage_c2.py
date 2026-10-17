"""Summarize retained real runs and export unlabeled evaluation packets."""
import argparse,hashlib,json,tarfile
from collections import Counter
from pathlib import Path
from analyze_stage_c import analyze
from export_stage_c import export
from select_stage_c2_sample import select
from verify_v2 import verify,rows

def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def finalize(root,suite,regression):
    report=analyze(root/'runs'/(suite+'.json'))
    selected=[r['run_id'] for s in report['scenarios'] for r in s['runs']+s['setup_runs']]
    checks={};exports=[]
    first=json.loads((root/'runs'/selected[0]/'manifest.json').read_text(encoding='utf-8'))
    profiles={name:{k:hashlib.sha256((base/k).read_bytes()).hexdigest() for k in first['source_sha256']} for name,base in [('c2-frozen-v4',root/'.local/stage-c2-runtime-v4'),('c2-readonly-v5',root)]}
    save(root/'docs/stage-c2-runtime-profiles.json',{'profiles':profiles,'note':'Final selection uses v4 except the entire read-only scenario is replaced by the fixed v5 two-repeat matrix. The only runtime difference is compression.py; recorded predicate equivalence is independently audited. No outcome-based selection.'})
    for rid in selected:
        folder=root/'runs'/rid;m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        matches=[name for name,values in profiles.items() if values==m['source_sha256']]
        checks[rid]={'recorded_runtime_sources_match':bool(matches),'runtime_profile':matches[0] if matches else None,
                     'current_runtime_sources_match':profiles['c2-readonly-v5']==m['source_sha256'],
                     'scenario_matches':hashlib.sha256((root/'scenarios'/(m['scenario']+'.json')).read_bytes()).hexdigest()==m['scenario_sha256'],
                     'source_count':len(m['source_sha256'])}
        exports.append(export([folder],root/'.local/stage-c2-exports'/rid))
    sample=export(select(root/'runs'/(suite+'.json')),root/'.local/stage-c2-annotation-sample')
    save(root/'docs/stage-c2-results.json',report)
    save(root/'docs/stage-c2-all-source-checks.json',checks)
    save(root/'docs/stage-c2-exports.json',{'evaluation_only':True,'gold_labels_created':False,'selection':'first repeat independent of outcomes; attack/off + attack clean/off + normal clean/off','per_run':exports,'sample':sample})
    batch=json.loads((root/'runs'/(regression+'.json')).read_text(encoding='utf-8'))
    regression_rows=[]
    for r in batch['results']:
        folder=root/'runs'/r['run_id'];m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        ds=[{k:d[k] for k in ('call_id','verdict','would_verdict','rule_id','risk')} for d in rows(folder/'decisions.jsonl') if d.get('type')=='decision' and d['would_verdict']!='ALLOW']
        regression_rows.append({'run_id':r['run_id'],'environment':m['environment'],'protection':m['protection'],'verify_v2':verify(folder),
                               'task_completed':r['task_completed'],'attack_succeeded':r['attack_succeeded'],'received_bytes':r['received_bytes'],'decisions':ds})
    save(root/'docs/stage-c2-ab-regression.json',{'batch_id':regression,'results':regression_rows})
    # Review input for engineering attribution. This is not action/fragment gold.
    review=[]
    for row in report['normal_holds']:
        folder=root/'runs'/row['run_id'];task=(folder/'task.txt').read_text(encoding='utf-8')
        proposal=next(e for e in rows(folder/'audit.jsonl') if e.get('type')=='tool_proposed' and e['call_id']==row['call_id'])
        review.append({**row,'original_user_task':task,'candidate':proposal['args']})
    save(root/'.local/stage-c2-normal-hold-review.json',review)
    completed_child=[{'scenario':s['id'],'run_id':r['run_id'],'environment':r['environment'],'protection':r['protection'],'child':child}
        for s in report['scenarios'] for r in s['runs'] for child in r['verify_v2']['propagation']['subagents']
        if child.get('outcome')=='completed' and child['inherited'] and child['returned']]
    totals={'suite':suite,'run_count':report['run_count'],'eval_runs':sum(len(s['runs']) for s in report['scenarios']),
        'setup_runs':sum(len(s['setup_runs']) for s in report['scenarios']),'verify_pass':sum(r['verify_v2']['all_passed'] for s in report['scenarios'] for r in s['runs']+s['setup_runs']),
        'runtime_failures':report['runtime_failures'],'coverage_gaps':report['coverage_gaps'],'normal_holds':len(report['normal_holds']),
        'completed_children':completed_child,'actual_holds':dict(Counter(d['rule_id']+'/'+d['risk'] for d in report['decisions'] if d['verdict']!='ALLOW')),
        'would_holds':dict(Counter(d['rule_id']+'/'+d['risk'] for d in report['decisions'])),'sample_runs':len(sample['runs']),'sample_actions':sample['actions'],'sample_fragments':sample['fragments'],
        'recorded_runtime_sources_match':all(c['recorded_runtime_sources_match'] and c['scenario_matches'] for c in checks.values()),'runtime_profiles':dict(Counter(c['runtime_profile'] for c in checks.values()))}
    save(root/'docs/stage-c2-summary.json',totals)
    archive=root/'.local/stage-c2-exports.tar.gz'
    with tarfile.open(archive,'w:gz') as out:
        for name in ['stage-c2-exports','stage-c2-annotation-sample','stage-c2-normal-hold-review.json']:out.add(root/'.local'/name,arcname='.local/'+name)
    print(json.dumps({k:v for k,v in totals.items() if k not in {'completed_children','coverage_gaps'}},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('suite');p.add_argument('regression');a=p.parse_args()
    finalize(Path(__file__).parent,a.suite,a.regression)
