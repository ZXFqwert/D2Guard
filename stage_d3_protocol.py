"""One-round budget and immutable D-triple-prime inputs."""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'.local/stage-d3'
OLD=ROOT/'.local/stage-d2'

def read(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]

def write_rows(path,rows):
    with path.open('x',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def plan():return json.loads((OUT/'protocol.json').read_text(encoding='utf-8'))

def budget(kind='data',reserve=0):
    p=plan();deadline=p['started_unix']+p['stage_budget_seconds']
    if kind=='data':
        extension=OUT/'continuation-authorization.json'
        data_deadline=p['started_unix']+p['data_budget_seconds']
        if extension.exists():
            permission=json.loads(extension.read_text(encoding='utf-8'))
            if permission.get('existing_data_only') is not True or permission.get('protocol_sha256')!=sha(OUT/'protocol.json'):
                raise ValueError('Invalid continuation authorization')
            data_deadline=permission['data_deadline_unix']
        gapfill=OUT/'gapfill-authorization.json'
        if gapfill.exists():
            permission=json.loads(gapfill.read_text(encoding='utf-8'))
            if permission.get('generation_allowed') is not True or permission.get('protocol_sha256')!=sha(OUT/'protocol.json'):
                raise ValueError('Invalid gap-fill authorization')
            data_deadline=permission['data_deadline_unix']
        deadline=min(deadline,data_deadline)
    if kind=='training':
        t=json.loads((OUT/'training-clock.json').read_text())
        deadline=min(deadline,t['started_unix']+p['training_evaluation_budget_seconds'])
    if time.time()>=deadline-reserve:raise TimeoutError('D-triple-prime '+kind+' wall-clock budget')
    return deadline


def reconstruct():
    import re
    from d2v2.semantic_view import semantic_view,mixed_word_statistics
    from d2v2.normalization import normalize
    from stage_d_data import frozen_evaluation
    from stage_d2_data import sha as text_sha
    # Recover licensed source bytes by stable original source identifiers.
    source=ROOT/'.local/stage-d-sources';public_raw={}
    for part in ('train','test'):
        for kind in ('text','code'):
            path=source/'BIPIA'/'benchmark'/f'{kind}_attack_{part}.json'
            if not path.exists():
                path=source/'bipia'/'benchmark'/f'{kind}_attack_{part}.json'
            if not path.exists():
                candidates=list(source.rglob(f'{kind}_attack_{part}.json'))
                if len(candidates)!=1:raise ValueError('Ambiguous public raw source')
                path=candidates[0]
            for family,texts in json.loads(path.read_text(encoding='utf-8')).items():
                for i,text in enumerate(texts):public_raw[f'public-bipia-{kind}-{part}-{text_sha(family)[:8]}-{i}']=text
    for name in ('flask','click','python'):
        blocks=re.split(r'\n\s*\n',(source/(name+'-doc.rst')).read_text(encoding='utf-8'))
        for i,block in enumerate(blocks):public_raw[f'public-{name}-{i}']=block.strip()
    def convert(r,gold=False):
        raw=r.get('raw_text')
        origin='raw_text'
        if raw is None:
            raw=r['text'] if gold else public_raw[r['id']]
            origin='gold original fragment' if gold else 'frozen licensed source'
            if not gold and normalize(raw)[0]!=r['text']:raise ValueError('Public source no longer matches original admitted text')
        return {**r,'raw_text':raw,'text':semantic_view(raw),'text_normalized':False,'semantic_view_version':'d3-v1','raw_source':origin}
    train=[r for r in read(OLD/'round-3/admitted.jsonl') if r['split']=='train']
    validation=read(OLD/'validation-frozen.jsonl');held=read(OLD/'semantic-heldout-frozen.jsonl')
    _,gold,gold_files=frozen_evaluation()
    sets={'retained-training':train,'old-validation':validation,'frozen-heldout':held,'gold':gold}
    manifest={};converted={}
    for name,rows in sets.items():
        converted[name]=[convert(r,name=='gold') for r in rows]
        target=OUT/(name+'.jsonl');write_rows(target,converted[name]);manifest[name]={'n':len(rows),'sha256':sha(target)}
    russian=[r for r in held if r['split']=='semantic_heldout' and r['language']=='ru']
    before=mixed_word_statistics([normalize(r['raw_text'])[0] for r in russian])
    after=mixed_word_statistics([semantic_view(r['raw_text']) for r in russian])
    result={'datasets':manifest,'russian_semantic_heldout_n':len(russian),'before':before,'after':after,'passed':after['fraction']<.01,
        'frozen_source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [OLD/'round-3/admitted.jsonl',OLD/'validation-frozen.jsonl',OLD/'semantic-heldout-frozen.jsonl',ROOT/'docs/stage-d2-heldout-audit/exclusions.json']},
        'gold_source_sha256':gold_files,'semantic_view_sha256':sha(ROOT/'src/d2v2/semantic_view.py'),
        'rule_view_sha256':sha(ROOT/'src/d2v2/normalization.py')}
    (OUT/'semantic-view.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('gold_source_sha256','frozen_source_sha256')}))

if __name__=='__main__':reconstruct()
