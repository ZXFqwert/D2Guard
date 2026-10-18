"""Fresh pre-fit candidates, same contracts and clock; never relabel discarded rows."""
import argparse
import collections
import concurrent.futures
import hashlib
import json
import random
import time
from pathlib import Path
from stage_d2_data import OUT, ROOT, contract, generate


def main(number, train_n, validation_n):
    folder = OUT / f'round-{number}'
    if any(folder.glob('*-fit-started.json')) or (OUT / 'final-selection.json').exists():
        raise ValueError('Supplement is only allowed before fitting')
    started = json.loads((folder / 'generation-clock.json').read_text())['started_unix']
    rows = [contract(split, 10000 + i, number) for split, n in
            [('train', train_n), ('validation', validation_n)] for i in range(n)]
    random.Random(20261017).shuffle(rows)
    manifest = {'started_unix': time.time(), 'original_generation_started_unix': started,
                'reason': 'Isolated validation candidates below 600; fresh validation and training reserve before any teacher review or fitting',
                'counts': {'train': train_n, 'validation': validation_n}, 'same_contracts': True,
                'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                                  ('stage_d2_supplement.py', 'stage_d2_data.py', 'stage_d2_cloud.py')}}
    with (folder / 'supplement-started.json').open('x') as f:
        json.dump(manifest, f, indent=2)
    counts, failures = collections.Counter(), collections.Counter()
    attempted = 0
    with (folder / 'generated-supplement.jsonl').open('x', encoding='utf-8') as stream:
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            iterator = iter(rows)
            pending = set()
            for _ in range(min(32, len(rows))):
                pending.add(pool.submit(generate, next(iterator)))
            while pending:
                if time.time()-started >= 10700:
                    for future in pending:future.cancel()
                    raise TimeoutError('Original three-hour generation/review clock expires')
                done, pending = concurrent.futures.wait(pending, timeout=20, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    attempted += 1
                    try:
                        row = future.result()
                        stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                        stream.flush()
                        counts[row['split']] += 1
                    except Exception as error:
                        failures[type(error).__name__] += 1
                    row = next(iterator, None)
                    if row is not None:
                        pending.add(pool.submit(generate, row))
                state = {'attempted': attempted, 'generated': dict(counts), 'failures': dict(failures), 'seconds': time.time()-started}
                (folder / 'supplement-progress.json').write_text(json.dumps(state, indent=2))
    (folder / 'supplement-summary.json').write_text(json.dumps(state, indent=2))
    print(json.dumps(state), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--round', type=int, default=1)
    p.add_argument('--train', type=int, default=800)
    p.add_argument('--validation', type=int, default=800)
    a = p.parse_args()
    main(a.round, a.train, a.validation)
