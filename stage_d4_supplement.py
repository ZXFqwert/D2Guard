"""Volume-only extension of the new test collection, before any model evaluation."""
import hashlib
import json
from collections import Counter
from tokenizers import Tokenizer
from stage_d4_protocol import OUT,read,save,sha
from stage_d4_collect import slices

def main():
    assert not (OUT/'evaluation-started.json').exists()
    old=read(OUT/'candidates.jsonl');rows=read(OUT/'supplement-candidates.jsonl');seen={r['raw_sha256'] for r in old+rows}
    tok=Tokenizer.from_file(str(OUT/'tokenizer.json'));tok.no_truncation();tok.no_padding()
    commands=json.loads((OUT/'command-outputs-supplement.json').read_text())
    for r in commands:
        for i,part in enumerate(list(slices(tok,'stdout:\n'+r['stdout']+'\nstderr:\n'+r['stderr'],'TOOL_OUTPUT'))[:3]):
            digest=hashlib.sha256(part.encode()).hexdigest()
            if digest in seen:continue
            seen.add(digest);rows.append({'id':'d4-'+digest[:20],'raw_text':part,'text':part,'language':'en','source_type':'TOOL_OUTPUT','category':'command','command_id':r['id'],'repository':r['repository'],'commit':r['commit'],'licenses':r['licenses'],'url':r['url'],'command':r['command'],'returncode':r['returncode'],'sandbox':r['sandbox'],'slice':i,'raw_sha256':digest})
    with (OUT/'supplement-frozen.jsonl').open('x',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    save('supplement-freeze.json',{'n':len(rows),'category':dict(Counter(r['category'] for r in rows)),'original_candidate_n':len(old),'union_candidate_n':len(old)+len(rows),'sha256':sha(OUT/'supplement-frozen.jsonl'),'basis':'Only missing admission counts: initial docs486<600, distinct servers94<100. No classifier predictions or evaluation results available. All initial valid agreements retained; no previous fragment rejudged. Additional actual wc output commands37.'})
    print(json.dumps({'n':len(rows),'category':dict(Counter(r['category'] for r in rows))}))

if __name__=='__main__':main()
