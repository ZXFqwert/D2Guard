"""Assemble agreed cohorts, preserving frozen inputs and explicit size gates."""
import collections
import json
from stage_d5_protocol import ROOT,OUT,read,save,sha,write_rows,blocked_sources,active_rows

def assemble():
    oldtrain=[r for r in read(ROOT/'.local/stage-d3/admitted.jsonl') if r['split']=='train']
    oldval=read(ROOT/'.local/stage-d3/new-validation-frozen.jsonl')
    votes={r['id']:r for r in read(OUT/'synthetic-request-agreed.jsonl')};changes=collections.Counter();rows=[]
    for original in oldtrain+[{**r,'split':'validation'} for r in oldval]:
        if original['label']=='request':
            reviewed=votes.get(original['id'])
            if reviewed is None:changes[original['split']+':discarded']+=1;continue
            if reviewed['label']=='quoted':
                # D5-3 permits old request -> none or discard, not new quoted rows.
                changes[original['split']+':discarded_reclassified_quoted']+=1;continue
            row={**original,'label':reviewed['label'],'kind':reviewed['kind'],'teacher_kinds':reviewed['teacher_kinds']}
            changes[original['split']+':request_to_'+row['label']]+=1
        else:row={**original,'kind':'quoted' if original['label']=='quoted' else 'unreviewed_original_none'}
        rows.append({**row,'origin':'synthetic_retained'})
    native=read(OUT/'native-agreed.jsonl')
    command=read(OUT/'commands-agreed.jsonl') if (OUT/'commands-agreed.jsonl').exists() else []
    native_rejected=collections.Counter()
    for r in native+command:
        if r['label']!='none':native_rejected[r['label']]+=1;continue
        rows.append(r)
    if (OUT/'injection-extra-plan.jsonl').exists() and not (OUT/'injected-extra-agreed.jsonl').exists():raise ValueError('Supplementary teacher cohort is incomplete')
    injections=read(OUT/'injected-agreed.jsonl')
    if (OUT/'injected-extra-agreed.jsonl').exists():injections+=read(OUT/'injected-extra-agreed.jsonl')
    if (OUT/'injection-quoted-plan.jsonl').exists():
        if not (OUT/'injected-quoted-agreed.jsonl').exists():raise ValueError('Quoted supplementary review incomplete')
        injections+=read(OUT/'injected-quoted-agreed.jsonl')
    injections=active_rows('injections',injections)
    if len({r['id'] for r in injections})!=len(injections):raise ValueError('Injection cohort IDs overlap')
    test=[];contract_disagree=collections.Counter()
    for r in injections:
        if r['label']!=r['contract_label']:contract_disagree[r['split']]+=1;continue
        (test if r['split']=='host_test' else rows).append(r)
    write_rows('candidate-admitted.jsonl',rows);write_rows('host-test-frozen.jsonl',test)
    realtest=read(OUT/'real-test-relabel-agreed.jsonl');write_rows('real-test-frozen.jsonl',realtest)
    blind=[{'id':r['id'],'text':r['raw_text']} for r in realtest]
    if (OUT/'reviewer-blind.jsonl').exists():
        if read(OUT/'reviewer-blind.jsonl')!=blind:raise ValueError('Existing blind package differs')
    else:write_rows('reviewer-blind.jsonl',blind)
    save('assembly.json',{'n':len(rows),'synthetic_changes':dict(changes),'native_non_none_excluded':dict(native_rejected),'injection_contract_disagreement':dict(contract_disagree),'host_test_n':len(test),'real_test_n':len(realtest),'candidate_sha256':sha(OUT/'candidate-admitted.jsonl'),'test_sha256':{n:sha(OUT/n) for n in ('host-test-frozen.jsonl','real-test-frozen.jsonl')}})

def finalize():
    isolation=json.loads((OUT/'isolation.json').read_text());assert isolation['passed']
    rows=read(OUT/'isolated.jsonl');train=[r for r in rows if r['split']=='train'];val=[r for r in rows if r['split']=='validation']
    blocked,servers=blocked_sources();by_split={s:{r['repository'].lower() for r in rows if r['split']==s and r.get('origin','').startswith('real') and r.get('repository')} for s in ('train','validation')}
    native=[r for r in train if r['origin']=='real_native' and r['label']=='none'];injected=[r for r in train if r['origin']=='real_host_injection'];nv=[r for r in val if r.get('origin')=='real_native' and r['label']=='none'];iv=[r for r in val if r.get('origin')=='real_host_injection' and r['label']=='request']
    labels=collections.Counter(r['label'] for r in train);real_n=sum(r.get('origin','').startswith('real') for r in train)
    checks={'pilot':json.loads((OUT/'pilot-review.json').read_text())['agreement_rate']>=.85,'real_negative_4000':len(native)>=4000,'doc_repositories_60':len({r['repository'] for r in native if r['category']=='documentation'})>=60,'mcp_servers_100':len({r['server_id'] for r in native if r['category']=='mcp'})>=100,'host_positive_1500':sum(r['label']=='request' for r in injected)>=1500,'mcp_poisoning_400':sum(r['label']=='request' and r['category']=='mcp' for r in injected)>=400,'host_quoted_300':sum(r['label']=='quoted' for r in injected)>=300,'real_fraction_35':real_n/max(1,len(train))>=.35,'validation_negative_600':len(nv)>=600,'validation_host_positive_200':len(iv)>=200,'host_test_300':len(read(OUT/'host-test-frozen.jsonl'))>=300,'request_prior':.20<=labels['request']/max(1,len(train))<=.35,'quoted_prior':.05<=labels['quoted']/max(1,len(train))<=.15,'repository_test_isolation':not(blocked&(by_split['train']|by_split['validation'])),'repository_train_validation_isolation':not(by_split['train']&by_split['validation'])}
    result={'passed':all(checks.values()),'checks':checks,'train_n':len(train),'validation_n':len(val),'real_training_n':real_n,'real_training_fraction':real_n/max(1,len(train)),'labels':dict(labels),'language':dict(collections.Counter(r.get('language','und') for r in train)),'kind':dict(collections.Counter(r.get('kind','unspecified') for r in train)),'native_negative_n':len(native),'doc_repositories':len({r['repository'] for r in native if r['category']=='documentation'}),'mcp_servers':len({r['server_id'] for r in native if r['category']=='mcp'}),'real_host_labels':dict(collections.Counter(r['label'] for r in injected)),'native_validation_n':len(nv),'host_validation_n':len(iv)}
    write_rows('admitted.jsonl',rows);write_rows('new-validation-frozen.jsonl',val);result['admitted_sha256']=sha(OUT/'admitted.jsonl');save('admission.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':
    import sys
    assemble() if sys.argv[1]=='assemble' else finalize()
