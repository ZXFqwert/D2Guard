"""Aggregate real evidence without using runtime defense-success summary flags."""
import argparse
import json
from pathlib import Path
from verify_v2 import verify, rows


def analyze(suite_path):
    root=suite_path.parent.parent;suite=json.loads(suite_path.read_text(encoding='utf-8'))
    summary={'suite':suite['suite'],'evaluation_only':True,'scenarios':[],'decisions':[],
             'normal_holds':[],'run_count':0,'runtime_failures':[],'coverage_gaps':[]}
    for item in suite['batches']:
        batch=json.loads((suite_path.parent/(item['batch_id']+'.json')).read_text(encoding='utf-8'))
        scenario=json.loads((root/'scenarios'/(item['scenario']+'.json')).read_text(encoding='utf-8'))
        record={'id':item['scenario'],'category':scenario['category'],'batch_id':item['batch_id'],
                'status':batch['status'],'pairing':batch['pairing'],'runs':[],'setup_runs':[]}
        for r in batch['setup_runs']+batch['results']:
            folder=suite_path.parent/r['run_id'];v=verify(folder)
            m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
            summary['run_count']+=1
            if not result['model_run_ok']:summary['runtime_failures'].append(r['run_id'])
            compact={k:r[k] for k in ('run_id','repeat','environment','protection','phase')}
            compact.update(verify_v2=v,task_completed=result['task_completed'],attack_succeeded=result['attack_succeeded'],
                           received_bytes=result['received_bytes'],model_run_ok=result['model_run_ok'])
            record['setup_runs' if r['phase']=='setup' else 'runs'].append(compact)
            for key in ('required_memory_covered','required_subagent_covered'):
                if v['propagation'].get(key) is False:summary['coverage_gaps'].append({'run_id':r['run_id'],'requirement':key})
            for d in rows(folder/'decisions.jsonl'):
                if d.get('type')!='decision' or d['would_verdict'] not in {'ASK','BLOCK'}:continue
                delta=d['evidence']['security_delta']
                row={'scenario':item['scenario'],'run_id':r['run_id'],'phase':r['phase'],
                     'environment':m['environment'],'protection':m['protection'],
                     'call_id':d['call_id'],'verdict':d['verdict'],'would_verdict':d['would_verdict'],
                     'rule_id':d['rule_id'],'risk':d['risk'],'tool':delta['tool'],'target':delta['target'],
                     'evidence_refs':d['evidence']['evidence_refs'],'model_used':d['fast'].get('model_used'),
                     'decision_facts':d['decision_facts'],'model_answers':d['model_answers']}
                summary['decisions'].append(row)
                if d['verdict'] in {'ASK','BLOCK'} and (m['environment']=='clean' or scenario['category']=='normal'):
                    # This field is deliberately empty until evidence is reviewed.
                    summary['normal_holds'].append({**row,'attribution':None,'attribution_explanation':None})
        summary['scenarios'].append(record)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('suite',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze(a.suite)
    a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'runs':r['run_count'],'scenarios':len(r['scenarios']),'normal_holds':len(r['normal_holds']),
                      'runtime_failures':r['runtime_failures'],'coverage_gaps':r['coverage_gaps']},ensure_ascii=False))
