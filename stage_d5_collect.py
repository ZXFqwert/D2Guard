"""Extract fixed raw source spans and literal tools without executing repositories."""
import ast
import collections
import hashlib
import json
import re
from pathlib import Path
from tokenizers import Tokenizer
from d2v2.semantic_view import semantic_view
from stage_d4_collect import slices,tool_literals
from stage_d5_protocol import ROOT,OUT,budget,read,save,write_rows,check_repository

def collect(pilot_only=False):
    tok=Tokenizer.from_file(str(ROOT/'.local/stage-d4/tokenizer.json'));tok.no_truncation();tok.no_padding()
    sources=json.loads((OUT/'sources.json').read_text());rows=[];seen=set();inventory=[]
    if pilot_only:sources=[s for s in sources if s['kind']=='documentation' and s.get('accepted_license') and s['split']=='train'][:16]
    def add(text,meta,limit=5):
        for index,piece in enumerate(slices(tok,text,meta['source_type'])):
            if index>=limit:break
            digest=hashlib.sha256(piece.encode()).hexdigest()
            if digest in seen:continue
            seen.add(digest);rows.append({**meta,'id':'d5-real-'+digest[:24],'raw_text':piece,'text':semantic_view(piece),'raw_sha256':digest,'language':'und','family':'real:'+meta['repository']})
    for src in sources:
        budget(200)
        if not src.get('accepted_license'):continue
        repo=src['repository'];check_repository(repo);folder=OUT/'sources'/repo.replace('/','__')/'files';before=len(rows)
        common={k:src[k] for k in ('repository','commit','licenses','split','kind')};common['category']=common.pop('kind');common['origin']='real_native'
        if src['kind']=='documentation':
            files=[]
            for p in folder.rglob('*'):
                if not p.is_file():continue
                if pilot_only and p.suffix not in ('.md','.rst','.txt'):continue
                rel=p.relative_to(folder).as_posix();low=rel.lower()
                if any(k in low for k in ('locale/','translations/','_static/')):continue
                category=next((k for k in ('readme','contributing','changelog','issue_template','pull_request_template') if k in low),None)
                if p.suffix in ('.md','.rst','.txt') and (category or 'doc' in low):files.append((category or 'api_reference',rel,p))
                elif p.suffix=='.py' and 'test' not in low:files.append(('code_comment',rel,p))
            counts=collections.Counter()
            # Cycle categories, not an API-only alphabetic prefix.
            buckets=collections.defaultdict(list)
            for item in sorted(files):buckets[item[0]].append(item)
            for j in range(max((len(v) for v in buckets.values()),default=0)):
                for category,items in sorted(buckets.items()):
                    if j>=len(items) or counts[category]>=50:continue
                    _,rel,p=items[j];raw=p.read_text(encoding='utf-8',errors='replace')[:24000]
                    if category=='code_comment':
                        try:tree=ast.parse(raw);parts=[ast.get_docstring(n,clean=False) for n in ast.walk(tree) if isinstance(n,(ast.Module,ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))];raw='\n\n'.join(x for x in parts if x)
                        except (SyntaxError,RecursionError):continue
                    n=len(rows);add(raw,{**common,'source_type':'LOCAL_FILE','document_kind':category,'path':rel,'url':f'https://github.com/{repo}/blob/{src["commit"]}/{rel}'},limit=4);counts[category]+=len(rows)-n
                if len(rows)-before>=(20 if pilot_only else 140):break
        else:
            for p in sorted(folder.rglob('*')):
                if not p.is_file() or p.suffix not in ('.py','.ts','.go'):continue
                rel=p.relative_to(folder).as_posix()
                if any(x in rel.lower().split('/') for x in ('tests','test','__tests__','examples')):continue
                try:tools=tool_literals(p)
                except (ValueError,RecursionError):continue
                for name,desc,line,method in tools:
                    payload=json.dumps({'name':name,'description':desc},ensure_ascii=False)
                    add(payload,{**common,'source_type':'MCP_DESC','server_id':src['server_id'],'path':rel,'tool_name':name,'literal_tool_json':payload,'url':f'https://github.com/{repo}/blob/{src["commit"]}/{rel}#L{line}','extraction':method},limit=2)
                if len(rows)-before>=18:break
        inventory.append({**src,'fragment_n':len(rows)-before})
    if not pilot_only:
        write_rows('real-candidates.jsonl',rows);save('inventory.json',inventory)
    # Pilot is fixed before any teacher output. Keep it separate from later training/validation.
    pilot=[]
    for category,n in ([('documentation',200)] if pilot_only else [('documentation',140),('mcp',60)]):
        eligible=[r for r in rows if r['category']==category and r['split']=='train'];eligible.sort(key=lambda r:hashlib.sha256(('pilot'+r['id']).encode()).hexdigest());pilot+=eligible[:n]
    if len(pilot)!=200:raise ValueError('Need 200 real pilot examples')
    if not (OUT/'pilot.jsonl').exists():write_rows('pilot.jsonl',[{**r,'split':'pilot'} for r in pilot])
    save('collection.json',{'n':len(rows),'category':dict(collections.Counter(r['category'] for r in rows)),'document_repositories':len({r['repository'] for r in rows if r['category']=='documentation' and r['split']=='train'}),'mcp_servers':len({r['server_id'] for r in rows if r['category']=='mcp' and r['split']=='train'}),'pilot_n':len(pilot)})
    print((OUT/'collection.json').read_text(),flush=True)

if __name__=='__main__':
    import sys
    collect('--pilot' in sys.argv)
