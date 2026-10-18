"""Finalize real-set metadata before its first classifier evaluation."""
import hashlib
import json
import shutil
from collections import Counter
from stage_d4_protocol import OUT,read,save,sha

def main():
    assert not (OUT/'evaluation-started.json').exists()
    marker=OUT/'data-finalization.json'
    if marker.exists():raise ValueError('Real-set metadata already finalized')
    path=OUT/'benign-frozen.jsonl';rows=read(path);prior_sha=sha(path)
    signature=lambda data:hashlib.sha256(json.dumps([(r['id'],r['raw_text'],r['source_type'],r['label']) for r in data],ensure_ascii=False).encode()).hexdigest()
    before=signature(rows)
    shutil.copyfile(path,OUT/'benign-before-language-metadata.jsonl')
    for r in rows:r['language']='und'
    assert signature(rows)==before
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    admission=json.loads((OUT/'admission.json').read_text());admission['benign_sha256']=sha(path)
    admission['language_annotation']='Not annotated for real-source data; und replaces a collection placeholder. Language is not a model input.'
    admission['distribution']={'repository':dict(Counter(r['repository'] for r in rows)),
      'document_kind':dict(Counter(r.get('document_kind','not_documentation') for r in rows)),
      'category_labels':{c:dict(Counter(r['label'] for r in rows if r['category']==c)) for c in admission['category']},
      'server':dict(Counter(r['server_id'] for r in rows if r['category']=='mcp'))}
    save('admission.json',admission)
    save('data-finalization.json',{'before_sha256':prior_sha,'final_sha256':sha(path),'classifier_input_and_label_signature':before,'text_labels_ids_source_types_unchanged':True,'language_metadata':'und; not annotated','no_classifier_predictions_exist':True})
    print(json.dumps({'passed':admission['passed'],'n':len(rows),'category':admission['category'],'servers':admission['distinct_mcp_servers'],'repositories':admission['repository_n'],'commands':admission['distinct_command_outputs']}))

if __name__=='__main__':main()
