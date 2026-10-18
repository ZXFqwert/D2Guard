"""Freeze public source candidates and real sandbox outputs before teacher review."""
import hashlib
import json
from collections import Counter
from tokenizers import Tokenizer
from stage_d4_protocol import OUT,read,save,sha,budget
from stage_d4_collect import slices

def main():
    budget(reserve=600);rows=read(OUT/'public-candidates.jsonl');tok=Tokenizer.from_file(str(OUT/'tokenizer.json'));tok.no_truncation();tok.no_padding()
    commands=json.loads((OUT/'command-outputs.json').read_text());seen={r['raw_sha256'] for r in rows}
    for r in commands:
        text='stdout:\n'+r['stdout']+'\nstderr:\n'+r['stderr']
        for i,part in enumerate(list(slices(tok,text,'TOOL_OUTPUT'))[:3]):
            digest=hashlib.sha256(part.encode()).hexdigest()
            if digest in seen:continue
            seen.add(digest)
            rows.append({'id':'d4-'+digest[:20],'raw_text':part,'text':part,'language':'en','source_type':'TOOL_OUTPUT','category':'command','command_id':r['id'],'repository':r['repository'],'commit':r['commit'],'licenses':r['licenses'],'url':r['url'],'command':r['command'],'returncode':r['returncode'],'sandbox':r['sandbox'],'slice':i,'raw_sha256':digest})
    categories=Counter(r['category'] for r in rows)
    servers={r['server_id'] for r in rows if r['category']=='mcp'}
    source_outputs={r['command_id'] for r in rows if r['category']=='command'}
    print(json.dumps({'candidate_categories':dict(categories),'servers':len(servers),'commands':len(source_outputs)}),flush=True)
    if categories['documentation']<600 or len(servers)<100 or len(source_outputs)<100:raise ValueError('Collection size below preregistered minimum')
    with (OUT/'candidates.jsonl').open('x',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    save('candidate-freeze.json',{'n':len(rows),'categories':dict(categories),'distinct_servers':len(servers),'distinct_commands':len(source_outputs),'actual_commands_executed':len(commands),'nonzero_command_exits':sum(r['returncode']!=0 for r in commands),'sha256':sha(OUT/'candidates.jsonl'),'selection':'deterministic file order and first slices, before teacher votes or model predictions'})
    print(json.dumps({'n':len(rows),'category':dict(categories),'servers':len(servers),'commands':len(source_outputs)}))

if __name__=='__main__':main()
