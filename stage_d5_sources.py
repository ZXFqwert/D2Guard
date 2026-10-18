"""Pinned, repository-isolated public sources for D5 (no upstream execution)."""
import concurrent.futures
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path
import httpx
from stage_d4_sources import license_type
from stage_d5_protocol import ROOT,OUT,budget,blocked_sources,save

DOC_TRAIN='''django/django tornadoweb/tornado celery/celery encode/uvicorn aio-libs/aiohttp aio-libs/aiosignal aio-libs/frozenlist aio-libs/multidict aio-libs/yarl aio-libs/aiocache aio-libs/aiomysql aio-libs/aiopg paramiko/paramiko pyca/cryptography pyca/bcrypt pyca/pynacl python-pillow/Pillow python-babel/babel dateutil/dateutil python-tz/tz python-semver/python-semver Delgan/loguru getlogbook/logbook structlog/structlog jmespath/jmespath.py pyyaml/pyyaml uiri/toml simplejson/simplejson ultrajson/ultrajson ijl/orjson msgpack/msgpack-python python-lz4/python-lz4 facebook/zstd joblib/joblib cloudpipe/cloudpickle dill/dill dask/dask dask/distributed python-streamz/streamz python-boltons/boltons more-itertools/more-itertools pytoolz/toolz pytoolz/cytoolz python-babel/flask-babel marshmallow-code/marshmallow coleifer/peewee encode/databases tortoise/tortoise-orm ponyorm/pony arrow-py/arrow python-pendulum/pendulum dbader/schedule agronholm/apscheduler rq/rq huey-task/huey dramatiq/dramatiq pallets-eco/flask-wtf wtforms/wtforms pallets-eco/flask-sqlalchemy pallets-eco/flask-caching maxcountryman/flask-login pallets-eco/flask-session PrettyTable/PrettyTable astanin/python-tabulate tqdm/tqdm facelessuser/wcwidth prompt-toolkit/python-prompt-toolkit python-cmd2/cmd2 davidhalter/jedi davidhalter/parso google/python-fire miguelgrinberg/python-socketio miguelgrinberg/python-engineio'''.split()
DOC_VALIDATION='''aio-libs/aiobotocore asyncpg/asyncpg magicstack/asyncpg Tinche/aiofiles encode/broadcaster litestar-org/litestar sanic-org/sanic falconry/falcon bottlepy/bottle webpy/webpy MasoniteFramework/masonite python-eve/eve hugapi/hug python-restx/flask-restx Flask-RESTful/flask-restful'''.split()

def plan():
    blocked,servers=blocked_sources();registry=json.loads((OUT/'registry-github.json').read_text());candidates={}
    for item in registry:
        s=item['server'];match=re.match(r'https://github.com/([^/]+/[^/#]+)',s.get('repository',{}).get('url',''))
        if not match:continue
        repo=match[1].removesuffix('.git')
        if repo.lower() in blocked or repo in DOC_TRAIN+DOC_VALIDATION:continue
        candidates.setdefault(repo,s['name'])
    # Fixed hash order; one independent repository per server prevents monorepo leakage.
    ordered=sorted(candidates,key=lambda r:hashlib.sha256(r.lower().encode()).hexdigest())
    mcp=[{'repository':r,'server_id':candidates[r],'split':'validation' if i%12==0 else 'train','kind':'mcp'} for i,r in enumerate(ordered[:320])]
    docs=[{'repository':r,'split':split,'kind':'documentation'} for split,rs in [('train',DOC_TRAIN),('validation',DOC_VALIDATION)] for r in rs]
    assert not {r['repository'].lower() for r in docs+mcp}&blocked
    result={'sources':docs+mcp,'excluded_test_repositories':sorted(blocked),'excluded_test_servers':sorted(servers),'repository_overlap':[],'server_overlap':[],'registry_url':'https://registry.modelcontextprotocol.io/v0.1/servers','selection':'fixed SHA256 order; no model predictions; no source execution','license_policy':'record at pinned commit; accept MIT/Apache-2.0/BSD for training; no approval requests'}
    save('source-plan.json',result);return result

def fetch(src):
    budget(300);repo=src['repository'];folder=OUT/'sources'/repo.replace('/','__');folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'manifest.json'
    if marker.exists():return json.loads(marker.read_text())
    try:
        proc=subprocess.run(['git','ls-remote','https://github.com/'+repo+'.git','HEAD'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35)
        commit=proc.stdout.split()[0]
        if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Missing pinned commit')
        with httpx.stream('GET',f'https://codeload.github.com/{repo}/tar.gz/{commit}',timeout=65,follow_redirects=True) as response:
            response.raise_for_status();data=bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data)>40_000_000:raise ValueError('Archive exceeds registered 40MB budget')
        archive=tarfile.open(fileobj=io.BytesIO(data));files={};licenses=[]
        for member in archive.getmembers():
            if not member.isfile() or member.size>1_000_000:continue
            rel=member.name.split('/',1)[-1];parts=Path(rel).parts
            if '..' in parts or Path(rel).is_absolute():raise ValueError('Unsafe archive path')
            if any(x in ('node_modules','.git','vendor','dist','build') for x in parts):continue
            suffix=Path(rel).suffix.lower();base=Path(rel).name.lower()
            if suffix not in ('.md','.rst','.txt','.json','.py','.ts','.go','.yaml','.yml') and not base.startswith(('license','copying')):continue
            raw=archive.extractfile(member).read();dest=folder/'files'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);files[rel]=len(raw)
            if '/' not in rel and base.startswith(('license','copying')):
                spdx=license_type(raw.decode('utf-8',errors='replace'))
                if spdx:licenses.append({'path':rel,'spdx':spdx,'sha256':hashlib.sha256(raw).hexdigest()})
        result={**src,'commit':commit,'licenses':licenses,'accepted_license':bool(licenses),'files':len(files),'url':f'https://github.com/{repo}/tree/{commit}'}
    except Exception as e:result={**src,'error_type':type(e).__name__,'accepted_license':False}
    marker.write_text(json.dumps(result,indent=2),encoding='utf-8');return result

def main():
    p=json.loads((OUT/'source-plan.json').read_text());results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for row in pool.map(fetch,p['sources']):
            results.append(row)
            if len(results)%20==0:save('sources.json',results);print(json.dumps({'completed':len(results),'accepted':sum(r['accepted_license'] for r in results)}),flush=True)
    save('sources.json',results)

if __name__=='__main__':main()
