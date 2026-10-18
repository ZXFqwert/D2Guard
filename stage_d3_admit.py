"""Preserve teacher votes; accept unanimous labels or authorized agent rulings."""
import collections
import concurrent.futures
import hashlib
import json
import re
import time
from stage_d3_protocol import OUT, read, sha, budget, plan
from stage_d3_teacher import MODELS, judge, digest
from stage_d2_metrics import LABELS


def decision(row,pair):
    if len(pair)!=2 or not all(pair):return 'missing'
    if {v['model'] for v in pair}!=set(MODELS):raise ValueError('Two registered independent teachers required')
    if any(v['input_sha256']!=digest(row) for v in pair):raise ValueError('Teacher hash mismatch')
    return 'admit' if all(v['label']==row['label'] for v in pair) else 'disagree'


def adjudicated_row(row,pair,ruling):
    if decision(row,pair)!='disagree':raise ValueError('Agent ruling requires two complete disagreeing votes')
    if ruling['input_sha256']!=digest(row) or ruling['id']!=row['id']:
        raise ValueError('Adjudicated text changed')
    if ruling['label']=='abstain':return None
    if ruling['label'] not in LABELS:raise ValueError('Invalid adjudicated label')
    return {**row,'contract_label':row['label'],'label':ruling['label'],
            'original_teacher_votes':pair,'agent_adjudication':ruling}


def adjudications():
    result={};evidence={}
    for folder in sorted((OUT/'adjudication').glob('batch-*')):
        assignment=json.loads((folder/'assignments.json').read_text(encoding='utf-8'))
        if sha(folder/'rubric.txt')!=assignment['rubric_sha256']:raise ValueError('Adjudication rubric changed')
        for i in (1,2,3):
            blind=folder/('blind-'+str(i)+'.jsonl');judged=folder/('judgments-'+str(i)+'.jsonl')
            if sha(blind)!=assignment['blind_sha256'][str(i)]:raise ValueError('Adjudication input changed')
            if not judged.exists():raise ValueError('Assigned agent adjudication incomplete')
            inputs={r['id']:r for r in read(blind)};items=read(judged)
            if len(items)!=len(inputs) or {r['id'] for r in items}!=set(inputs):
                raise ValueError('Adjudication coverage mismatch')
            for r in items:
                if (r['id'] in result or r['input_sha256']!=inputs[r['id']]['input_sha256']
                    or r['label'] not in (*LABELS,'abstain') or not r.get('reason') or not r.get('reviewer')):
                    raise ValueError('Invalid agent adjudication')
                result[r['id']]=r
            evidence[str(judged.relative_to(OUT))]=sha(judged)
    return result,evidence


def balance_generators(rows):
    kept=[];removed=collections.Counter()
    for split in ('train','validation'):
        groups=collections.defaultdict(list)
        for row in rows:
            if row['split']==split:groups[row['generator']].append(row)
        if len(groups)!=2:
            kept.extend(r for values in groups.values() for r in values);continue
        limit=int(min(map(len,groups.values()))*1.5)
        for generator,part in groups.items():
            part.sort(key=lambda r:hashlib.sha256(r['id'].encode()).hexdigest())
            kept.extend(part[:limit]);removed[split+':'+generator]=max(0,len(part)-limit)
    return kept,dict(removed)


