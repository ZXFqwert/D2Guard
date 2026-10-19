"""Read-only Stage F trace/citation audit. Does not call a model or rewrite runs."""
import argparse,hashlib,json,sqlite3
from pathlib import Path
from collections import Counter
from d2v2.trace import build_trace,jsonl
from d2v2.ledger import values

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit_run(folder):
 folder=Path(folder)
 files=[folder/n for n in ('state.sqlite3','audit.jsonl','decisions.jsonl','result.json','manifest.json') if (folder/n).exists()]
 before={p.name:sha(p) for p in files}
 trace=build_trace(folder);errors=[];refs=0
 db=sqlite3.connect((folder/'state.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
 def check(ref):
  nonlocal refs
  refs+=1
  row=db.execute('SELECT raw,sha FROM events WHERE id=?',(ref['event_id'],)).fetchone()
  span=ref.get('char_span')
  valid=bool(row and row[1]==hashlib.sha256(row[0].encode()).hexdigest()==ref['sha256'] and
   isinstance(span,list) and len(span)==2 and all(type(x) is int for x in span) and 0<=span[0]<=span[1]<=len(row[0]))
  if not valid:errors.append('invalid_reference')
  return valid
 for s in trace['sources']:check(s['evidence_ref'])
 held=[]
 for c in trace['calls']:
  for ref in c['evidence_refs']:check(ref)
  if c['verdict'] in ('ASK','BLOCK'):
   held.append({'call_id':c['call_id'],'rule_id':c['rule_id'],'verdict':c['verdict'],'risk':c['risk'],'executed':c['executed'],'refs':c['evidence_refs']})
   if not c['report'] or not c['evidence_refs']:errors.append('missing_report_or_reference')
  elif c['report']:errors.append('review_for_allow')
  if c.get('review'):
   for ref in c['review'].get('citations',[]):check(ref)
 text=json.dumps(trace,ensure_ascii=False)
 secrets=set()
 for raw, in db.execute('SELECT e.raw FROM secrets s JOIN events e ON e.id=s.event_id'):secrets.update(values(raw))
 if any(secret in text for secret in secrets):errors.append('public_secret')
 db.close()
 after={p.name:sha(p) for p in files}
 if before!=after:errors.append('evidence_changed')
 if not trace['graph']['acyclic']:errors.append('graph_cycle')
 reviews=[x for x in jsonl(folder/'decisions.jsonl') if x.get('type')=='slow_review']
 return {'run_id':folder.name,'scenario':trace['run']['scenario'],'decision_mode':trace['run']['decision_mode'],
         'calls':len(trace['calls']),'held':held,'reference_count':refs,'source_count':len(trace['sources']),
         'node_kinds':dict(Counter(n['kind'] for n in trace['graph']['nodes'])),
         'source_types':dict(Counter(s['type'] for s in trace['sources'])),
         'reviews':dict(Counter(x.get('attribution_status','historical') for x in reviews)),
         'evidence_unchanged':before==after,'errors':errors,'passed':not errors}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--runs',nargs='+',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
 result=[audit_run(Path('runs')/rid) for rid in args.runs]
 Path(args.output).write_text(json.dumps({'runs':result,'passed':all(x['passed'] for x in result)},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'runs':len(result),'held':sum(len(x['held']) for x in result),'passed':all(x['passed'] for x in result)},ensure_ascii=False))
