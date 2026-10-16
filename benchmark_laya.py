"""Offline runtime comparison on recorded security facts, never an Agent replay.

No tools, model API requests, verdicts or attack outcomes are produced here.
The checkpoint, questions and security facts stay fixed across runtime variants.
"""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from d2v2.compression import fast_view
from original_laya import OriginalLaya, QUESTIONS, payload_for


def read_cases():
    sources = [('normal_read', '20261016-135333-36e8d4', 'fs.read'),
               ('normal_write', '20261016-135333-36e8d4', 'fs.write'),
               ('ungranted_sensitive_read', '20261016-135159-540bea', 'fs.read')]
    cases = []
    for name, run_id, tool in sources:
        rows = [json.loads(line) for line in (ROOT/'runs'/run_id/'decisions.jsonl').read_text(encoding='utf-8').splitlines()]
        matches = [r for r in rows if r.get('type') == 'decision' and
                   r['evidence']['security_delta']['tool'] == tool and r['fast'].get('model_used')]
        row = matches[-1] if name == 'ungranted_sensitive_read' else matches[0]
        payload = payload_for(fast_view(row['previous_security_state']), fast_view(row['evidence']['security_delta']))
        sha = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if sha != row['fast']['input']['payload_sha256']:
            raise ValueError('Recorded input digest mismatch')
        cases.append({'name':name, 'run_id':run_id, 'payload_sha256':sha, 'payload':payload,
                      'recorded_cpu_answers':row['fast']['answers']})
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/laya-runtime-benchmark.json')
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    import torch
    fast = OriginalLaya(ROOT/'.local/laya.json')
    cases = read_cases()
    # No input formatting, precision, weights or question changes.
    variants = [(4, False), (2, False), (1, False), (4, True)]
    measurements = []
    forward_times = []
    original_forward = fast.agent._forward
    def timed_forward(batch):
        start = time.perf_counter()
        try:
            return original_forward(batch)
        finally:
            forward_times.append((time.perf_counter()-start)*1000)
    fast.agent._forward = timed_forward
    report = {'kind':'offline_runtime_comparison_not_defense_validation', 'model':fast.metadata,
              'cases':[{k:v for k,v in c.items() if k!='payload'} for c in cases],
              'questions_sha256':hashlib.sha256(json.dumps(QUESTIONS,sort_keys=True).encode()).hexdigest(),
              'measurements':measurements, 'complete':False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    try:
        for repeat in range(args.repeats):
            jobs = [(variant, case) for variant in variants for case in cases]
            random.Random(711+repeat).shuffle(jobs)
            for (threads,inference),case in jobs:
                torch.set_num_threads(threads)
                forward_times.clear()
                start = time.perf_counter()
                with torch.inference_mode() if inference else contextlib.nullcontext():
                    result = fast.agent.system_one(case['payload'], QUESTIONS, max_len=2048)
                elapsed = (time.perf_counter()-start)*1000
                row = {'repeat':repeat, 'case':case['name'], 'threads':threads,
                       'inference_mode':inference, 'elapsed_ms':elapsed,
                       'forward_ms':sum(forward_times), 'forward_calls':len(forward_times),
                       'usage':result['usage'], 'answers':result['answers']}
                measurements.append(row)
                save()
                print(json.dumps({k:row[k] for k in ('repeat','case','threads','inference_mode','elapsed_ms','forward_ms')}),flush=True)
        summaries = []
        for threads,inference in variants:
            selected = [m for m in measurements if m['threads']==threads and m['inference_mode']==inference]
            summaries.append({'threads':threads, 'inference_mode':inference,
                              'median_ms':statistics.median(m['elapsed_ms'] for m in selected),
                              'per_case_median_ms':{c['name']:statistics.median(m['elapsed_ms'] for m in selected if m['case']==c['name']) for c in cases}})
        report.update(complete=True, summaries=summaries)
        save()
    finally:
        fast.agent._forward = original_forward
        fast.runtime.cleanup()


if __name__ == '__main__':
    main()
