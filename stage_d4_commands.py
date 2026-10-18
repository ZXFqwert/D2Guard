"""Real read-only command output inside networkless bubblewrap sandboxes."""
import concurrent.futures
import json
import os
import subprocess
import tarfile
from pathlib import Path
from stage_d4_protocol import OUT,budget,save

CHECKER='''import ast, json, pathlib, sys, unittest
root=pathlib.Path('/data')
mode=sys.argv.pop()
files=sorted(p for p in root.rglob('*') if p.is_file())
class SourceChecks(unittest.TestCase):
    def test_source_files_present(self): self.assertGreater(len(files),0)
    def test_public_documents_utf8(self):
        for p in files:
            if p.suffix in ('.md','.rst','.txt'): p.read_text(encoding='utf-8')
    def test_json_syntax(self):
        for p in files:
            if p.suffix=='.json': json.loads(p.read_text(encoding='utf-8'))
if mode=='test': unittest.main(verbosity=2)
elif mode=='build':
    for p in files:
        if p.suffix=='.py':
            try: ast.parse(p.read_text(encoding='utf-8')); print('syntax OK',p.relative_to(root))
            except SyntaxError as e: print('syntax ERROR',p.relative_to(root),e.msg)
        elif p.suffix in ('.md','.rst','.txt'): print('document indexed',p.relative_to(root),'bytes',p.stat().st_size)
    print('read-only indexing complete; source code was not executed')
'''

def prepare():
    sources=json.loads((OUT/'sources.json').read_text());docs=[s for s in sources if s['kind']=='documentation' and 'error' not in s]
    with tarfile.open(OUT/'command-inputs.tar.gz','w:gz') as t:
        for s in docs:
            root=OUT/'sources'/s['repository'].replace('/','__')/'files'
            selected=[]
            for suffix in ('.md','.rst','.txt','.json','.py'):
                selected+=sorted((p for p in root.rglob('*') if p.is_file() and p.suffix==suffix and p.stat().st_size<100000),key=lambda p:(len(p.parts),str(p)))[:3]
            for p in selected:t.add(p,arcname=s['repository'].replace('/','__')+'/'+p.relative_to(root).as_posix())
    save('command-source-plan.json',docs)
    (OUT/'check_public_sources.py').write_text(CHECKER,encoding='utf-8')
    print(json.dumps({'repositories':len(docs),'commands':len(docs)*4,'archive_bytes':(OUT/'command-inputs.tar.gz').stat().st_size}))

def run_repo(source,extra=False):
    budget(reserve=600)
    repo=source['repository'];slug=repo.replace('/','__');folder=OUT/'command-data'/slug
    commands=[['/usr/bin/find','/data','-type','f','-exec','/usr/bin/sha256sum','{}',';'],
              ['/usr/bin/du','-ab','/data'],
              ['/usr/bin/python3','/runner.py','test'],['/usr/bin/python3','/runner.py','build']]
    if extra:commands=[['/usr/bin/find','/data','-type','f','-exec','/usr/bin/wc','-l','-w','-c','{}',';']]
    rows=[]
    for i,command in enumerate(commands):
        base=['bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(folder),'/data','--ro-bind',str(OUT/'check_public_sources.py'),'/runner.py','--chdir','/data','--clearenv','--setenv','PATH','/usr/bin','--setenv','LANG','C.UTF-8',*command]
        result=subprocess.run(base,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        rows.append({'id':slug+'-'+str(i+4 if extra else i),'repository':repo,'commit':source['commit'],'licenses':source.get('licenses',[]),'url':source['url'],'command':command,'stdout':result.stdout,'stderr':result.stderr,'returncode':result.returncode,'sandbox':'bubblewrap unshare-all; read-only data; no host home; no network'})
    return rows

def collect(extra=False):
    folder=OUT/'command-data';folder.mkdir(exist_ok=True)
    with tarfile.open(OUT/'command-inputs.tar.gz') as t:t.extractall(folder,filter='data')
    sources=json.loads((OUT/'command-source-plan.json').read_text());rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(run_repo,s,extra) for s in sources]
        for f in concurrent.futures.as_completed(futures):
            rows+=f.result()
            save('command-outputs-supplement.json' if extra else 'command-outputs.json',rows)
            print(json.dumps({'completed_commands':len(rows),'nonzero':sum(r['returncode']!=0 for r in rows)}),flush=True)

if __name__=='__main__':
    import sys
    prepare() if sys.argv[1]=='prepare' else collect(sys.argv[1]=='extra')
