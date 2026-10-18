"""Label-blind gold/payload exclusions, fixed D-prime similarity thresholds."""
import argparse
import collections
import hashlib
import json
import re
import time
from pathlib import Path
import numpy as np
from stage_d2_data import ROOT,OUT,read,sha,reused_training
from stage_d_prime_isolation import Index,canon,template


def segments(text):
    return list(dict.fromkeys([text]+[x.strip() for x in re.split(r'\n+|(?<=[.!?。！？])\s+',text) if len(x.strip())>=24]))


def freeze():
    from stage_d_data import frozen_evaluation
    _,gold,files=frozen_evaluation();payload=[]
    def visit(value,inside=False):
        if isinstance(value,dict):
            for k,v in value.items():visit(v,inside or bool(re.search(r'attack|payload|injection|malicious|poison',k,re.I)))
        elif isinstance(value,list):
            for v in value:visit(v,inside)
        elif inside and isinstance(value,str) and len(value.strip())>=24:payload.extend(segments(value))
    for path in sorted((ROOT/'scenarios').rglob('*.json')):visit(json.loads(path.read_text(encoding='utf-8')))
    frozen=list(dict.fromkeys(x for row in gold for x in segments(row['text'])))
    value={'frozen':frozen,'payload_sentences':sorted(set(payload)),'source_sha256':files,'thresholds':{'char5_jaccard':.5,'bge_m3_cosine':.9},
           'policy':'Gold raw/near duplicates and scenario payload sentences only; domain is not excluded'}
    with (OUT/'exclusions.json').open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False)
    print(json.dumps({'gold_exclusion_units':len(frozen),'payload_units':len(value['payload_sentences'])}))


def run(round_number,smoke=False):
    import torch
    from transformers import AutoTokenizer,AutoModel
    from d2v2.content_model import windows
    folder=OUT/f'round-{round_number}';started=time.time()
    generation_start=json.loads((folder/'generation-clock.json').read_text())['started_unix']
    def budget():
        if time.time()-generation_start>=10800:raise TimeoutError('Round generation/admission 3-hour budget')
    frozen=json.loads((OUT/'exclusions.json').read_text(encoding='utf-8'))
    rows=read(folder/('isolation-smoke-input.jsonl' if smoke else 'generated.jsonl'))+([] if smoke else read(folder/'public-candidates.jsonl'))
    rows.sort(key=lambda r:(r['split']!='semantic_heldout',r['split']!='public_heldout',r['split']!='validation',sha(r['id'])))
    index=Index();patterns=Index();seen=set();kept=[];rejected=[]
    for i,text in enumerate(frozen['frozen']):index.add(text,'gold:'+str(i),'gold')
    for i,text in enumerate(frozen['payload_sentences']):patterns.add(template(text),'payload:'+str(i),'gold')
    # Frozen independent holdout is an exclusion source in later rounds only.
    if round_number>1:
        for row in read(OUT/'semantic-heldout-frozen.jsonl')+read(OUT/'validation-frozen.jsonl'):index.add(row['text'],row['id'],'frozen-evaluation')
    for row in reused_training(folder):seen.add(sha(canon(row['text'])))
    tokenizers=[AutoTokenizer.from_pretrained(str(p),local_files_only=True) for p in [ROOT/'.local/models/laya-english/tokenizer',Path('/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf/tokenizer')]]
    for row in rows:
        budget();text=row['text'];sig=sha(canon(text));reason=None;match=None
        if sig in seen:reason='exact_duplicate'
        else:
            for part in segments(text):
                match=index.match(part,row['split'])
                if match:reason='char5_jaccard_ge_0.5';break
                match=patterns.match(template(part),row['split'])
                if match:reason='scenario_payload_sentence_template';break
        if not reason and any(len(windows(tok,text,row['source_type']))!=1 for tok in tokenizers):reason='whole_fragment_exceeds_256_token_view'
        if reason:rejected.append({'id':row['id'],'reason':reason,'match':match});continue
        seen.add(sig);kept.append({**row,'text_normalized':True})
        for part in segments(text):index.add(part,row['id'],row['split'])
    print(json.dumps({'lexical_and_budget_kept':len(kept),'rejected':len(rejected)}),flush=True)
    modelpath=Path('/home/roots/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181')
    torch.set_num_threads(4)
    tok=AutoTokenizer.from_pretrained(modelpath,local_files_only=True)
    model=AutoModel.from_pretrained(modelpath,local_files_only=True).to('cuda:0').half().eval()
    def embed(texts):
        result=[]
        for i in range(0,len(texts),24):
            budget();parts=[];spans=[]
            for text in texts[i:i+24]:
                ids=tok(text,add_special_tokens=False)['input_ids'];start=len(parts)
                parts.extend(tok.prepare_for_model(ids[j:j+480],return_attention_mask=True) for j in range(0,max(1,len(ids)),448));spans.append((start,len(parts)))
            vectors=[]
            for j in range(0,len(parts),24):
                batch=tok.pad(parts[j:j+24],padding=True,return_tensors='pt').to('cuda:0')
                with torch.inference_mode():z=torch.nn.functional.normalize(model(**batch).last_hidden_state[:,0].float(),dim=1)
                vectors.append(z.cpu())
            v=torch.cat(vectors);result.extend(torch.nn.functional.normalize(v[a:b].mean(0),dim=0).numpy() for a,b in spans)
        return np.asarray(result,dtype=np.float32)
    exclusion=list(dict.fromkeys(canon(s) for s in frozen['frozen']+frozen['payload_sentences'] if s.strip()))
    if round_number>1:exclusion += [r['text'] for r in read(OUT/'semantic-heldout-frozen.jsonl')+read(OUT/'validation-frozen.jsonl')]
    f=embed(exclusion);v=embed([r['text'] for r in kept]);accepted=[];indices=[]
    for i,row in enumerate(kept):
        budget();score=float((f@v[i]).max())
        if score>=.9:rejected.append({'id':row['id'],'reason':'frozen_embedding_ge_0.9','cosine':score});continue
        other=[j for j in indices if kept[j]['split']!=row['split']]
        if other and float((v[other]@v[i]).max())>=.9:
            rejected.append({'id':row['id'],'reason':'cross_split_embedding_ge_0.9'});continue
        accepted.append(row);indices.append(i)
    violations=[]
    for field in ('family','domain','source_dataset'):
        assignment=collections.defaultdict(set)
        for row in accepted:assignment[row[field]].add(row['split'])
        violations.extend(field+':'+name for name,splits in assignment.items() if len(splits)>1)
    if violations:raise ValueError('Split group violation')
    output=folder/('isolated-smoke.jsonl' if smoke else 'isolated.jsonl')
    with output.open('x',encoding='utf-8') as stream:
        for row in accepted:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    result={'passed':True,'candidate_n':len(rows),'kept_n':len(accepted),'split':dict(collections.Counter(r['split'] for r in accepted)),
            'rejected_counts':dict(collections.Counter(r['reason'] for r in rejected)),'rejections':rejected,'seconds':time.time()-started,
            'thresholds':frozen['thresholds'],'embedding_revision':modelpath.name,'group_violations':violations,'isolated_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
    (folder/('isolation-smoke.json' if smoke else 'isolation.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rejections'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--round',type=int,default=1);p.add_argument('--smoke',action='store_true');a=p.parse_args();freeze() if a.freeze else run(a.round,a.smoke)
