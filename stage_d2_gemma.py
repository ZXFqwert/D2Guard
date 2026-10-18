"""Local Gemma reference, independent of cloud generation and admission."""
import json
import time
from pathlib import Path
import httpx
import numpy as np
from stage_d2_teacher import RUBRIC, digest, view
from stage_d2_diagnostic import read, OUT, OLD, write_new
from stage_d2_metrics import mapped, groups, LABELS


def main():
    rows = mapped(read(OLD / 'gold.jsonl')); unique = {}
    for row in rows: unique.setdefault(digest(row), row)
    inputs = list(unique.values()); votes = []
    with (OUT/'gemma-started.json').open('x') as f: json.dump({'started_unix':time.time(),'unique_n':len(inputs)},f)
    with (OUT/'gemma-predictions.jsonl').open('x',encoding='utf-8') as stream:
        for start in range(0,len(inputs),8):
            batch = inputs[start:start+8]; before = time.monotonic()
            with httpx.Client(timeout=180,trust_env=False) as client:
                response=client.post('http://127.0.0.1:18175/v1/chat/completions',json={
                    'model':'stage-d2-gemma4-31b-q8','messages':[{'role':'system','content':RUBRIC},{'role':'user','content':json.dumps([{'id':i,**view(r)} for i,r in enumerate(batch)],ensure_ascii=False)}],
                    'temperature':0,'max_tokens':1500,'response_format':{'type':'json_object'}})
            if response.status_code != 200: raise RuntimeError('Gemma HTTP status '+str(response.status_code))
            body=response.json()
            if body.get('model')!='stage-d2-gemma4-31b-q8' or body['choices'][0]['finish_reason']!='stop': raise ValueError('Gemma identity/completeness failure')
            items=json.loads(body['choices'][0]['message']['content'])['items']
            if len(items)!=len(batch) or {x[0] for x in items}!=set(range(len(batch))):raise ValueError('Gemma coverage mismatch')
            for i,label,ps in items:
                if label not in LABELS or len(ps)!=3 or abs(sum(ps)-1)>.015 or min(ps)<0 or ps[LABELS.index(label)]<max(ps)-1e-8:raise ValueError('Invalid Gemma probabilities')
                rec={'id':batch[i]['id'],'input_sha256':digest(batch[i]),'probabilities':ps,'latency_ms_per_fragment':(time.monotonic()-before)*1000/len(batch)}
                votes.append(rec);stream.write(json.dumps(rec)+'\n')
            stream.flush();print(json.dumps({'gemma_unique_done':len(votes),'unique_total':len(inputs)}),flush=True)
    lookup={v['input_sha256']:v for v in votes};ps=np.array([lookup[digest(r)]['probabilities'] for r in rows])
    result={'model':'Gemma4-31B JANG_4M-CRACK Q8_0 (local derivative)', 'metrics':groups(rows,ps),
            'latency_ms_per_unique_fragment':float(np.mean([v['latency_ms_per_fragment'] for v in votes]))}
    write_new(OUT/'gemma-diagnostic.json',result);print(json.dumps(result['metrics']['all']),flush=True)

if __name__=='__main__':main()
