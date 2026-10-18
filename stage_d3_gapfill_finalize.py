"""Preserve pre-fit failure evidence, then merge authorized new candidates."""
import argparse
import collections
import json
import shutil
from stage_d3_protocol import OUT,read,sha,budget

OUTPUTS=('generated-combined.jsonl','teacher-votes-combined.jsonl','collection.json',
         'lexical-filter.json','isolated.jsonl','isolation.json','admitted.jsonl','admission.json',
         'new-validation-frozen.jsonl','probe.json','candidate-isolation-vectors.npy',
         'candidate-isolation-vectors.json')


def snapshot():
    if (OUT/'training-clock.json').exists():raise ValueError('Cannot amend data after training starts')
    archive=OUT/'pre-gapfill';archive.mkdir(exist_ok=False)
    hashes={}
    for name in OUTPUTS:
        path=OUT/name
        if not path.exists():continue
        shutil.copy2(path,archive/name)
        hashes[name]=sha(path)
        if sha(archive/name)!=hashes[name]:raise ValueError('Archive copy failed')
    (archive/'manifest.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')


def merge():
    budget(reserve=120)
    archive=OUT/'pre-gapfill';hashes=json.loads((archive/'manifest.json').read_text())
    for name,expected in hashes.items():
        if sha(archive/name)!=expected:raise ValueError('Historical evidence changed')
    folder=OUT/'gapfill';review=json.loads((folder/'stream-review.json').read_text())
    if not review['complete'] or sha(folder/'teacher-votes.jsonl')!=review['teacher_votes_sha256']:
        raise ValueError('Gapfill review incomplete')
    rows=read(archive/'generated-combined.jsonl');votes=read(archive/'teacher-votes-combined.jsonl')
    added=[]
    for generator in ('cloud','local'):
        path=folder/('generated-'+generator+'.jsonl')
        if sha(path)!=review['generated_sha256'][generator]:raise ValueError('Changed generation')
        added+=read(path)
    rows+=added;votes+=read(folder/'teacher-votes.jsonl')
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate candidate ID')
    if len({(v['model'],v['id']) for v in votes})!=len(votes):raise ValueError('Duplicate teacher vote')
    clear()
    for name,items in [('generated-combined',rows),('teacher-votes-combined',votes)]:
        with (OUT/(name+'.jsonl')).open('x',encoding='utf-8') as f:
            for row in items:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    old=json.loads((archive/'collection.json').read_text())
    errors=collections.Counter(old['errors']);errors.update(review['errors'])
    result={'complete':True,'sources':old['sources'],'gapfill_review':review,
            'previous_collection_sha256':hashes['collection.json'],'gapfill_n':len(added),
            'candidate_n':len(rows),'vote_n':len(votes),
            'generated_sha256':sha(OUT/'generated-combined.jsonl'),
            'teacher_votes_sha256':sha(OUT/'teacher-votes-combined.jsonl'),'errors':dict(errors)}
    (OUT/'collection.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'candidate_n':len(rows),'gapfill_n':len(added),'vote_n':len(votes)}))


def clear():
    archive=OUT/'pre-gapfill';hashes=json.loads((archive/'manifest.json').read_text())
    # Verify every exact archive and current target before any deletion.
    targets=[]
    for name in OUTPUTS:
        path=OUT/name
        if not path.exists():continue
        if name not in hashes or sha(path)!=hashes[name] or sha(archive/name)!=hashes[name]:
            raise ValueError('Unexpected current output or changed archive')
        if path.resolve().parent!=OUT.resolve():raise ValueError('Target outside stage folder')
        targets.append(path)
    for path in targets:path.unlink()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['snapshot','merge','clear']);a=p.parse_args()
    {'snapshot':snapshot,'merge':merge,'clear':clear}[a.operation]()
