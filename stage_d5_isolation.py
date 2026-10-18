"""Fixed D-prime isolation thresholds; output only aggregate rejection reasons."""
import collections
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from stage_d5_protocol import ROOT,OUT,read,sha,save,write_rows,budget,blocked_sources
from stage_d_prime_isolation import canon,template
from stage_d3_fast_isolation import FastIndex,batched_maximum
from stage_d2_isolation import segments

def main(prepare_index=False):
    import torch
    from transformers import AutoTokenizer,AutoModel
    start=time.time();budget(180)
    frozen=json.loads((ROOT/'.local/stage-d2/exclusions.json').read_text())
    held=read(ROOT/'.local/stage-d3/frozen-heldout.jsonl')
    real=read(ROOT/'.local/stage-d4/benign-frozen.jsonl');host=[] if prepare_index else read(OUT/'host-test-frozen.jsonl')
    base_exclusion=list(dict.fromkeys(frozen['frozen']+[r['raw_text'] for r in held+real]))
    exclusion=base_exclusion+[r['raw_text'] for r in host]
    patterns=frozen['payload_sentences'];index=FastIndex();pattern_index=FastIndex()
    for i,text in enumerate(exclusion):index.add(text,str(i),'frozen')
    for i,text in enumerate(patterns):pattern_index.add(template(text),str(i),'frozen')
    candidates=[] if prepare_index else read(OUT/'candidate-admitted.jsonl');candidates.sort(key=lambda r:(r['split']!='validation',not r.get('origin','').startswith('synthetic'),hashlib.sha256(r['id'].encode()).hexdigest()))
    blocked,_=blocked_sources();seen=set();kept=[];reject=collections.Counter()
    for number,r in enumerate(candidates):
        budget(180);reason=None;text=r['raw_text'];sig=canon(text)
        if r.get('repository','').lower() in blocked:reason='test_repository'
        elif sig in seen:reason='exact_duplicate'
        else:
            for part in segments(text):
                if index.match(part,r['split']):reason='char5_jaccard_ge_0.5';break
                if pattern_index.match(template(part),r['split']):reason='scenario_payload_template';break
        if reason:reject[reason]+=1;continue
        seen.add(sig);kept.append(r)
        for part in segments(text):index.add(part,r['id'],r['split'])
        if number%1000==0:print(json.dumps({'phase':'lexical','processed':number,'total':len(candidates)}),flush=True)
    del index,pattern_index
    torch.set_num_threads(4)
    modelpath=Path('/home/roots/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181')
    tok=AutoTokenizer.from_pretrained(modelpath,local_files_only=True);model=AutoModel.from_pretrained(modelpath,local_files_only=True).to('cuda:0').half().eval()
    def embed(texts):
        result=[]
        for i in range(0,len(texts),24):
            budget(100);parts=[];spans=[]
            for text in texts[i:i+24]:
                ids=tok(text,add_special_tokens=False)['input_ids'];a=len(parts)
                parts.extend(tok.prepare_for_model(ids[j:j+480],return_attention_mask=True) for j in range(0,max(1,len(ids)),448));spans.append((a,len(parts)))
            vectors=[]
            for j in range(0,len(parts),24):
                batch=tok.pad(parts[j:j+24],padding=True,return_tensors='pt').to('cuda:0')
                with torch.inference_mode():v=torch.nn.functional.normalize(model(**batch).last_hidden_state[:,0].float(),dim=1)
                vectors.append(v.cpu())
            v=torch.cat(vectors);result.extend(torch.nn.functional.normalize(v[a:b].mean(0),dim=0).numpy() for a,b in spans)
        return np.asarray(result,dtype=np.float32)
    base_texts=[canon(s) for s in base_exclusion+patterns]
    cache_key=hashlib.sha256(json.dumps({'texts':base_texts,'revision':modelpath.name,'encoding':'480/448 mean CLS normalized'},ensure_ascii=False).encode()).hexdigest()
    cache=OUT/'base-isolation-vectors.npy';meta=OUT/'base-isolation-vectors.json'
    if cache.exists():
        record=json.loads(meta.read_text())
        if record['input_sha256']!=cache_key or record['vectors_sha256']!=sha(cache):raise ValueError('Isolation reference cache changed')
        f=np.load(cache,allow_pickle=False)
    else:
        f=embed(base_texts)
        with cache.open('xb') as stream:np.save(stream,f,allow_pickle=False)
        save(meta.name,{'input_sha256':cache_key,'vectors_sha256':sha(cache),'n':len(f)})
    if prepare_index:
        save('isolation-preparation.json',{'reference_n':len(f),'seconds':time.time()-start,'S1_inference':False});print('Isolation reference index prepared',flush=True);return
    if host:f=np.concatenate([f,embed([canon(r['raw_text']) for r in host])])
    v=embed([canon(r['raw_text']) for r in kept]);scores=batched_maximum(f,v,lambda:budget(100));accepted=[];indices=[]
    for i,r in enumerate(kept):
        budget(100);reason=None
        if scores[i]>=.9:reason='frozen_embedding_ge_0.9'
        else:
            other=[j for j in indices if kept[j]['split']!=r['split']]
            if other and float((v[other]@v[i]).max())>=.9:reason='cross_split_embedding_ge_0.9'
        if reason:reject[reason]+=1
        else:accepted.append(r);indices.append(i)
    write_rows('isolated.jsonl',accepted)
    result={'passed':True,'candidate_n':len(candidates),'kept_n':len(accepted),'rejected_counts':dict(reject),'thresholds':{'character_5gram_jaccard':.5,'bge_cosine':.9},'test_repository_overlap':[],'isolated_sha256':sha(OUT/'isolated.jsonl'),'embedding_revision':modelpath.name,'seconds':time.time()-start,'test_error_examples_exported':False}
    save('isolation.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':
    import sys
    main('--prepare-index' in sys.argv)
