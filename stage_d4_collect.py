"""Extract literal public documentation and tool descriptions; never execute source."""
import ast
import hashlib
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
from tokenizers import Tokenizer
from d2v2.semantic_view import semantic_view
from stage_d4_protocol import OUT,read,save,budget

def tool_literals(path):
    text=path.read_text(encoding='utf-8',errors='replace')
    found=[]
    if path.suffix=='.py':
        try:tree=ast.parse(text)
        except SyntaxError:return []
        definitions={n.name:n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        for n in ast.walk(tree):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Call) and isinstance(n.func.func,ast.Attribute) and n.func.func.attr=='tool' and n.args:
                target=n.args[0]
                key=target.attr if isinstance(target,ast.Attribute) else target.id if isinstance(target,ast.Name) else None
                definition=definitions.get(key)
                if definition:
                    description=ast.get_docstring(definition,clean=False);name=key
                    for kw in n.func.keywords:
                        if kw.arg=='name' and isinstance(kw.value,ast.Constant):name=kw.value.value
                        if kw.arg=='description' and isinstance(kw.value,ast.Constant):description=kw.value.value
                    if isinstance(description,str):found.append((name,description,definition.lineno,'registered bound method docstring'))
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                dec=[d for d in n.decorator_list if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in ('tool','add_tool')]
                if dec:
                    name=n.name;description=ast.get_docstring(n,clean=False)
                    for kw in dec[0].keywords:
                        if kw.arg=='name' and isinstance(kw.value,ast.Constant):name=kw.value.value
                        if kw.arg=='description' and isinstance(kw.value,ast.Constant):description=kw.value.value
                    if isinstance(name,str) and isinstance(description,str):found.append((name,description,n.lineno,'decorated tool docstring'))
            if isinstance(n,ast.Call) and ((isinstance(n.func,ast.Attribute) and n.func.attr=='Tool') or (isinstance(n.func,ast.Name) and n.func.id=='Tool')):
                values={k.arg:k.value.value for k in n.keywords if isinstance(k.value,ast.Constant)}
                if isinstance(values.get('name'),str) and isinstance(values.get('description'),str):found.append((values['name'],values['description'],n.lineno,'Tool declaration'))
    if path.suffix in ('.ts','.go'):
        literal=r'(?P<q>[\'"`])(?P<value>(?:(?!(?P=q)).|\n)*?)(?P=q)'
        # Only search description values following an actual tool registration/name.
        patterns=[r'\.(?:tool|registerTool|accountTool|userTool)\(\s*[\'"`]([^\'"`]+)[\'"`]\s*,\s*(?:\{\s*(?:title:\s*[^,]+,\s*)?description:\s*)?'+literal,
                  r'\bname:\s*[\'"`]([^\'"`]+)[\'"`]\s*,\s*(?:title:\s*[^,]+,\s*)?description:\s*'+literal,
                  r'\bName:\s*"([^"]+)"\s*,\s*Description:\s*(?:t\("[^"]+",\s*)?'+literal]
        for pattern in patterns:
            for m in re.finditer(pattern,text):
                desc=m.group('value')
                if '${' in desc:continue # Dynamic interpolation is not a literal description.
                found.append((m.group(1),desc,text.count('\n',0,m.start())+1,'literal tool registration'))
    return [x for x in found if 20<=len(x[1])<=12000]

def server_for(repo,rel):
    parts=rel.parts
    if repo=='awslabs/mcp':
        return repo+'/'+parts[1] if len(parts)>2 and parts[0]=='src' and parts[1].endswith('mcp-server') else None
    if repo.startswith('modelcontextprotocol/servers'):
        return repo+'/'+parts[1] if len(parts)>2 and parts[0]=='src' else None
    if repo=='cloudflare/mcp-server-cloudflare':
        return repo+'/'+parts[1] if len(parts)>2 and parts[0]=='apps' and parts[1] not in ('demo-day','sandbox-container') else None
    if repo=='neo4j-contrib/mcp-neo4j':return repo+'/'+parts[1] if len(parts)>2 and parts[0]=='servers' else None
    if repo.endswith(('/python-sdk','/typescript-sdk','/fastmcp')):return None
    return repo

def slices(tok,text,source):
    # Cut original spans by semantic-token offsets; preserve raw text in local evidence.
    text=semantic_view(text)
    encoded=tok.encode(text,add_special_tokens=False);offsets=encoded.offsets
    start=0
    while start<len(offsets):
        end=min(start+350,len(offsets))
        piece=text[offsets[start][0]:offsets[end-1][1]]
        while len(tok.encode(json.dumps({'source_type':source,'fragment':piece},ensure_ascii=False),add_special_tokens=False).ids)>384:
            end-=1;piece=text[offsets[start][0]:offsets[end-1][1]]
        if len(piece.strip())>=60:yield piece
        start=end

