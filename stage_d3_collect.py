"""Freeze completed original and supplemental generation without replacing evidence."""
import collections
import json
from stage_d3_protocol import OUT, read, sha, budget
from stage_d3_stream_review import complete_rows


def main():
    budget(reserve=120)
    rows=[];votes=[];sources={};errors=collections.Counter()
    for directory in (OUT,OUT/'supplement'):
        cutoff_path=OUT/'cutoff/cutoff.json'
        cutoff=json.loads(cutoff_path.read_text(encoding='utf-8')) if directory==OUT and cutoff_path.exists() else None
        if cutoff:
            paths={'cloud':OUT/'generated-cloud.jsonl','local':OUT/'cutoff/generated-local.jsonl'}
            if sha(paths['local'])!=cutoff['generated_sha256']:raise ValueError('Cutoff input changed')
            progress=json.loads((OUT/'review-progress.json').read_text(encoding='utf-8'))
            n=sum(len(read(p)) for p in paths.values())
            if progress['reviewed_candidate_n']!=n or progress['queued_batches'] or progress['running_batches']:
                raise ValueError('Cutoff teacher review still pending')
            review={**progress,'complete':True,'teacher_votes_sha256':sha(OUT/'teacher-votes.jsonl'),
                    'generated_sha256':{g:sha(p) for g,p in paths.items()},'generation_cutoff':cutoff}
            (OUT/'cutoff/stream-review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
            sources['time_cutoff']=cutoff
        else:
            paths={g:directory/('generated-'+g+'.jsonl') for g in ('cloud','local')}
            review=json.loads((directory/'stream-review.json').read_text(encoding='utf-8'))
        if not review['complete']:raise ValueError('Review still running')
        if sha(directory/'teacher-votes.jsonl')!=review['teacher_votes_sha256']:
            raise ValueError('Changed teacher evidence')
        for generator in ('cloud','local'):
            path=paths[generator]
            state=json.loads((directory/('generation-'+generator+'.json')).read_text(encoding='utf-8'))
            part=read(path)
            if not (cutoff and generator=='local') and (state['attempted']!=state['planned'] or len(part)!=sum(state['generated'].values())):
                raise ValueError('Generation incomplete')
            if sha(path)!=review['generated_sha256'][generator]:raise ValueError('Changed generation evidence')
            sources[str(path.relative_to(OUT))]={'sha256':sha(path),'n':len(part),'state':state}
            rows.extend(part)
        votes.extend(read(directory/'teacher-votes.jsonl'))
        errors.update(review['errors'])
    ids={r['id'] for r in rows}
    if len(ids)!=len(rows):raise ValueError('Duplicate generated ID')
    if len({(v['model'],v['id']) for v in votes})!=len(votes):raise ValueError('Duplicate teacher vote')
    if any(v['id'] not in ids for v in votes):raise ValueError('Unknown teacher input')
    for name,items in [('generated-combined',rows),('teacher-votes-combined',votes)]:
        with (OUT/(name+'.jsonl')).open('x',encoding='utf-8') as f:
            for row in items:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    result={'complete':True,'sources':sources,'candidate_n':len(rows),'vote_n':len(votes),
            'generated_sha256':sha(OUT/'generated-combined.jsonl'),
            'teacher_votes_sha256':sha(OUT/'teacher-votes-combined.jsonl'),'errors':dict(errors)}
    (OUT/'collection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}))


if __name__=='__main__':main()