def audit(retained,new):
    corpus=retained+new;checks={};distribution={}
    for split,minimum in [('train',12204),('validation',900)]:
        part=[r for r in corpus if r['split']==split];n=len(part)
        distribution[split]={field:dict(collections.Counter(r.get(field) for r in part)) for field in
                              ('label','language','source_kind','transform','generator')}
        checks[split+'_minimum']=n>=minimum
        checks[split+'_request_prior']=bool(n) and .20<=sum(r['label']=='request' for r in part)/n<=.35
        checks[split+'_quoted_prior']=bool(n) and .05<=sum(r['label']=='quoted' for r in part)/n<=.15
        checks[split+'_languages']=all({r['language'] for r in part if r['label']==label}=={'en','zh','ja','ru'} for label in LABELS)
        checks[split+'_sources']={r['source_kind'] for r in part}=={'repository_docs','code_comments','issue_pr','email_ticket','mcp_description','mcp_return','memory','web'}
        fresh=[r for r in new if r['split']==split]
        counts=collections.Counter(r['generator'] for r in fresh)
        checks[split+'_generator_balance']=len(counts)==2 and all(.40<=c/len(fresh)<=.60 for c in counts.values())
    checks['retained_8204']=len(retained)==8204
    checks['new_train_4000']=sum(r['split']=='train' for r in new)>=4000
    checks['unique_ids']=len({r['id'] for r in corpus})==len(corpus)
    for field in ('family','domain','source_dataset'):
        assigned=collections.defaultdict(set)
        for r in corpus:assigned[r[field]].add(r['split'])
        checks['isolated_'+field]=all(len(v)==1 for v in assigned.values())
    styles=plan()['styles'];train_styles={r['style_id'] for r in new if r['split']=='train'};val_styles={r['style_id'] for r in new if r['split']=='validation'}
    checks['style_coverage']=len(train_styles)>=40 and len(val_styles)>=12 and not train_styles&val_styles
    checks['style_registry']=all(r['style_id'] in {s['id'] for s in styles if s['split']==r['split']} for r in new)
    positive=[r for r in corpus if r['label']=='request']
    ai=re.compile(r'\b(?:AI|assistant|agent|LLM|language model)\b|助手|模型|アシスタント|エージェント|ассистент|агент',re.I)
    no_ai=sum(not ai.search(r['text']) for r in positive)/len(positive) if positive else 0
    checks['request_without_ai']=no_ai>=.60
    obf=sum(r['transform']!='plain' for r in corpus)/len(corpus) if corpus else 0
    checks['obfuscation_fraction']=.15<=obf<=.25
    checks['seven_types']=all(k in {r['transform'] for r in corpus} for k in ('unicode','split','comments','format','encoding','dilution','emoji'))
    train=[r for r in corpus if r['split']=='train']
    dilution=sum(r['transform']=='dilution' for r in train)/len(train) if train else 0
    checks['long_dilution_minimum']=dilution>=.05
    patterns={'env':r'(?<!\w)\.env\b','url':r'https?://','private_key_path':r'id_rsa','config':r'config\.toml','memory':r'memory/session\.json','credential_file':r'credentials\.json'}
    rates={key:{label:sum(bool(re.search(pattern,r['text'],re.I)) for r in corpus if r['label']==label)/max(1,sum(r['label']==label for r in corpus)) for label in LABELS} for key,pattern in patterns.items()}
    checks['surface_gaps']=all(max(v.values())-min(v.values())<=.10 for v in rates.values())
    return {'passed':all(checks.values()),'checks':checks,'distribution':distribution,'request_without_ai_fraction':no_ai,
            'obfuscation_fraction':obf,'long_dilution_fraction':dilution,'surface_presence_rates':rates,
            'new_style_counts':{'train':len(train_styles),'validation':len(val_styles)}}