def collect(supplement=False):
    budget(reserve=500)
    tok=Tokenizer.from_file(str(OUT/'tokenizer.json'));tok.no_truncation();tok.no_padding()
    sources=json.loads((OUT/'sources.json').read_text());rows=[];toolmap=defaultdict(list);seen=set()
    if supplement:
        sources+=json.loads((OUT/'reserve-sources.json').read_text())
        seen={r['raw_sha256'] for r in read(OUT/'candidates.jsonl')}
        save('supplement-plan.json',{'reason':'Admission-only volume shortfall; no model predictions produced','documentation_new_cap_per_repository':24,'mcp_new_fragment_cap_per_server':3,'sampling':'same deterministic file/name order; exclude all original candidate hashes including missing/disagreed votes','training_data_added':0})
    prior=set()
    for folder in ('stage-d2','stage-d3'):
        # Exact semantic input exclusion over previous data; no labels or mistakes inspected.
        for filename in ('admitted.jsonl','train.jsonl','new-validation-frozen.jsonl','old-validation.jsonl','frozen-heldout.jsonl','gold.jsonl'):
            p=OUT.parent/folder/filename
            if p.exists():
                for r in read(p):prior.add(hashlib.sha256(semantic_view(r.get('raw_text',r.get('text',''))).encode()).hexdigest())
    rejected=Counter()
    def add(text,meta):
        for i,part in enumerate(slices(tok,text,meta['source_type'])):
            digest=hashlib.sha256(part.encode()).hexdigest()
            if digest in prior:rejected['previous_exact']+=1;continue
            if digest in seen:rejected['duplicate']+=1;continue
            seen.add(digest);rows.append({**meta,'id':'d4-'+digest[:20],'raw_text':part,'text':part,'language':'en','slice':i,'raw_sha256':digest})
    doclist=[]
    for src in sorted(sources,key=lambda x:x['repository']):
        if 'error' in src:continue
        repo=src['repository'];folder=OUT/'sources'/repo.replace('/','__')/'files'
        common={'repository':repo,'commit':src['commit'],'licenses':src.get('licenses',[])}
        if src['kind']=='documentation':
            files=[]
            for p in folder.rglob('*'):
                if not p.is_file() or p.suffix.lower() not in ('.md','.rst','.txt'):continue
                rel=p.relative_to(folder).as_posix();low=rel.lower()
                category=next((k for k in ('readme','contributing','changelog','issue_template','pull_request_template') if k in low),None)
                if category is None and ('doc' in low and any(k in low for k in ('api','reference','usage','guide','tutorial','doc'))):category='api_docs'
                if category and 'locale/' not in low:files.append((category,rel,p))
            count=Counter();before=len(rows)
            for category,rel,p in sorted(files):
                if count[category]>=30:continue
                text=p.read_text(encoding='utf-8',errors='replace');start=len(rows)
                # Deterministic first three slices per file, no model-based filtering.
                for part in list(slices(tok,text,'LOCAL_FILE'))[:3]:
                    add(part,{**common,'category':'documentation','document_kind':category,'source_type':'LOCAL_FILE','path':rel,'url':f'https://github.com/{repo}/blob/{src["commit"]}/{rel}'})
                count[category]+=len(rows)-start
                if len(rows)-before>=(24 if supplement else 48):break
            doclist.append({**common,'fragments':len(rows)-before,'document_kinds':dict(count)})
        else:
            for p in folder.rglob('*'):
                if not p.is_file() or p.suffix not in ('.py','.ts','.go'):continue
                rel=p.relative_to(folder)
                if any(x in ('tests','test','__tests__','examples','node_modules') for x in rel.parts) or any(x in p.name for x in ('.test.','.spec.','test_','_test.')):continue
                server=server_for(repo,rel)
                if not server:continue
                for name,description,line,method in tool_literals(p):
                    toolmap[server].append((name,description,{**common,'category':'mcp','source_type':'MCP_DESC','server_id':server,'path':rel.as_posix(),'line':line,'extraction':method,'url':f'https://github.com/{repo}/blob/{src["commit"]}/{rel.as_posix()}#L{line}'}))
    inventory=[]
    for server,tools in sorted(toolmap.items()):
        before=len(rows);names=set()
        for name,description,meta in sorted(tools,key=lambda x:(x[0],x[2]['path'])):
            if name in names:continue
            names.add(name)
            payload=json.dumps({'name':name,'description':description},ensure_ascii=False)
            # Long literal JSON is sliced like documentation; full literal retained privately.
            add(payload,{**meta,'literal_tool_json':payload})
            if len(rows)-before>=3:break
        if len(rows)>before:inventory.append({'server_id':server,'fragments':len(rows)-before,'repository':tools[0][2]['repository'],'commit':tools[0][2]['commit'],'licenses':tools[0][2]['licenses']})
    save('source-inventory-supplement.json' if supplement else 'source-inventory.json',{'documents':doclist,'mcp_servers':inventory,'distinct_mcp_servers':len(inventory),'source_rejections':dict(rejected),'extraction_note':'name and description literal fields only; schemas not reconstructed; no upstream code executed'})
    with (OUT/('supplement-candidates.jsonl' if supplement else 'public-candidates.jsonl')).open('w',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(json.dumps({'n':len(rows),'category':dict(Counter(r['category'] for r in rows)),'servers':len(inventory),'document_repositories':len(doclist),'rejected':dict(rejected)}),flush=True)

if __name__=='__main__':
    import sys
    collect('--supplement' in sys.argv)
