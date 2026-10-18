"""Authorized pre-fit gap filling; retain original briefs, lengths and labels."""
import argparse
import collections
import concurrent.futures
import json
import re
import time
from stage_d3_protocol import OUT as MAIN, budget, sha
import stage_d3_data as data


def contracts(generator):
    result=[]
    for split,labels in [('train',['request']*300+['quoted']*100+['none']*600),
                         ('validation',['quoted']*40+['none']*160)]:
        # Rotate requested labels to avoid sending a class-blocked stream.
        remaining=collections.Counter(labels); index=200000+(generator=='local')
        languages=collections.Counter({'en':800,'zh':67,'ja':67,'ru':66}) if split=='train' else collections.Counter({'en':50,'zh':50,'ja':50,'ru':50})
        while any(remaining.values()):
            row=data.contract(split,index,generator);index+=2
            prose_styles={'repository_docs-01','repository_docs-05','code_comments-01','code_comments-06','email_ticket-01','email_ticket-04','email_ticket-05','email_ticket-06','memory-01','memory-03','memory-06','web-03','web-05'}
            if split=='train' and row['style_id'] not in prose_styles:continue
            if remaining[row['label']] and languages[row['language']] and (row['transform']=='dilution' if split=='train' else row['transform']=='plain'):
                row['gapfill_batch']='authorized-20261018'
                row['brief']['length_enforcement']='The assigned length is a strict budget for the COMPLETE DOCUMENT including all headings, schema fields, comments and metadata. Keep near the lower bound, never below it. Avoid repeated field names and verbose nested schemas. Use common concise vocabulary. Do not append explanation or expand beyond the requested length. Preserve all semantic content and the assigned structure.'
                if split=='train' and row['language']=='en':
                    row['brief']['length']='200–210 words TOTAL, including headings, field names and all metadata. Use short common words and concise sentences. Count the entire final document; do not exceed 210 words. At least 180 English words are required.'
                result.append(row);remaining[row['label']]-=1;languages[row['language']]-=1
    return result


def checked_generate(row):
    result=data.generate(row)
    if row['split']=='train':
        language=row['language'];text=result['raw_text']
        pattern=r'[A-Za-z]+(?:[\x27-][A-Za-z]+)*' if language=='en' else r'[\u0400-\u04ff]+' if language=='ru' else r'[\u3040-\u30ff\u3400-\u9fff]'
        count=len(re.findall(pattern,text));minimum={'en':180,'ru':110,'zh':280,'ja':280}[language]
        if count<minimum:raise data.CloudFailure('Below original long-document minimum')
        result['long_document_units']=count
        result['long_document_minimum']=minimum
    return result


def main(generator,smoke):
    out=MAIN/'gapfill';out.mkdir(exist_ok=True);data.OUT=out
    permission=json.loads((MAIN/'gapfill-authorization.json').read_text(encoding='utf-8'))
    if not permission['generation_allowed']:raise ValueError('No gap-fill authorization')
    budget(reserve=100)
    rows=contracts(generator)
    if smoke:
        rows=[r for r in rows if r['split']=='train'][:16]+[r for r in rows if r['split']=='validation'][:4]
    suffix='-smoke-v4' if smoke else ''
    with (out/('contracts-'+generator+suffix+'.jsonl')).open('x',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    counts=collections.Counter();errors=collections.Counter();total=0
    workers=16 if generator=='cloud' else 24
    with (out/('generated-'+generator+suffix+'.jsonl')).open('x',encoding='utf-8') as stream,concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        iterator=iter(rows);pending={}
        def submit():
            row=next(iterator,None)
            if row is not None:budget(reserve=100);pending[pool.submit(checked_generate,row)]=row['id']
        for _ in range(workers):submit()
        while pending:
            done,_=concurrent.futures.wait(pending,timeout=20,return_when=concurrent.futures.FIRST_COMPLETED)
            budget(reserve=100)
            for future in done:
                pending.pop(future);total+=1
                try:
                    row=future.result();stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();counts[row['split']]+=1
                except Exception as e:errors[str(e) if isinstance(e,data.CloudFailure) else type(e).__name__]+=1
                submit()
            state={'attempted':total,'planned':len(rows),'generated':dict(counts),'errors':dict(errors)}
            (out/('generation-'+generator+suffix+'.json')).write_text(json.dumps(state,indent=2),encoding='utf-8')
            if done and (smoke or total%100<workers):print(json.dumps(state),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('generator',choices=['cloud','local']);p.add_argument('--smoke',action='store_true')
    a=p.parse_args();main(a.generator,a.smoke)
