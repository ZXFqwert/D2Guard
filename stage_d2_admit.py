"""Unanimous contract/two-teacher admission; disagreement is never relabeled."""
import argparse,collections,concurrent.futures,hashlib,json,re,time
from stage_d2_data import OUT,read,sha,reused_training
from stage_d2_teacher import MODELS,judge,digest
from stage_d2_metrics import LABELS


def admission_decision(row,pair):
    if len(pair)!=2 or not all(pair):return 'missing'
    if {v['model'] for v in pair}!=set(MODELS):raise ValueError('Two independent registered teacher routes are required')
    if any(v['input_sha256']!=digest(row) for v in pair):raise ValueError('Teacher input hash mismatch')
    return 'admit' if all(v['label']==row['label'] for v in pair) else 'disagree'


def audit(rows):
    distribution={split:{field:dict(collections.Counter(r[field] for r in rows if r['split']==split)) for field in ('label','language','source_kind','transform','source_dataset')}
                  for split in sorted({r['split'] for r in rows})}
    checks={};targets={'train':3000,'validation':600,'semantic_heldout':600}
    for split,minimum in targets.items():
        part=[r for r in rows if r['split']==split];n=len(part)
        checks[split+'_minimum']=n>=minimum
        checks[split+'_request_prior']=bool(n) and .20<=sum(r['label']=='request' for r in part)/n<=.35
        checks[split+'_quoted_prior']=bool(n) and .05<=sum(r['label']=='quoted' for r in part)/n<=.15
        checks[split+'_languages']=all({r['language'] for r in part if r['label']==label}=={'en','zh','ja','ru'} for label in LABELS)
        checks[split+'_sources']={r['source_kind'] for r in part}=={'repository_docs','code_comments','issue_pr','email_ticket','mcp_description','mcp_return','memory','web'}
    positive=[r for r in rows if r['label']=='request' and r['split']!='public_heldout']
    ai=re.compile(r'\b(?:AI|assistant|agent|LLM|language model)\b|助手|模型|アシスタント|エージェント|ассистент|агент',re.I)
    without=sum(not ai.search(r['text']) for r in positive)/len(positive) if positive else 0
    checks['request_without_ai']=without>=.60
    corpus=[r for r in rows if r['split'] in targets];obfuscated=sum(r['transform']!='plain' for r in corpus)/len(corpus) if corpus else 0
    checks['obfuscation_fraction']=.15<=obfuscated<=.25
    checks['seven_obfuscation_types']=all(kind in {r['transform'] for r in corpus} for kind in ('unicode','split','comments','format','encoding','dilution','emoji'))
    feature_patterns={'env':r'(?<!\w)\.env\b','url':r'https?://','private_key_path':r'id_rsa','config':r'config\.toml','memory':r'memory/session\.json','credential_file':r'credentials\.json'}
    rates={}
    for feature,pattern in feature_patterns.items():
        rates[feature]={}
        for label in LABELS:
            part=[r for r in corpus if r['label']==label]
            rates[feature][label]=sum(bool(re.search(pattern,r['text'],re.I)) for r in part)/len(part) if part else 0
    checks['surface_gaps']=all(max(v.values())-min(v.values())<=.10 for v in rates.values())
    checks['unique_ids']=len({r['id'] for r in rows})==len(rows)
    for field in ('family','domain','source_dataset'):
        groups=collections.defaultdict(set)
        for row in rows:groups[row[field]].add(row['split'])
        checks['isolated_'+field]=all(len(v)==1 for v in groups.values())
    checks['public_test_present']=any(r['split']=='public_heldout' and r.get('upstream_dataset')=='BIPIA' for r in rows)
    checks['public_train_present']=any(r['split']=='train' and r.get('upstream_dataset')=='BIPIA' for r in rows)
    return {'passed':all(checks.values()),'checks':checks,'distribution':distribution,'request_without_ai_fraction':without,
            'obfuscation_fraction':obfuscated,'surface_presence_rates':rates}


