"""Build D5 corpus from reviewed rows; reject cross-split near duplicates, run shortcut probe."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from metrics import groups,LABELS

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--excluded',required=True,help='Frozen test text JSONL, used only for isolation');p.add_argument('--output',required=True);a=p.parse_args()
 rows=[json.loads(l) for l in Path(a.input).read_text(encoding='utf-8').splitlines() if l.strip()];excluded=[json.loads(l) for l in Path(a.excluded).read_text(encoding='utf-8').splitlines() if l.strip()]
 from d2v2.semantic_view import semantic_view
 def grams(t):return set(t[i:i+5] for i in range(max(1,len(t)-4)))
 def near(a,b):return len(a&b)/max(1,len(a|b))>=.5
 tests=[grams(semantic_view(r['raw_text'])) for r in excluded];kept=[];indexes=[];rejected=0
 ids=set();families={}
 for r in rows:
  if r['id'] in ids:raise ValueError('Duplicate ID')
  ids.add(r['id']);assert r['label'] in LABELS and r['split'] in ('train','validation')
  if not r.get('reviewed'):raise ValueError('Unreviewed row')
  family=r['family'];old=families.setdefault(family,r['split'])
  if old!=r['split']:raise ValueError('Cross-split family')
  r['text']=semantic_view(r['raw_text']);g=grams(r['text'])
  if any(near(g,b) for b in tests) or any(split!=r['split'] and near(g,b) for split,b in indexes):rejected+=1;continue
  kept.append(r);indexes.append((r['split'],g))
 out=Path(a.output);out.mkdir(parents=True,exist_ok=True);data=out/'admitted.jsonl';data.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in kept),encoding='utf-8')
 train=[r for r in kept if r['split']=='train'];val=[r for r in kept if r['split']=='validation']
 checks={'reviewed':True,'isolation':True,'train_n':len(train)>=12204,'validation_n':len(val)>=900,'real_fraction':sum(r.get('origin','').startswith('real') for r in train)/max(1,len(train))>=.35}
 result={}
 for name,first in [('full',False),('first_sentence',True)]:
  def text(r):return r['text'].split('.')[0].split('\n')[0] if first else r['text']
  vec=TfidfVectorizer(analyzer='char',ngram_range=(3,5),max_features=150000,sublinear_tf=True);x=vec.fit_transform([text(r) for r in train]);clf=LogisticRegression(max_iter=500,class_weight='balanced');clf.fit(x,[r['label'] for r in train]);p=clf.predict_proba(vec.transform([text(r) for r in val]));p=p[:,[list(clf.classes_).index(k) for k in LABELS]];result[name]={'validation':groups(val,p)}
 probe={'pretrain_passed':result['first_sentence']['validation']['all']['accuracy']<.90,**result,'validation_sha256':hashlib.sha256(json.dumps(val,sort_keys=True).encode()).hexdigest()}
 (out/'probe.json').write_text(json.dumps(probe,indent=2));(out/'admission.json').write_text(json.dumps({'passed':all(checks.values()),'checks':checks,'isolation_rejected':rejected,'admitted_sha256':hashlib.sha256(data.read_bytes()).hexdigest()},indent=2))
if __name__=='__main__':main()