def main():
    isolation=json.loads((OUT/'isolation.json').read_text(encoding='utf-8'))
    if not isolation['passed'] or sha(OUT/'isolated.jsonl')!=isolation['isolated_sha256']:raise ValueError('Isolation gate invalid')
    rows=read(OUT/'isolated.jsonl');retained=read(OUT/'retained-training.jsonl')
    available=collections.Counter(r['split'] for r in rows)
    streamed=OUT/'collection.json'
    if streamed.exists():
        result=json.loads(streamed.read_text(encoding='utf-8'))
        if not result['complete'] or sha(OUT/'teacher-votes-combined.jsonl')!=result['teacher_votes_sha256']:
            raise ValueError('Incomplete or changed streaming votes')
        if sha(OUT/'generated-combined.jsonl')!=result['generated_sha256']:raise ValueError('Generated input changed')
        finalize(rows,retained,read(OUT/'teacher-votes-combined.jsonl'),result['errors'])
        return
    if (OUT/'continuation-authorization.json').exists():
        raise ValueError('Existing-data continuation cannot request new teacher votes')
    if available['train']<4000 or available['validation']<900:
        raise ValueError('Insufficient isolated candidates; no cloud review paid')
    jobs=[(model,rows[i:i+4]) for i in range(0,len(rows),4) for model in MODELS]
    votes=[];errors=collections.Counter();done_n=0
    with (OUT/'teacher-votes.jsonl').open('x',encoding='utf-8') as stream, concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        iterator=iter(jobs);pending={}
        def submit():
            job=next(iterator,None)
            if job is not None:
                budget(reserve=100);pending[pool.submit(judge,*job)]=job[0]
        for _ in range(24):submit()
        while pending:
            done,_=concurrent.futures.wait(pending,timeout=20,return_when=concurrent.futures.FIRST_COMPLETED)
            budget(reserve=100)
            for future in done:
                model=pending.pop(future);done_n+=1
                try:
                    new=future.result();votes.extend(new)
                    for v in new:stream.write(json.dumps(v,ensure_ascii=False)+'\n')
                    stream.flush()
                except Exception as e:errors[model+':'+type(e).__name__]+=1
                submit()
            progress={'completed_batches':done_n,'total_batches':len(jobs),'errors':dict(errors)}
            (OUT/'review-progress.json').write_text(json.dumps(progress,indent=2),encoding='utf-8')
            if done and done_n%100<24:print(json.dumps(progress),flush=True)
    finalize(rows,retained,votes,dict(errors))


def finalize(rows,retained,votes,errors):
    lookup={(v['model'],v['id']):v for v in votes};accepted=[];rejected=collections.Counter()
    rulings,ruling_evidence=adjudications();unanimous=0;adjudicated=0;relabeled=0
    if len(lookup)!=len(votes):raise ValueError('Duplicate teacher votes')
    for r in rows:
        pair=[lookup.get((model,r['id'])) for model in MODELS]
        status=decision(r,pair)
        if status=='admit':accepted.append(r);unanimous+=1
        elif status=='disagree' and r['id'] in rulings:
            ruling=rulings[r['id']]
            revised=adjudicated_row(r,pair,ruling)
            if revised is None:rejected['agent_abstain']+=1;continue
            accepted.append(revised)
            adjudicated+=1;relabeled+=int(ruling['label']!=r['label'])
        else:rejected[status]+=1
    before_balance=len(accepted)
    accepted,balance_removed=balance_generators(accepted)
    quality=audit(retained,accepted)
    with (OUT/'admitted.jsonl').open('x',encoding='utf-8') as f:
        for r in retained+accepted:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    result={'passed':quality['passed'],'isolated_n':len(rows),'new_admitted_n':len(accepted),
            'fully_reviewed_n':len(rows)-rejected['missing'],'agreement_rate':unanimous/max(1,len(rows)-rejected['missing']),
            'unanimous_n':unanimous,'agent_adjudicated_n':adjudicated,'agent_relabeled_n':relabeled,
            'before_generator_balance_n':before_balance,'generator_balance_removed':balance_removed,
            'final_agent_adjudicated_n':sum('agent_adjudication' in r for r in accepted),
            'final_agent_relabeled_n':sum('contract_label' in r and r['contract_label']!=r['label'] for r in accepted),
            'adjudication_evidence':ruling_evidence,'teacher_policy':'Unanimous contract + two teachers, or user-authorized blind agent ruling on complete disagreeing votes; missing votes still discarded',
            'discarded':dict(rejected),'batch_errors':dict(errors),'quality':quality,'admitted_sha256':sha(OUT/'admitted.jsonl'),
            'teachers':MODELS,'data_elapsed_seconds':time.time()-plan()['started_unix']}
    (OUT/'admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
