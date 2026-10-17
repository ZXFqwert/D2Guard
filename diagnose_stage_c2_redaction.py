"""Read-only offline serialization regression on retained failures, not model runs."""
import argparse,hashlib,json,sqlite3,sys
from collections import Counter
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folders',type=Path,nargs='+')
    p.add_argument('--runtime-root',type=Path,default=Path(__file__).parent);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.runtime_root.resolve()/'src'))
    from d2v2.core import CoreV2
    from d2v2.ledger import FingerprintLedger
    result=[]
    for folder in a.folders:
        paths=[folder/n for n in ['security_chain.jsonl','decisions.jsonl','state.sqlite3','fingerprint.key']]
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        secret=(folder/'workspace/.env').read_text(encoding='utf-8').splitlines()[0].split('=',1)[1]
        fields=Counter();original=remaining=0
        def locate(value,path=''):
            if isinstance(value,str) and secret in value:fields[path]+=1
            elif isinstance(value,dict):
                for k,v in value.items():locate(v,path+'.'+k)
            elif isinstance(value,list):
                for v in value:locate(v,path+'[]')
        with closing(sqlite3.connect((folder/'state.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)) as db:
            db.row_factory=sqlite3.Row
            stub=SimpleNamespace(ledger=FingerprintLedger(SimpleNamespace(db=db,folder=folder)))
            for name in ['security_chain.jsonl','decisions.jsonl']:
                for line in (folder/name).read_text(encoding='utf-8').splitlines():
                    value=json.loads(line);original+=secret in line;locate(value,name)
                    sanitized=CoreV2._security(stub,value)
                    remaining+=secret in json.dumps(sanitized,ensure_ascii=False)
        result.append({'run_id':folder.name,'original_leaking_rows':original,'leaking_field_paths':dict(fields),
            'after_serialization_leaking_rows':remaining,'original_artifacts_unchanged':all(hashlib.sha256(p.read_bytes()).hexdigest()==before[p.name] for p in paths)})
    report={'kind':'offline_read_only_serialization_diagnostic','not_real_model_runs':True,'gold_generated':False,'results':result}
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
