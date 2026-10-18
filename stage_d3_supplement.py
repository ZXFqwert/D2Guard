"""Fresh pre-fit candidates correcting a general brief contradiction, one round."""
import argparse
import collections
import concurrent.futures
import json
import time
from stage_d3_protocol import OUT as MAIN, budget
import stage_d3_data as data


def main(generator):
    out=MAIN/'supplement';out.mkdir(exist_ok=True)
    data.OUT=out;budget(reserve=100)
    q=json.loads((MAIN/'teacher-qualification.json').read_text(encoding='utf-8'))
    if not all(x['passed'] for x in q.values()):raise ValueError('Teacher gate failed')
    rows=[data.contract(split,10000+i*2+(generator=='local'),generator)
          for split,n in [('train',1200),('validation',400)] for i in range(n)]
    with (out/('contracts-'+generator+'.jsonl')).open('x',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    workers=16 if generator=='cloud' else 24
    counts=collections.Counter();errors=collections.Counter();total=0
    with (out/('generated-'+generator+'.jsonl')).open('x',encoding='utf-8') as stream,concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        iterator=iter(rows);pending={}
        def submit():
            row=next(iterator,None)
            if row is not None:budget(reserve=100);pending[pool.submit(data.generate,row)]=row['id']
        for _ in range(workers):submit()
        while pending:
            finished,_=concurrent.futures.wait(pending,timeout=20,return_when=concurrent.futures.FIRST_COMPLETED)
            budget(reserve=100)
            for future in finished:
                pending.pop(future);total+=1
                try:
                    row=future.result();stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();counts[row['split']]+=1
                except Exception as e:errors[str(e) if isinstance(e,data.CloudFailure) else type(e).__name__]+=1
                submit()
            state={'attempted':total,'planned':len(rows),'generated':dict(counts),'errors':dict(errors)}
            (out/('generation-'+generator+'.json')).write_text(json.dumps(state,indent=2),encoding='utf-8')
            if finished and total%100<workers:print(json.dumps(state),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('generator',choices=['cloud','local']);main(p.parse_args().generator)
