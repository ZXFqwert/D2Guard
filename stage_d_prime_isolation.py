"""Fixed lexical/template and embedding exclusion gates, never label-driven."""
import argparse,collections,json,re,time,sys,hashlib
from pathlib import Path
import numpy as np
from stage_d_prime_data import ROOT,OUT,PREREG,read_jsonl,write_jsonl,sha,view,frozen_evaluation,all_strings
from d2v2.normalization import normalize

def canon(s):return re.sub(r'\s+',' ',normalize(s,casefold=True)[0]).strip()
def content_body(text):
    """Neutral context must never disguise a copied original or inflate size."""
    text=normalize(text)[0]
    return re.split(r'\n(?:Reference fields|参考字段|参照項目|Справочные поля|Synthetic source context[^\n]*?reference fields)\s*:',text,flags=re.I)[0]
def grams(s):
    s=canon(s);return {s[i:i+5] for i in range(max(1,len(s)-4))}
def template(s):
    s=canon(s)
    s=re.sub(r'https?://[^\s<>"\)]+','<url>',s)
    s=re.sub(r'(?:[\w.~/-]+/)*[\w.-]+\.(?:env|json|txt|md|py|csv|sh|yaml|yml|toml|ini)','<path>',s)
    return re.sub(r'\d+','<n>',s)

class Index:
    def __init__(self):self.rows=[];self.reverse=collections.defaultdict(lambda:collections.defaultdict(list))
    def add(self,text,identity,split):
        g=grams(text);i=len(self.rows);self.rows.append((g,identity,split))
        for x in g:self.reverse[split][x].append(i)
    def match(self,text,split,threshold=.5):
        g=grams(text);counts=collections.Counter(i for previous,index in self.reverse.items() if previous!=split for x in g for i in index.get(x,()))
        for i,n in counts.most_common():
            old,id,previous=self.rows[i]
            if split==previous:continue
            if n/(len(g)+len(old)-n)>=threshold:return id
        return None

def freeze():
    frozen,gold,files=frozen_evaluation()
    write_jsonl(OUT/'gold.jsonl',gold)
    # Only exclusions are exported to the filtering worker, without gold labels.
    texts=list(dict.fromkeys(s for s in frozen if s.strip()))
    payload=[]
    def visit(d,key=''):
        if isinstance(d,dict):
            for k,v in d.items():visit(v,k)
        elif isinstance(d,list):
            for v in d:visit(v,key)
        elif isinstance(d,str) and re.search(r'attack|payload|injection|malicious',key,re.I):
            payload.extend(s.strip() for s in re.split(r'\n+|(?<=[.!?。！？])\s+',d) if len(s.strip())>=24)
    for p in sorted((ROOT/'scenarios').rglob('*.json')):visit(json.loads(p.read_text(encoding='utf8')))
    manifest={'frozen':texts,'payload_sentences':sorted(set(payload)),'source_sha256':files,'thresholds':PREREG['isolation']}
    (OUT/'exclusions.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf8')
    print(json.dumps({'frozen_unique':len(texts),'payload_sentences':len(manifest['payload_sentences']),'gold':len(gold)}))

