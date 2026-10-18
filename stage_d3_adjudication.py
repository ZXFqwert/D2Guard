"""Freeze blind, deterministic disagreement batches for authorized agent teachers."""
import argparse
import collections
import hashlib
import json
from stage_d3_protocol import OUT,budget,sha
from stage_d3_stream_review import complete_rows
from stage_d3_teacher import MODELS,RUBRIC,digest


def main(number,limit=288,validation_only=False,isolated_dilution=False,isolated_training=False):
    budget(reserve=120)
    folder=OUT/'adjudication'/('batch-'+str(number));folder.mkdir(parents=True,exist_ok=False)
    rows=[];votes=[]
    if isolated_dilution or isolated_training:
        rows=[r for r in complete_rows(OUT/'isolated.jsonl') if r['split']=='train' and (not isolated_dilution or r['transform']=='dilution')]
        votes=complete_rows(OUT/'teacher-votes-combined.jsonl')
    else:
        for parent in (OUT,OUT/'supplement'):
            for generator in ('cloud','local'):rows.extend(complete_rows(parent/('generated-'+generator+'.jsonl')))
            votes.extend(complete_rows(parent/'teacher-votes.jsonl'))
    lookup={(v['model'],v['id']):v for v in votes}
    if len(lookup)!=len(votes):raise ValueError('Duplicate original vote')
    excluded=set()
    def gather(value):
        if isinstance(value,dict):
            if 'id' in value:excluded.add(value['id'])
            for key,v in value.items():
                if key=='sample_ids':excluded.update(v)
                else:gather(v)
        elif isinstance(value,list):
            for v in value:gather(v)
    for path in OUT.glob('dean-*-audit.json'):gather(json.loads(path.read_text(encoding='utf-8')))
    for path in (OUT/'adjudication').glob('batch-*/assignments.json'):
        excluded.update(json.loads(path.read_text(encoding='utf-8'))['ids'])
    buckets=collections.defaultdict(list)
    for row in rows:
        if row['id'] in excluded or (validation_only and row['split']!='validation'):continue
        pair=[lookup.get((m,row['id'])) for m in MODELS]
        if not all(pair):continue
        if any(v['input_sha256']!=digest(row) for v in pair):raise ValueError('Vote input changed')
        if all(v['label']==row['label'] for v in pair):continue
        key=tuple(row[k] for k in ('split','generator','language','label'))
        buckets[key].append(row)
    for values in buckets.values():values.sort(key=lambda r:hashlib.sha256(r['id'].encode()).hexdigest())
    chosen=[]
    while len(chosen)<limit and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(chosen)<limit:chosen.append(buckets[key].pop(0))
    chosen.sort(key=lambda r:hashlib.sha256(r['id'].encode()).hexdigest())
    for worker in range(3):
        with (folder/('blind-'+str(worker+1)+'.jsonl')).open('x',encoding='utf-8') as f:
            for row in chosen[worker::3]:
                f.write(json.dumps({'id':row['id'],'source_type':row['source_type'],'text':row['text'],'input_sha256':digest(row)},ensure_ascii=False)+'\n')
    (folder/'rubric.txt').write_text(RUBRIC,encoding='utf-8')
    with (folder/'original-votes.jsonl').open('x',encoding='utf-8') as f:
        for row in chosen:f.write(json.dumps({'id':row['id'],'contract_label':row['label'],'votes':[lookup[(m,row['id'])] for m in MODELS]},ensure_ascii=False)+'\n')
    record={'batch':number,'n':len(chosen),'ids':[r['id'] for r in chosen],
            'sampling':'smallest sha256(id), round robin split/generator/language/contract-label; prior audited/assigned IDs excluded',
            'split':dict(collections.Counter(r['split'] for r in chosen)),'validation_only':validation_only,'isolated_dilution':isolated_dilution,'isolated_training':isolated_training,
            'rubric_sha256':sha(folder/'rubric.txt'),'blind_sha256':{str(i):sha(folder/('blind-'+str(i)+'.jsonl')) for i in (1,2,3)}}
    (folder/'assignments.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k!='ids'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('number',type=int);p.add_argument('--limit',type=int,default=288);p.add_argument('--validation-only',action='store_true')
    p.add_argument('--isolated-dilution',action='store_true')
    p.add_argument('--isolated-training',action='store_true')
    a=p.parse_args();main(a.number,a.limit,a.validation_only,a.isolated_dilution,a.isolated_training)
