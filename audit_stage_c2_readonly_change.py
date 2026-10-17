"""Offline predicate equivalence audit; not a model replay or gold annotation."""
import argparse,ast,hashlib,importlib.util,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'src'))
from d2v2.compression import canonical,readonly_write_violation
from verify_v2 import rows

def audit(root,suite,old_root):
 spec=importlib.util.spec_from_file_location('d2v2._v4_compression',old_root/'src/d2v2/compression.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 data=json.loads(suite.read_text(encoding='utf-8'));folders=[]
 for item in data['batches']:
  b=json.loads((suite.parent/(item['batch_id']+'.json')).read_text(encoding='utf-8'));folders.extend(suite.parent/r['run_id'] for r in b['results']+b['setup_runs'])
 def other_ast(path):
  tree=ast.parse(path.read_text(encoding='utf-8'));tree.body=[node for node in tree.body if not isinstance(node,ast.FunctionDef) or node.name!='readonly_write_violation'];return ast.dump(tree,include_attributes=False)
 unchanged=other_ast(old_root/'src/d2v2/compression.py')==other_ast(root/'src/d2v2/compression.py')
 changes=[];count=0;readonly=0;writes=0
 extensions={'.py','.js','.ts','.tsx','.jsx','.c','.cpp','.h','.java','.go','.rs','.sh','.ps1'}
 first=json.loads((folders[0]/'manifest.json').read_text(encoding='utf-8'))
 differences=[name for name in first['source_sha256'] if (old_root/name).read_bytes()!=(root/name).read_bytes()]
 for folder in folders:
  manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));sources={canonical(name) for name in manifest['initial_files'] if Path(name).suffix.lower() in extensions}
  for d in rows(folder/'decisions.jsonl'):
   if d.get('type')!='decision':continue
   count+=1;anchor=d['previous_security_state']['authority_anchor'];delta=d['evidence']['security_delta'];readonly+=anchor['intent_mode']=='READONLY_REVIEW';writes+=anchor['intent_mode']=='READONLY_REVIEW' and delta['tool']=='fs.write'
   previous=old.readonly_write_violation(delta,anchor,sources);current=readonly_write_violation(delta,anchor,sources)
   if previous!=current:changes.append({'run_id':folder.name,'call_id':d['call_id'],'tool':delta['tool'],'target':delta['target'],'previous_predicate':previous,'current_predicate':current})
 return {'kind':'offline_recorded_predicate_comparison_not_model_replay','suite':data['suite'],'runs':len(folders),'decision_frames':count,'readonly_frames':readonly,'readonly_write_frames':writes,'runtime_source_difference_files':differences,'changed_recorded_predicates':changes,'observed_predicates_equivalent':not changes,'only_runtime_change_is_compression':differences==['src/d2v2/compression.py'],'other_compression_ast_identical':unchanged,'training_allowed':False,'gold_labels_created':False}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('suite',type=Path);p.add_argument('--old-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=audit(Path(__file__).parent,a.suite,a.old_root);a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(r,ensure_ascii=False))
