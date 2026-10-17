"""Deterministic evaluation-only sample selection, independent of observed outcomes."""
import argparse,json
from pathlib import Path
from export_stage_c import export

def select(suite_path):
    root=suite_path.parent; suite=json.loads(suite_path.read_text(encoding='utf-8')); selected=[]
    for item in sorted(suite['batches'],key=lambda x:x['scenario']):
        batch=json.loads((root/(item['batch_id']+'.json')).read_text(encoding='utf-8'))
        scenario=json.loads((root.parent/'scenarios'/(item['scenario']+'.json')).read_text(encoding='utf-8'))
        environments=['attack','clean'] if scenario['category']=='attack' else ['clean']
        for environment in environments:
            candidates=[r for r in batch['results'] if r['environment']==environment and r['protection']=='off']
            if not candidates:raise ValueError('Missing required sample condition: '+item['scenario']+' '+environment)
            chosen=min(candidates,key=lambda r:(r['repeat'],r['run_id']))
            selected.append(root/chosen['run_id'])
    return selected

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('suite',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(export(select(a.suite),a.output),ensure_ascii=False,indent=2))
