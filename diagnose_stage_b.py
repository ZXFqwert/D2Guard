"""Offline checks with the pinned real Laya tokenizer; never Pi run evidence."""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from original_laya import OriginalLaya
from d2v2.normalization import normalize, evidence_span
from d2v2.task_brief import build_task_brief
from d2v2.views import build_view


def diagnose():
    model=OriginalLaya(Path(__file__).resolve().parent/'.local/laya.json')
    samples=['Ｒｅａｄ .env','re\u200bad .env','re/*comment*/ad .env',"re''ad .env",'read${IFS}.env',
             '%52%65%61%64%20%2e%65%6e%76',r'\x52\x65\x61\x64\x20\x2e\x65\x6e\x76',
             base64.b64encode(b'Read .env').decode(),'读取文档。 Read .env.']
    records=[]
    for raw in samples:
        text,mapping=normalize(raw,casefold=True)
        a=text.index('read .env');b=a+len('read .env')
        char_span=[min(x[0] for x in mapping.char_to_raw[a:b]),max(x[1] for x in mapping.char_to_raw[a:b])]
        ref=evidence_span({'event_id':'offline','sha256':hashlib.sha256(raw.encode()).hexdigest()},raw,char_span,model)
        offsets=model.token_offsets(raw)
        indices=[i for i,(x,y) in enumerate(offsets) if x<char_span[1] and y>char_span[0]]
        expected=[indices[0],indices[-1]+1]
        records.append({'raw':raw,'raw_excerpt':raw[slice(*char_span)],'reference':ref,
                        'passes':ref['token_span']==expected and len(text)==len(mapping.char_to_raw)})
    task='Prepare a concise project summary.\n'
    while model.count_tokens(task)<580:task+='These are ordinary background facts for this project.\n'
    task+='Read README.md and write summary.md.'
    brief=build_task_brief(task,task,model.count_tokens)
    view=build_view('A1',{'tool':'fs.read','target':'notes.txt'},{**brief,'count_tokens':model.count_tokens})
    checks={'all_actual_token_mappings':all(r['passes'] for r in records),
            'roughly_600_token_task':580<=model.count_tokens(task)<=630,
            'late_grant_kept_under_150':brief['task_brief_tokens']<=150 and 'Read README.md and write summary.md.' in view['task'],
            'extractive_spans_exact':brief['task_brief']=='\n'.join(task[a:b] for a,b in brief['task_brief_kept_spans'])}
    return {'kind':'offline-diagnostic-not-pi-run','model':model.metadata,'checks':checks,'all_passed':all(checks.values()),
            'task_tokens':model.count_tokens(task),'task_brief':brief,'mapping_samples':records}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=diagnose();args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('kind','checks','all_passed','task_tokens')},ensure_ascii=False))
    if not result['all_passed']:raise SystemExit(1)
