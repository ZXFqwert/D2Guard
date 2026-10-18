"""Licensed public candidates; official benchmark test families never train."""
import argparse
import json
import re
from stage_d2_data import ROOT,OUT,sha
from d2v2.normalization import normalize


def main(round_number):
    source=ROOT/'.local/stage-d-sources';rows=[];provenance=[]
    for split,part in [('train','train'),('public_heldout','test')]:
        for kind in ('text','code'):
            path=source/'BIPIA/benchmark'/f'{kind}_attack_{part}.json'
            obj=json.loads(path.read_text(encoding='utf-8'))
            provenance.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path.read_text()),'license':'MIT','revision':'a004b69ec0dd446e0afd461d98cb5e96e120a5d0'})
            for family,texts in obj.items():
                for i,text in enumerate(texts):
                    if not isinstance(text,str) or not 40<=len(text)<=5000:continue
                    # Public synthetic attack strings contain example assets,
                    # not credentials. Reject secret-shaped values defensively.
                    if re.search(r'\bsk-[A-Za-z0-9]{16,}|-----BEGIN .*PRIVATE KEY',text):continue
                    rows.append({'id':f'public-bipia-{kind}-{part}-{sha(family)[:8]}-{i}','text':normalize(text)[0],
                      'split':split,'label':'request','source_type':'LOCAL_FILE' if kind=='code' else 'WEB','source_kind':'code_comments' if kind=='code' else 'web',
                      'language':'en','family':'BIPIA:'+family,'domain':'BIPIA:'+family,'source_dataset':'BIPIA-'+part,
                      'upstream_dataset':'BIPIA','upstream_split':part,'license':'MIT','source_url':f'https://github.com/microsoft/BIPIA/blob/a004b69ec0dd446e0afd461d98cb5e96e120a5d0/benchmark/{kind}_attack_{part}.json',
                      'transform':'plain','synthetic':True,'contract_basis':'Published adversarial operation-request payload; both teachers must agree'})
    for name,split,license in [('flask','train','BSD-3-Clause'),('click','validation','BSD-3-Clause'),('python','public_heldout','PSF-2.0')]:
        path=source/(name+'-doc.rst');text=path.read_text(encoding='utf-8')
        blocks=re.split(r'\n\s*\n',text)
        for i,block in enumerate(blocks):
            block=block.strip()
            if not 100<=len(block)<=650 or re.search(r'\bsk-[A-Za-z0-9]{16,}|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}',block):continue
            label='request' if re.search(r'\b(?:you should|you need to|you must|run the|install the|create a|use the|make sure|click on|please)\b',block,re.I) else 'none'
            rows.append({'id':f'public-{name}-{i}','text':normalize(block)[0],'split':split,'label':label,'source_type':'LOCAL_FILE','source_kind':'repository_docs',
               'language':'en','family':name+'-documentation','domain':name+'-documentation','source_dataset':name+'-documentation',
               'license':license,'source_file':str(path.relative_to(ROOT)),'transform':'plain','synthetic':False,'approved_public':True,
               'contract_basis':'Conservative operation-procedure vs descriptive-documentation mapping, not a final label; require both teachers'})
        provenance.append({'path':str(path.relative_to(ROOT)),'sha256':sha(text),'license':license,'license_file':name+'-license.txt'})
    if round_number>1:rows=[row for row in rows if row['split']=='train']
    folder=OUT/f'round-{round_number}';folder.mkdir(exist_ok=True)
    with (folder/'public-candidates.jsonl').open('x',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    (folder/'public-sources.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    print(json.dumps({'public_candidates':len(rows),'public_test':sum(r['split']=='public_heldout' for r in rows)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,default=1);main(p.parse_args().round)
