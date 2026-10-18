"""D5 user-authorized dean decisions, with original votes preserved as provenance."""
import collections,json
from stage_d5_protocol import OUT,read,save,sha,write_rows,active_rows,teacher_role,KINDS,RUBRIC

DECISIONS=('dean-early-decisions.jsonl','dean-host-train-decisions-0.jsonl','dean-host-train-decisions-1.jsonl','dean-host-train-decisions-2.jsonl','dean-host-train-decisions-3.jsonl','dean-host-train-decisions-4.jsonl','dean-host-train-decisions-5.jsonl','dean-host-test-decisions.jsonl')

def load_decisions():
    result={}
    for name in DECISIONS:
        path=OUT/name
        if not path.exists():continue
        for row in read(path):
            if KINDS.get(row.get('kind'))!=row.get('label') or not row.get('reason'):raise ValueError('Invalid dean decision')
            if row.get('reviewer')!='gpt-6.1-sol' or row.get('reasoning_effort')!='low':raise ValueError('Wrong reviewer')
            if row['id'] in result:raise ValueError('Duplicate dean decision')
            result[row['id']]=row
    return result

def adjudicated_row(row,decision,votes):
    return {**row,'original_label':row['label'],'label':decision['label'],'kind':decision['kind'],
            'teacher_kinds':[v['kind'] for v in votes],'original_teacher_votes':votes,
            'review_status':'dean_adjudicated','adjudication':decision}

def legacy_choice(row,votes):
    by={teacher_role(v['model']):v for v in votes};a=by.get('deepseek-v4.1-flash')
    b=by.get('glm-5.3-flash') or by.get('mimo-v2.5')
    if not a or not b or a['label']!=b['label'] or a['label']!=row['contract_label']:return None
    return {**row,'original_label':row['label'],'label':a['label'],'kind':a['kind'] if a['kind']==b['kind'] else 'mixed_none',
            'teacher_kinds':[a['kind'],b['kind']],'original_teacher_votes':votes,'review_status':'legacy_qualified_reused',
            'reuse_basis':'Existing qualified host review accepted by dean; not claimed as direct dean reading'}

def main(finalize=False):
    decisions=load_decisions();summary={};outputs={}
    for name in ('synthetic-request','injected','injected-extra','injected-quoted'):
        rows=active_rows(name,read(OUT/(name+'.jsonl')));by=collections.defaultdict(list)
        for vote in read(OUT/(name+'-votes.jsonl')):by[vote['id']].append(vote)
        kept=[];deferred=0
        for row in rows:
            d=decisions.get(row['id']);vs=by[row['id']]
            if d:out=adjudicated_row(row,d,vs)
            elif name=='synthetic-request' or row['split']=='host_test':out=None
            else:out=legacy_choice(row,vs)
            if out is None:deferred+=1
            else:kept.append(out)
        counts=collections.Counter(r['split']+':'+r['label'] for r in kept)
        summary[name]={'n':len(rows),'reviewed_n':len(kept),'deferred_n':deferred,'split_labels':dict(counts),
                       'review_status':dict(collections.Counter(r['review_status'] for r in kept))}
        outputs[name]=kept
    record={'authority':'gpt-6.1-sol low, explicit user authorization','dual_teacher_gate_superseded':True,'model_acceptance_unchanged':True,'queues':summary,
            'decision_files':{n:sha(OUT/n) for n in DECISIONS if (OUT/n).exists()},'original_votes_preserved':True,'source_sha256':{n:sha(OUT/n) for n in ('synthetic-request.jsonl','injected.jsonl','injected-extra.jsonl','injected-quoted.jsonl','synthetic-request-votes.jsonl','injected-votes.jsonl','injected-extra-votes.jsonl','injected-quoted-votes.jsonl')}}
    save('dean-admission-preview.json',record)
    print(json.dumps(summary),flush=True)
    if not finalize:return
    if len([r for r in outputs['injected'] if r['split']=='host_test'])!=500:raise ValueError('Blind host test review incomplete')
    for name,rows in outputs.items():
        if (OUT/(name+'-agreed.jsonl')).exists() or (OUT/(name+'-review.json')).exists():raise ValueError('Do not overwrite finalized review')
    for name,rows in outputs.items():
        write_rows(name+'-agreed.jsonl',rows)
        meta=summary[name]
        save(name+'-review.json',{'n':meta['n'],'fully_reviewed':meta['reviewed_n'],'agreement_n':len(rows),
            'agreement_rate':None,'agreement_rate_valid':None,'missing_n':meta['deferred_n'],'kind_disagreements':None,
            'kind':dict(collections.Counter(r['kind'] for r in rows)),'labels':dict(collections.Counter(r['label'] for r in rows)),
            'review_method':'dean final decisions and qualified legacy reuse; agreement rates not applicable',
            'prompt_sha256':__import__('hashlib').sha256(RUBRIC.encode()).hexdigest(),'errors_n':None})
    save('dean-finalization.json',record)

if __name__=='__main__':
    import sys
    main('--finalize' in sys.argv)
