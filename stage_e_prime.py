"""Stage E-prime audit and frozen-source offline replay. No inference is repeated."""
import json,hashlib,time,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'.local/stage-e-prime'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def audit():
 old=read(ROOT/'.local/stage-e/regression.json');found=[];n=0;allowed=0
 for phase,records in old['records'].items():
  for r in records:
   if r['cell']['arm']!='C':continue
   n+=1
   for line in (ROOT/'runs'/r['run_id']/'decisions.jsonl').read_text().splitlines():
    d=json.loads(line)
    if d.get('verdict')=='ALLOW' and d.get('rule_id')=='DT-4c-S1':
     allowed+=1
     if d.get('decision_facts',{}).get('untrusted_sink'):
      found.append({'phase':phase,'run_id':r['run_id'],'call_id':d['call_id'],'cell':r['cell'],'rule_id':d['rule_id'],'untrusted_sink':True})
 result={'runs':n,'DT_4c_S1_allow':allowed,'untrusted_sink_allow':found,'audited_unix':time.time()};save('prior-egress-audit.json',result);print(json.dumps(result))
def offline():
 import stage_e_offline as e
 class Frozen:
  def __init__(self,*a):pass
  def classify(self,*a):raise RuntimeError('Frozen cache missing: no new inference allowed')
 e.OUT=OUT;e.RequestContentModel=Frozen
 shutil.copy2(ROOT/'.local/stage-e/source-predictions.json',OUT/'source-predictions.json')
 e.main()
if __name__=='__main__':
 OUT.mkdir(exist_ok=True)
 {'audit':audit,'offline':offline}[sys.argv[1]]()
