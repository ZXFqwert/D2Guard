"""Overlap generation with blind review; isolation still precedes admission."""
import collections
import concurrent.futures
import json
import subprocess
import sys
import time
import argparse
from stage_d3_protocol import ROOT,OUT,budget,sha
from stage_d3_teacher import MODELS,judge
import stage_d3_teacher as teacher


def complete_rows(path):
    if not path.exists():return []
    # A live generator may be writing its last line; do not send partial JSON.
    data=path.read_bytes();data=data[:data.rfind(b'\n')+1]
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def main(resume=False):
    qualification=json.loads((OUT/'teacher-qualification.json').read_text(encoding='utf-8'))
    if not all(v['passed'] for v in qualification.values()):raise ValueError('Teacher qualification incomplete')
    existing=complete_rows(OUT/'teacher-votes.jsonl') if resume else []
    saved={(v['model'],v['id']) for v in existing}
    if len(saved)!=len(existing):raise ValueError('Duplicate saved votes')
    seen=set();jobs=collections.deque();pending={};errors=collections.Counter();votes=len(existing);complete=False;last_fetch=0;last_log=0
    if resume:
        prior=json.loads((OUT/'review-progress.json').read_text(encoding='utf-8'))
        errors.update(prior['errors']);errors['stream_resume_after_snapshot_timeout']+=1
    with (OUT/'teacher-votes.jsonl').open('a' if resume else 'x',encoding='utf-8') as stream, concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        while True:
            budget(reserve=100)
            if time.monotonic()-last_fetch>=60:
                prefix=OUT.relative_to(ROOT).as_posix()+'/'
                for remote,local in [('generated-local.jsonl','generated-local.jsonl'),('generation-local.json','generation-local.json')]:
                    try:
                        r=subprocess.run([sys.executable,str(ROOT/'.local/stage_d2_remote.py'),'get-fast',prefix+remote,prefix+local],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',errors='replace',timeout=55)
                        if r.returncode:errors['snapshot_transfer']+=1
                    except subprocess.TimeoutExpired:errors['snapshot_timeout']+=1
                last_fetch=time.monotonic()
            fresh=[]
            for generator in ('cloud','local'):
                for row in complete_rows(OUT/('generated-'+generator+'.jsonl')):
                    if row['id'] not in seen:
                        if not row.get('synthetic'):raise ValueError('Only synthetic generation may be reviewed')
                        seen.add(row['id']);fresh.append(row)
            for model in MODELS:
                missing=[row for row in fresh if (model,row['id']) not in saved]
                for i in range(0,len(missing),4):jobs.append((model,missing[i:i+4]))
            while jobs and len(pending)<24:
                job=jobs.popleft();pending[pool.submit(judge,*job)]=job[0]
            done,_=concurrent.futures.wait(pending,timeout=1,return_when=concurrent.futures.FIRST_COMPLETED) if pending else (set(),set())
            for future in done:
                model=pending.pop(future)
                try:
                    new=future.result();votes+=len(new)
                    for v in new:stream.write(json.dumps(v,ensure_ascii=False)+'\n')
                    stream.flush()
                except Exception as e:errors[model+':'+type(e).__name__]+=1
            summaries=[]
            for g in ('cloud','local'):
                path=OUT/('generation-'+g+'.json')
                try:summaries.append(json.loads(path.read_text(encoding='utf-8')))
                except (FileNotFoundError,json.JSONDecodeError):pass
            complete=(len(summaries)==2 and all(r['attempted']==r['planned'] for r in summaries)
                      and len(seen)==sum(sum(r['generated'].values()) for r in summaries))
            state={'reviewed_candidate_n':len(seen),'votes':votes,'queued_batches':len(jobs),'running_batches':len(pending),'errors':dict(errors),'generation_complete':complete}
            (OUT/'review-progress.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
            if time.monotonic()-last_log>=60:print(json.dumps(state),flush=True);last_log=time.monotonic()
            if complete and not jobs and not pending:break
            if not pending:time.sleep(1)
    state.update(complete=True,teacher_votes_sha256=sha(OUT/'teacher-votes.jsonl'),generated_sha256={g:sha(OUT/('generated-'+g+'.jsonl')) for g in ('cloud','local')})
    (OUT/'stream-review.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    print(json.dumps(state),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--supplement',action='store_true');parser.add_argument('--gapfill',action='store_true');parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    if args.supplement:OUT=OUT/'supplement';teacher.OUT=OUT
    if args.gapfill:OUT=OUT/'gapfill';teacher.OUT=OUT
    main(args.resume)
