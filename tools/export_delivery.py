"""Explicit allowlist export. Does not touch the four delivery documents."""
import argparse,ast,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def copytree(src,dst):shutil.copytree(src,dst,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.cache','*.pyc','app.js'))
def scan(folder):
 findings=[];secrets=[]
 for f in (ROOT/'.local').glob('*teacher*.env'):
  for l in f.read_text(encoding='utf-8').splitlines():
   if '=' in l and any(k in l.split('=',1)[0].upper() for k in ('KEY','TOKEN','SECRET')):
    v=l.split('=',1)[1].strip().strip('\"\'')
    if len(v)>12:secrets.append(v)
 counts={k:0 for k in ('sk-','Bearer ','api_key','ip')};blocked=[]
 for p in folder.rglob('*'):
  if not p.is_file() or p.suffix in ('.safetensors','.bin','.png','.jpg','.woff2'):continue
  text=p.read_text(encoding='utf-8',errors='replace')
  for key in ('sk-','Bearer ','api_key'):counts[key]+=text.count(key)
  counts['ip']+=len(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',text))
  if any(v in text for v in secrets) or re.search(r'\bsk-[A-Za-z0-9]{20,}',text):blocked.append(p.relative_to(folder).as_posix())
  # Infrastructure identifiers are forbidden, synthetic/local-service addresses are not secrets.
  if any(v in text for v in ('175.6.27.158','10.33.0.30','li33_compute_roots','/home/roots/')):blocked.append(p.relative_to(folder).as_posix())
 return {'passed':not blocked,'blocked_files':sorted(set(blocked)),'pattern_counts':counts,'known_secret_count':len(secrets),'note':'Generic API field names, Bearer construction and loopback/lab/test fixture addresses are code, not credentials; matching live keys or compute identifiers blocks export.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--assets',required=True);p.add_argument('--destination',default=str(ROOT.parent/'交付件'));a=p.parse_args();dest=Path(a.destination).resolve();code=dest/'03-程序源码';code.mkdir(parents=True,exist_ok=True)
 for name in ('src','extensions','scenarios','training'):copytree(ROOT/name,code/name)
 for name in ('lab.py','verify_v2.py','run_evaluation.py','policies.yaml','package.json','runtime-lock.json','runtime-source-manifest.json','requirements-core.txt','requirements-laya.txt','requirements-gpu.txt'):
  src=ROOT/name
  if src.exists():shutil.copy2(src,code/name)
 shutil.copy2(ROOT/'src/d2v2/policies.yaml',code/'policies.yaml')
 (code/'deploy').mkdir(exist_ok=True);shutil.copy2(ROOT/'deploy/host-exec.md',code/'deploy/host-exec.md')
 (code/'tools').mkdir(exist_ok=True)
 for name in ('configure_delivery.py','setup_runtime.py','console_launcher.py','setup_windows.py','windows_console.py','package_delivery.py',
              'run_direct_input_evaluation.py','audit_direct_input_evaluation.py','check_native_chat.py','verify_delivery_sources.py'):
  shutil.copy2(ROOT/'tools'/name,code/'tools'/name)
 shutil.copy2(ROOT/'deploy/WINDOWS-使用说明.md',code/'WINDOWS-使用说明.md')
 # Only tests whose import closure is available in the runtime export.
 candidates={p.stem:p for p in (ROOT/'tests').glob('*.py')};excluded=set()
 for name,p in candidates.items():
  tree=ast.parse(p.read_text(encoding='utf-8'));imports=[]
  for n in ast.walk(tree):
   if isinstance(n,ast.Import):imports += [x.name.split('.')[0] for x in n.names]
   elif isinstance(n,ast.ImportFrom):imports += [(n.module or '').split('.')[0]]
  if any(i.startswith(('stage_','train_stage_','evaluate_stage_')) or ((ROOT/(i+'.py')).exists() and i not in ('lab','verify_v2','run_evaluation')) for i in imports):excluded.add(name)
 changed=True
 while changed:
  changed=False
  for name,p in candidates.items():
   if name not in excluded and any(re.search(r'\b'+re.escape(e)+r'\b',p.read_text(encoding='utf-8')) for e in excluded):excluded.add(name);changed=True
 (code/'tests').mkdir(exist_ok=True)
 for name,p in candidates.items():
  if name not in excluded:shutil.copy2(p,code/'tests'/p.name)
  elif (code/'tests'/p.name).exists():(code/'tests'/p.name).unlink()
 shutil.copy2(ROOT/'tests/boundary.test.mjs',code/'tests/boundary.test.mjs')
 console=ROOT/'console'
 (code/'console').mkdir(exist_ok=True)
 for name in ('server.py','d2trace.py'):shutil.copy2(console/name,code/'console'/name)
 copytree(console/'static',code/'console/static')
 if (console/'data').exists():copytree(console/'data',code/'console/data')
 copytree(ROOT/'scenarios',dest/'04-测试样例/scenarios')
 copytree(Path(a.assets),code)
 for name in ('setup-windows.bat','start-console.bat','build-submission.bat'):
  shutil.copy2(ROOT/'deploy/windows'/name,code/name)
 shutil.copy2(ROOT/'tools/delivery-readme.md',code/'README.md')
 for cache in list(code.rglob('__pycache__')):
  if code in cache.resolve().parents:shutil.rmtree(cache)
 result=scan(code);result['scenario_scan']=scan(dest/'04-测试样例/scenarios');result['excluded_tests']=sorted(excluded)
 result['files']={p.relative_to(code).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()} for p in sorted(code.rglob('*')) if p.is_file()}
 (ROOT/'.local/delivery/export-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False))
 if not result['passed'] or not result['scenario_scan']['passed']:raise SystemExit('Secret scan blocked export')
if __name__=='__main__':main()