def main(round_number):
    if round_number not in (1,2,3) or (OUT/'final-selection.json').exists():raise ValueError('Round unavailable after selection or outside the three-round budget')
    folder=OUT/f'round-{round_number}';rows=read(folder/'isolated.jsonl')
    isolation=json.loads((folder/'isolation.json').read_text());started=json.loads((folder/'generation-clock.json').read_text())['started_unix']
    if not isolation['passed'] or hashlib.sha256((folder/'isolated.jsonl').read_bytes()).hexdigest()!=isolation['isolated_sha256']:raise ValueError('Invalid isolation gate')
    minimums={'train':3000,**({'validation':600,'semantic_heldout':600} if round_number==1 else {})}
    available=collections.Counter(row['split'] for row in rows)
    prior_training=reused_training(folder);available['train']+=len(prior_training)
    if any(available[split]<minimum for split,minimum in minimums.items()):raise ValueError('Isolated candidate count is already below the admission minimum; add fresh data before paying for reviews')
    jobs=[(model,rows[i:i+8]) for i in range(0,len(rows),8) for model in MODELS]
    votes=[];errors=collections.Counter();done_n=0
    with (folder/'teacher-votes.jsonl').open('x',encoding='utf-8') as stream:
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            pending={};iterator=iter(jobs)
            for _ in range(24):
                job=next(iterator,None)
                if job:pending[pool.submit(judge,*job)]=job[0]
            while pending:
                if time.time()-started>=10700:
                    for future in pending:future.cancel()
                    raise TimeoutError('Round generation/review 3-hour budget; drain only running bounded requests')
                finished,_=concurrent.futures.wait(pending,timeout=20,return_when=concurrent.futures.FIRST_COMPLETED)
                for future in finished:
                    pending.pop(future);done_n+=1
                    try:
                        new=future.result();votes+=new
                        for item in new:stream.write(json.dumps(item,ensure_ascii=False)+'\n')
                        stream.flush()
                    except Exception as error:errors[type(error).__name__]+=1
                    job=next(iterator,None)
                    if job:pending[pool.submit(judge,*job)]=job[0]
                if finished and done_n%20<4:print(json.dumps({'review_batches_done':done_n,'batches_total':len(jobs),'errors':dict(errors),'seconds':time.time()-started}),flush=True)
    lookup={(v['model'],v['id']):v for v in votes};agreement=[];disagreements=[];missing=[]
    for row in rows:
        pair=[lookup.get((model,row['id'])) for model in MODELS]
        decision=admission_decision(row,pair)
        if decision=='missing':missing.append(row['id'])
        elif decision=='admit':agreement.append(row)
        else:disagreements.append(row['id'])
    # Later rounds reuse the exact independently generated, unanimously labeled
    # holdout. It is never regenerated or sent for a new vote after evaluation.
    reused=[]
    if round_number>1:
        reused=read(OUT/'semantic-heldout-frozen.jsonl')+read(OUT/'validation-frozen.jsonl')
        if not reused or any(r['split'] not in ('validation','semantic_heldout','public_heldout') for r in reused):raise ValueError('Frozen evaluation splits are unavailable')
        if any(r['split']!='train' for r in agreement):raise ValueError('Later rounds cannot replace frozen evaluation splits')
    # Keep every unanimous record initially: no post-hoc label/semantic surgery.
    corpus=prior_training+agreement+reused
    output=folder/'admitted.jsonl'
    with output.open('x',encoding='utf-8') as f:
        for row in corpus:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    quality=audit(corpus)
    result={'passed':quality['passed'],'isolated_n':len(rows),'fully_reviewed_n':len(rows)-len(missing),'unanimous_n':len(agreement),
        'agreement_rate':len(agreement)/(len(rows)-len(missing)) if len(rows)>len(missing) else 0.,'disagreement_n':len(disagreements),'missing_vote_n':len(missing),
        'discarded_disagreement_ids':disagreements,'discarded_missing_vote_ids':missing,'batch_failures':dict(errors),'audit':quality,
        'reused_training_n':len(prior_training),'reused_frozen_heldout_n':sum(r['split']!='validation' for r in reused),'reused_frozen_validation_n':sum(r['split']=='validation' for r in reused),'admitted_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'generation_wall_seconds':time.time()-started}
    (folder/'admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if round_number==1 and quality['passed']:
        with (OUT/'semantic-heldout-frozen.jsonl').open('x',encoding='utf-8') as f:
            for row in agreement:
                if row['split'] in ('semantic_heldout','public_heldout'):f.write(json.dumps(row,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('discarded_disagreement_ids','discarded_missing_vote_ids')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,default=1);main(p.parse_args().round)
