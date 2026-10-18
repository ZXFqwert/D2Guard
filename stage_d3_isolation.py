"""Fixed lexical/embedding gates; frozen evaluation content is never exported."""
import collections
import hashlib
import json
import time
import argparse
from pathlib import Path
import numpy as np
from stage_d3_protocol import ROOT, OUT, OLD, read, sha, budget
from stage_d_prime_isolation import Index, canon, template
from stage_d2_isolation import segments
from stage_d3_fast_isolation import FastIndex,batched_maximum


def main(prepare_index=False):
    import torch
    from transformers import AutoTokenizer, AutoModel
    start = time.time(); budget(reserve=100)
    manifest = json.loads((OUT/'semantic-view.json').read_text(encoding='utf-8'))
    # Original evidence hashes are checked on their local owning machine before
    # dispatch. The compute worker verifies the exact derived artifacts it uses.
    for name,record in manifest['datasets'].items():
        if sha(OUT/(name+'.jsonl')) != record['sha256']:
            raise ValueError('Derived frozen input changed')
    frozen = json.loads((OLD/'exclusions.json').read_text(encoding='utf-8'))
    retained = read(OUT/'retained-training.jsonl')
    oldval = read(OUT/'old-validation.jsonl'); held = read(OUT/'frozen-heldout.jsonl')
    rows=[]
    if not prepare_index:
        collection = json.loads((OUT/'collection.json').read_text(encoding='utf-8'))
        if not collection['complete'] or sha(OUT/'generated-combined.jsonl') != collection['generated_sha256']:
            raise ValueError('Candidate collection incomplete or changed')
        rows = read(OUT/'generated-combined.jsonl')
    rows.sort(key=lambda r:(r['split'] != 'validation',hashlib.sha256(r['id'].encode()).hexdigest()))
    index = FastIndex(); patterns = FastIndex(); seen = set(); kept=[]; rejected=[]
    for i,text in enumerate(frozen['frozen']):index.add(text,'gold:'+str(i),'frozen')
    for i,text in enumerate(frozen['payload_sentences']):patterns.add(template(text),'payload:'+str(i),'frozen')
    for r in oldval+held:index.add(r['raw_text'],r['id'],'frozen')
    for r in retained:index.add(r['raw_text'],r['id'],'train');seen.add(canon(r['raw_text']))
    tokenizers = [AutoTokenizer.from_pretrained(p,local_files_only=True) for p in
        [ROOT/'.local/models/laya-english/tokenizer',Path('/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf/tokenizer')]]
    for row_number,r in enumerate(rows):
        budget(reserve=100); text=r['text']; reason=None
        if row_number%500==0:print(json.dumps({'phase':'lexical_progress','processed':row_number,'total':len(rows),'seconds':time.time()-start}),flush=True)
        if canon(r['raw_text']) in seen:reason='exact_duplicate'
        if not reason:
            for part in segments(r['raw_text']):
                if index.match(part,r['split']):reason='char5_jaccard_ge_0.5';break
                if patterns.match(template(part),r['split']):reason='scenario_payload_sentence_template';break
        state=json.dumps({'source_type':r['source_type'],'fragment':text},ensure_ascii=False)
        lengths=[len(tok(state,add_special_tokens=False)['input_ids']) for tok in tokenizers]
        if not reason and max(lengths)>384:reason='whole_fragment_exceeds_384_token_view'
        if reason:
            rejected.append({'id':r['id'],'reason':reason});continue
        r={**r,'view_tokens_by_tokenizer':lengths}
        kept.append(r);seen.add(canon(r['raw_text']))
        for part in segments(r['raw_text']):index.add(part,r['id'],r['split'])
    print(json.dumps({'phase':'lexical','kept':len(kept),'rejected':len(rejected)}),flush=True)
    if not prepare_index:
        with (OUT/'lexical-filter.json').open('x',encoding='utf-8') as stream:
            json.dump({'candidate_sha256':sha(OUT/'generated-combined.jsonl'),'kept_n':len(kept),'rejected_n':len(rejected),'rejected_counts':dict(collections.Counter(r['reason'] for r in rejected)),'seconds':time.time()-start},stream,indent=2)
    modelpath=Path('/home/roots/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181')
    torch.set_num_threads(4)
    tok=AutoTokenizer.from_pretrained(modelpath,local_files_only=True)
    model=AutoModel.from_pretrained(modelpath,local_files_only=True).to('cuda:0').half().eval()
    def embed(texts):
        result=[]
        for i in range(0,len(texts),24):
            budget(reserve=100);parts=[];spans=[]
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
    # Exactly the prior embedding representation (canon), not a newly tuned gate.
    exclusions=list(dict.fromkeys(canon(s) for s in frozen['frozen']+frozen['payload_sentences'] if s.strip()))
    exclusions += [canon(r['raw_text']) for r in oldval+held]
    def cached(name,texts):
        key=hashlib.sha256(json.dumps({'texts':texts,'model':modelpath.name,'representation':'D2 canon, 480/448 windows mean CLS normalized'},ensure_ascii=False).encode()).hexdigest()
        path=OUT/(name+'-isolation-vectors.npy');meta=OUT/(name+'-isolation-vectors.json')
        if path.exists():
            record=json.loads(meta.read_text(encoding='utf-8'))
            if record['input_sha256']!=key or record['vectors_sha256']!=sha(path):raise ValueError('Isolation cache changed')
            values=np.load(path,allow_pickle=False)
            if len(values)!=len(texts):raise ValueError('Isolation cache size mismatch')
            return values
        values=embed(texts)
        with path.open('xb') as stream:np.save(stream,values,allow_pickle=False)
        meta.write_text(json.dumps({'input_sha256':key,'vectors_sha256':sha(path),'n':len(values)},indent=2),encoding='utf-8')
        return values
    f=cached('frozen',exclusions);oldtrain=cached('retained',[canon(r['raw_text']) for r in retained])
    if prepare_index:
        result={'prepared':True,'seconds':time.time()-start,'frozen_n':len(f),'retained_n':len(oldtrain)}
        (OUT/'isolation-preparation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True);return
    v=cached('candidate',[canon(r['raw_text']) for r in kept])
    frozen_scores=batched_maximum(f,v,lambda:budget(reserve=100))
    validation_indices=[i for i,r in enumerate(kept) if r['split']=='validation']
    retained_scores=dict(zip(validation_indices,batched_maximum(oldtrain,v[validation_indices],lambda:budget(reserve=100))))
    accepted=[];indices=[]
    for i,r in enumerate(kept):
        budget(reserve=100);reason=None
        if float(frozen_scores[i])>=.9:reason='frozen_embedding_ge_0.9'
        elif r['split']=='validation' and float(retained_scores[i])>=.9:reason='old_train_validation_embedding_ge_0.9'
        else:
            other=[j for j in indices if kept[j]['split']!=r['split']]
            if other and float((v[other]@v[i]).max())>=.9:reason='cross_split_embedding_ge_0.9'
        if reason:rejected.append({'id':r['id'],'reason':reason});continue
        accepted.append(r);indices.append(i)
    with (OUT/'isolated.jsonl').open('x',encoding='utf-8') as stream:
        for r in accepted:stream.write(json.dumps(r,ensure_ascii=False)+'\n')
    result={'passed':True,'candidate_n':len(rows),'kept_n':len(accepted),'split':dict(collections.Counter(r['split'] for r in accepted)),
            'rejected_counts':dict(collections.Counter(r['reason'] for r in rejected)),
            'rejections':rejected,'thresholds':frozen['thresholds'],'isolated_sha256':sha(OUT/'isolated.jsonl'),
            'embedding_revision':modelpath.name,'seconds':time.time()-start}
    result['optimization']='Exact cached posting counts; batched fixed-reference cosine with legacy boundary recheck; original sequential cross-split decisions'
    (OUT/'isolation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rejections'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-index',action='store_true');main(parser.parse_args().prepare_index)
