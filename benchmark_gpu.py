"""Offline GPU measurement and controlled security-fact probes; no Agent execution."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from original_laya import OriginalLaya, QUESTIONS


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--cases',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    fast=OriginalLaya(a.config)
    cases=json.loads(a.cases.read_text(encoding='utf-8'))
    report={'kind':'offline_gpu_and_counterfactual_diagnostic_not_defense_validation',
            'model':fast.metadata,'measurements':[],'counterfactuals':[],
            'question_sha256':hashlib.sha256(json.dumps(QUESTIONS,sort_keys=True).encode()).hexdigest()}
    try:
        for case in cases:
            payload=case['payload']
            digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            if digest!=case['payload_sha256']:raise ValueError('Case digest mismatch')
            fast.classify_security(**payload)
            samples=[]
            for _ in range(10):
                fast.classify_security(**payload)
                samples.append(copy.deepcopy(fast.last_trace))
            row={'case':case['name'],'payload_sha256':digest,'samples':samples,
                 'median_ms':statistics.median(x['latency_ms'] for x in samples),
                 'max_ms':max(x['latency_ms'] for x in samples),
                 'recorded_cpu_answers':case.get('recorded_cpu_answers')}
            report['measurements'].append(row)
            print(case['name'],row['median_ms'],flush=True)
        # These deliberate input interventions are diagnostics, not new attack runs
        # or an independent evaluation set. They never change deployed questions.
        by_name={c['name']:c for c in cases}
        for variant in ('explicitly_authorized_sensitive_read','no_matching_external_source','withdrawn_write_grant'):
            source=by_name['normal_write' if variant=='withdrawn_write_grant' else 'ungranted_sensitive_read']
            payload=copy.deepcopy(source['payload'])
            state=payload['previous_security_state'];delta=payload['security_delta']
            if variant=='explicitly_authorized_sensitive_read':
                state['authority_anchor']['read'].append(delta['target'])
                delta['in_user_granted_scope']=True
            elif variant=='no_matching_external_source':
                state['active_taints']=[];delta['matches_untrusted_taint']=[]
            else:
                state['authority_anchor']['write']=[];delta['in_user_granted_scope']=False
            fast.classify_security(**payload)
            report['counterfactuals'].append({'variant':variant,'source_case':source['name'],'trace':copy.deepcopy(fast.last_trace)})
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:
        fast.runtime.cleanup()


if __name__=='__main__':main()
