"""D-double-prime D0 diagnostics. Output aggregate gold metrics, never errors."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
import numpy as np
from stage_d2_metrics import mapped, merge_old, groups

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '.local/stage-d2'
OLD = ROOT / '.local/stage-d-prime'


def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def register():
    OUT.mkdir(exist_ok=True)
    write_new(OUT / 'diagnostic-preregistered.json', {
        'registered_unix': time.time(), 'mapping': 'to_agent+for_reader=request;quoted=quoted;data=none',
        'old_model_temperature': 1., 'old_model_threshold': .5, 'old_model_input_question': 'unchanged D-prime four-class question',
        'probe': {'analyzer': 'char', 'ngram_range': [3, 5], 'max_features': 150000, 'C': 1., 'max_iter': 1000, 'seed': 20261017},
        'teacher_threshold': .5, 'teacher_prompt_source': 'new S1 definition + independent synthetic examples',
        'gold_policy': 'aggregate outputs only; diagnostics cannot affect data, prompt, threshold or model choice',
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [OLD / 'admitted.jsonl', OLD / 'gold.jsonl']},
    })


def probe():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from stage_d_prime_data import view
    if (OUT / 'old-probe.json').exists(): raise ValueError('Diagnostic already recorded')
    all_rows = mapped(read(OLD / 'admitted.jsonl'))
    train = [r for r in all_rows if r['split'] == 'train']
    start = time.time()
    vector = TfidfVectorizer(analyzer='char', ngram_range=(3, 5), max_features=150000, sublinear_tf=True)
    x = vector.fit_transform([view(r)['fragment'] for r in train])
    clf = LogisticRegression(C=1., max_iter=1000, random_state=20261017).fit(x, [r['label'] for r in train])
    result = {'class_order': list(clf.classes_), 'fit_seconds': time.time()-start, 'evaluations': {}}
    for split in ('validation', 'heldout', 'gold'):
        rows = mapped(read(OLD / 'gold.jsonl')) if split == 'gold' else [r for r in all_rows if r['split'] == split]
        start = time.time(); ps = clf.predict_proba(vector.transform([view(r)['fragment'] for r in rows]))
        ps = ps[:, [list(clf.classes_).index(label) for label in ('request', 'quoted', 'none')]]
        result['evaluations'][split] = {'metrics': groups(rows, ps), 'latency_ms_per_fragment': (time.time()-start)*1000/len(rows)}
    write_new(OUT / 'old-probe.json', result)
    print(json.dumps({'diagnostic': 'old_probe', 'metrics': {s: v['metrics']['all'] for s,v in result['evaluations'].items()}}), flush=True)


def models(smoke=False):
    import torch
    from laya.train import load_checkpoint
    from train_stage_d import hashes
    from stage_d_prime_model import predict
    torch.set_num_threads(4); device = torch.device('cuda:0')
    output = OUT / ('old-model-smoke.json' if smoke else 'old-model-diagnostic.json')
    if output.exists(): raise ValueError('Diagnostic already recorded')
    old_rows = ([{'id': 'synthetic-smoke', 'text': 'Please restart the practice counter.', 'source_type': 'TOOL_RET', 'label': 'for_reader', 'language': 'en'}]
                if smoke else read(OLD / 'gold.jsonl'))
    rows = mapped(old_rows); results = {}
    for name, path in [('english', OLD / 'D2Guard-Laya-english'), ('multilingual_epoch2', OLD / 'multilingual-best-work')]:
        before = hashes(path); copy = OUT / ('diagnostic-copy-' + name)
        if not copy.exists(): shutil.copytree(path, copy)
        model, tok, cfg = load_checkpoint(str(copy)); model.to(device).eval()
        ps, z, lat, windows = predict(model, tok, old_rows, device, temperature=1)
        results[name] = {'metrics': groups(rows, merge_old(ps)), 'latency_ms_per_fragment': lat, 'window_n': sum(windows),
                         'sha256': before, 'original_unchanged': hashes(path) == before}
        if not results[name]['original_unchanged']: raise ValueError('Original checkpoint changed')
        del model; torch.cuda.empty_cache()
        print(json.dumps({'diagnostic': name, 'smoke': smoke, 'metrics': results[name]['metrics']['all']}), flush=True)
    write_new(output, results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['register', 'probe', 'models', 'smoke'])
    action = parser.parse_args().action
    {'register': register, 'probe': probe, 'models': models, 'smoke': lambda: models(True)}[action]()
