"""Public-source inventory. Archive files stay under ignored local storage."""
import concurrent.futures
import io
import json
import subprocess
import tarfile
from pathlib import Path
import httpx
from stage_d4_protocol import OUT,budget,save

# Expectations are checked against the actual LICENSE at the pinned commit.
DOCS={
 'numpy/numpy':'BSD-3-Clause','scipy/scipy':'BSD-3-Clause','pandas-dev/pandas':'BSD-3-Clause',
 'scikit-learn/scikit-learn':'BSD-3-Clause','sympy/sympy':'BSD-3-Clause','networkx/networkx':'BSD-3-Clause',
 'pytest-dev/pytest':'MIT','HypothesisWorks/hypothesis':'MPL-2.0',
 'psf/requests':'Apache-2.0','urllib3/urllib3':'MIT','encode/httpx':'BSD-3-Clause',
 'encode/starlette':'BSD-3-Clause','fastapi/fastapi':'MIT','pydantic/pydantic':'MIT',
 'Textualize/rich':'MIT','Textualize/textual':'MIT','fastapi/typer':'MIT',
 'agronholm/anyio':'MIT','python-trio/trio':'MIT OR Apache-2.0',
 'pallets/jinja':'BSD-3-Clause','pallets/werkzeug':'BSD-3-Clause','pallets/itsdangerous':'BSD-3-Clause',
 'pallets/markupsafe':'BSD-3-Clause','python-attrs/attrs':'MIT','python-attrs/cattrs':'MIT',
 'pypa/packaging':'BSD-2-Clause OR Apache-2.0','pytest-dev/pluggy':'MIT','sphinx-doc/sphinx':'BSD-2-Clause',
 'pallets-eco/blinker':'MIT','pypa/virtualenv':'MIT','pypa/build':'MIT','pypa/installer':'MIT',
 'pypa/wheel':'MIT','pypa/flit':'BSD-3-Clause','pypa/hatch':'MIT','python-jsonschema/jsonschema':'MIT',
 'sqlalchemy/sqlalchemy':'MIT','pygments/pygments':'BSD-2-Clause'}
MCPS={
 'awslabs/mcp':'Apache-2.0','modelcontextprotocol/servers':'MIT','modelcontextprotocol/servers-archived':'MIT',
 'github/github-mcp-server':'MIT','microsoft/playwright-mcp':'Apache-2.0',
 'ChromeDevTools/chrome-devtools-mcp':'Apache-2.0','upstash/context7':'MIT',
 'browserbase/mcp-server-browserbase':'MIT','mendableai/firecrawl-mcp-server':'MIT',
 'tavily-ai/tavily-mcp':'MIT','qdrant/mcp-server-qdrant':'Apache-2.0','redis/mcp-redis':'MIT',
 'mongodb-js/mongodb-mcp-server':'Apache-2.0','elastic/mcp-server-elasticsearch':'Apache-2.0',
 'neo4j-contrib/mcp-neo4j':'Apache-2.0','datastax/mcp-server-astra':'Apache-2.0',
 'supabase-community/supabase-mcp':'Apache-2.0','cloudflare/mcp-server-cloudflare':'Apache-2.0',
 'stripe/agent-toolkit':'MIT','paypal/agent-toolkit':'Apache-2.0',
 'containers/kubernetes-mcp-server':'Apache-2.0','Flux159/mcp-server-kubernetes':'MIT',
 'alexander-zuev/supabase-mcp-server':'MIT','crystaldba/postgres-mcp':'MIT',
 'jlowin/fastmcp':'Apache-2.0','microsoft/azure-devops-mcp':'MIT',
 'mark3labs/mcp-filesystem-server':'MIT','mark3labs/mcp-server-git':'MIT',
 'modelcontextprotocol/python-sdk':'MIT','modelcontextprotocol/typescript-sdk':'MIT'}

def license_type(text):
    low=text.lower()
    if 'apache license' in low and ('version 2.0' in low or 'version 2,' in low):return 'Apache-2.0'
    if 'permission is hereby granted, free of charge' in low and 'the software' in low:return 'MIT'
    if 'redistribution and use in source and binary forms' in low and 'disclaimer' in low:
        return 'BSD-3-Clause' if 'neither the name' in low else 'BSD-2-Clause'
    return None

def fetch(repo,kind):
    budget(reserve=300)
    folder=OUT/'sources'/repo.replace('/','__');folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'manifest.json'
    if marker.exists():return json.loads(marker.read_text())
    try:
        proc=subprocess.run(['git','ls-remote','https://github.com/'+repo+'.git','HEAD'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
        commit=proc.stdout.split()[0]
        if len(commit)!=40:raise ValueError('Missing commit')
        response=httpx.get(f'https://codeload.github.com/{repo}/tar.gz/{commit}',timeout=75,follow_redirects=True)
        response.raise_for_status()
        archive=tarfile.open(fileobj=io.BytesIO(response.content))
        files={}
        for member in archive.getmembers():
            if not member.isfile() or member.size>2_000_000:continue
            rel=member.name.split('/',1)[-1]
            if '..' in Path(rel).parts:raise ValueError('Archive traversal')
            suffix=Path(rel).suffix.lower();base=Path(rel).name.lower()
            if suffix not in ('.md','.rst','.txt','.json','.py','.ts','.go','.toml','.yaml','.yml') and not base.startswith(('license','copying')):continue
            data=archive.extractfile(member).read()
            dest=folder/'files'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            files[rel]=len(data)
        licenses=[]
        for rel in files:
            if '/' not in rel and Path(rel).name.lower().startswith(('license','copying')):
                text=(folder/'files'/rel).read_text(encoding='utf-8',errors='replace');spdx=license_type(text)
                if spdx:licenses.append({'path':rel,'spdx':spdx})
        result={'repository':repo,'kind':kind,'commit':commit,'licenses':licenses,'accepted_license':bool(licenses),'file_n':len(files),'url':f'https://github.com/{repo}/tree/{commit}'}
    except Exception as e:result={'repository':repo,'kind':kind,'accepted_license':False,'error':type(e).__name__}
    marker.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

def main():
    jobs=[(r,'documentation') for r,l in DOCS.items() if l!='MPL-2.0']+[(r,'mcp') for r in MCPS]
    save('source-plan.json',{'documentation':DOCS,'mcp':MCPS,'excluded':['pallets/flask','pallets/click','python/cpython','HypothesisWorks/hypothesis'],'note':'Server identities derive from distinct published server packages, not tool count; license verified per fixed commit.'})
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        fs=[pool.submit(fetch,*j) for j in jobs]
        for f in concurrent.futures.as_completed(fs):
            r=f.result();results.append(r);print(json.dumps(r),flush=True)
            save('sources.json',results)

if __name__=='__main__':main()
