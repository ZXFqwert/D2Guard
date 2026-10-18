"""Pre-fit shortcut gate; gold is inaccessible to this round probe."""
import argparse
import hashlib
import json
import re
import time
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from stage_d3_protocol import OUT,read,budget
from stage_d2_metrics import LABELS,groups


def first_sentence(text):
    text=text.strip()
    try:
        value=json.loads(text)
        if isinstance(value,dict) and isinstance(value.get('description'),str):text=value['description']
    except (ValueError,TypeError):pass
    # A line break or an opening JSON brace is not a sentence. This prevents
    # pretty-printed tool descriptions from trivially evading the probe.
    match=re.search(r'[。！？]|[.!?](?=\s|$)',text)
    return text[:match.end()] if match else text


def main(round_number):
    folder=OUT;rows=read(folder/'admitted.jsonl')
    train=[r for r in rows if r['split']=='train'];val=[r for r in rows if r['split']=='validation'];results={}
    frozen=OUT/'new-validation-frozen.jsonl'
    serialized=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in val).encode('utf-8')
    if round_number==1 and not frozen.exists():
        with frozen.open('xb') as stream:stream.write(serialized)
    if not frozen.exists() or frozen.read_bytes()!=serialized:raise ValueError('Validation must remain identical across rounds')
    results['validation_sha256']=hashlib.sha256(serialized).hexdigest()
    for mode in ('first_sentence','full'):
        budget(reserve=120);start=time.time();text=lambda r:first_sentence(r['text']) if mode=='first_sentence' else r['text']
        vector=TfidfVectorizer(analyzer='char',ngram_range=(3,5),max_features=150000,sublinear_tf=True)
        x=vector.fit_transform([text(r) for r in train]);clf=LogisticRegression(C=1.,max_iter=1000,random_state=20261017).fit(x,[r['label'] for r in train])
        ps=clf.predict_proba(vector.transform([text(r) for r in val]));ps=ps[:,[list(clf.classes_).index(l) for l in LABELS]]
        results[mode]={'validation':groups(val,ps),'seconds':time.time()-start}
    results['pretrain_passed']=results['first_sentence']['validation']['all']['accuracy']<.90
    results['posttrain_rule']='tuned validation request F1 must exceed full probe validation request F1 by at least 0.03'
    with (folder/'probe.json').open('x',encoding='utf-8') as f:json.dump(results,f,ensure_ascii=False,indent=2)
    print(json.dumps({'pretrain_passed':results['pretrain_passed'],'first_sentence_accuracy':results['first_sentence']['validation']['all']['accuracy'],
       'full_request_f1':results['full']['validation']['all']['request']['f1']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,default=1);main(p.parse_args().round)