def run():
    import torch
    from transformers import AutoTokenizer,AutoModel
    from d2v2.content_model import model_items
    started=time.time();reg=json.loads((OUT/'preregistered.json').read_text())
    def budget():
        if time.time()-reg['registered_unix']>10800:raise TimeoutError('Generation wall-clock exceeded 3 hours')
    rows=read_jsonl(OUT/'candidates.jsonl');frozen=json.loads((OUT/'exclusions.json').read_text(encoding='utf8'))
    index=Index();pattern=Index()
    for i,s in enumerate(frozen['frozen']):index.add(s,'frozen:'+str(i),'frozen')
    for i,s in enumerate(frozen['payload_sentences']):pattern.add(template(s),'payload:'+str(i),'frozen')
    # Stable pre-label order, public rows first so public sources are attempted.
    rows.sort(key=lambda r:(r['split']!='train',r['split']=='heldout',r['source_dataset'].startswith('authored'),sha(r['id'])))
    kept=[];reject=[];seen=set()
    for r in rows:
        text=view(r)['fragment'];body=content_body(text);sig=sha(canon(body))
        reason=None;match=None
        if sig in seen:reason='exact_duplicate'
        else:
            match=index.match(body,r['split']) or index.match(text,r['split'])
            if match:reason='5gram_jaccard_ge_0.5'
            if not reason:
                match=pattern.match(template(body),r['split']) or pattern.match(template(text),r['split'])
                if match:reason='scenario_payload_sentence_template'
        if reason:reject.append({'id':r['id'],'reason':reason,'match':match});continue
        seen.add(sig);kept.append(r);index.add(body,r['id'],r['split'])
    print(json.dumps({'lexical_kept':len(kept),'rejected':len(reject)}),flush=True);budget()
    # Same <=256-token full-fragment contract for both bases; never truncate.
    tokens=[AutoTokenizer.from_pretrained(str(p),local_files_only=True) for p in
            [ROOT/'.local/models/laya-english/tokenizer',Path('/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf/tokenizer')]]
    valid=[]
    for r in kept:
        if all(len(model_items(tok,r['text'],r['source_type']))==1 for tok in tokens):valid.append(r)
        else:reject.append({'id':r['id'],'reason':'full_fragment_token_budget'})
    kept=valid;print(json.dumps({'token_kept':len(kept)}),flush=True);budget()
    modelpath=Path('/home/roots/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181')
    tok=AutoTokenizer.from_pretrained(modelpath,local_files_only=True)
    model=AutoModel.from_pretrained(modelpath,local_files_only=True).to('cuda:0').eval().half()
    torch.set_num_threads(4)
    def embed(texts):
        outputs=[]
        for i in range(0,len(texts),24):
            budget();batch=texts[i:i+24]
            # Embedding windows cover the full exclusion text as well.
            windows=[];spans=[]
            for text in batch:
                ids=tok(text,add_special_tokens=False)['input_ids']
                chunks=[ids[j:j+480] for j in range(0,max(1,len(ids)),448)]
                spans.append((len(windows),len(windows)+len(chunks)))
                windows.extend(tok.prepare_for_model(c,return_attention_mask=True) for c in chunks)
            vectors=[]
            for j in range(0,len(windows),24):
                encoded=tok.pad(windows[j:j+24],padding=True,return_tensors='pt').to('cuda:0')
                with torch.inference_mode():z=model(**encoded).last_hidden_state[:,0].float();z=torch.nn.functional.normalize(z,dim=1)
                vectors.append(z.cpu())
            vectors=torch.cat(vectors)
            outputs.extend(torch.nn.functional.normalize(vectors[a:b].mean(0),dim=0).numpy() for a,b in spans)
        return np.asarray(outputs,dtype=np.float32)
    frozen_text=list(dict.fromkeys(canon(s) for s in frozen['frozen']+frozen['payload_sentences'] if s.strip()))
    # Both the semantic body and full classifier view must pass the gold gate.
    f=embed(frozen_text);v=embed([content_body(view(r)['fragment']) for r in kept])
    full=embed([view(r)['fragment'] for r in kept]);budget()
    accepted=[];accepted_idx=[]
    for i,r in enumerate(kept):
        scores=np.maximum(f@v[i],f@full[i]);j=int(scores.argmax())
        if float(scores[j])>=.9:
            reject.append({'id':r['id'],'reason':'embedding_cosine_ge_0.9','match':'frozen:'+str(j),'cosine':float(scores[j])});continue
        others=[k for k in accepted_idx if kept[k]['split']!=r['split']]
        if others:
            scores=np.maximum(v[others]@v[i],full[others]@full[i]);j=int(scores.argmax())
            if float(scores[j])>=.9:
                reject.append({'id':r['id'],'reason':'cross_split_embedding_ge_0.9','match':kept[others[j]]['id'],'cosine':float(scores[j])});continue
        accepted.append(r);accepted_idx.append(i)
    groups={k:collections.defaultdict(set) for k in ('family','source_dataset','domain')}
    for r in accepted:
        for k in groups:groups[k][r[k]].add(r['split'])
    violations=[(k,g) for k,values in groups.items() for g,splits in values.items() if len(splits)>1]
    if violations:raise ValueError('Cross-split group overlap: '+str(violations[:10]))
    write_jsonl(OUT/'isolated.jsonl',accepted)
    result={'passed':True,'candidate_n':len(rows),'kept_n':len(accepted),'split':dict(collections.Counter(r['split'] for r in accepted)),
            'rejected_counts':dict(collections.Counter(r['reason'] for r in reject)),'rejections':reject,
            'thresholds':PREREG['isolation'],'embedding_revision':modelpath.name,'embedding_pooling':'normalized CLS; full-text window mean',
            'group_violations':violations,'seconds':time.time()-started,'admitted_sha256':hashlib.sha256((OUT/'isolated.jsonl').read_bytes()).hexdigest()}
    (OUT/'isolation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rejections'}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');a=p.parse_args()
    freeze() if a.freeze else run()
