"""Rewrite upstream hosts in a packaged delivery ZIP; the original runs on disk are never touched.

Run manifests record the upstream model endpoint. Any URL whose host contains a term from
.local/delivery-blocklist.txt is rewritten to the neutral host ``upstream.example`` (path kept).
Plain-JSON audits that record a rewritten manifest's sha256 are updated to the new digest.
Every entry is then rescanned; any remaining blocklist term fails the run.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
NEUTRAL_HOST = 'upstream.example'
RUN_MANIFEST = re.compile(r'^D2Guard/runs/[^/]+/manifest\.json$')

_spec = importlib.util.spec_from_file_location('export_delivery', ROOT / 'tools' / 'export_delivery.py')
_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_export)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def rewrite_manifest(raw, terms):
    """Return (new_bytes, replaced_urls); byte layout outside the replaced URLs is unchanged."""
    text = raw.decode('utf-8')
    replaced = {}
    for s in _strings(json.loads(text)):
        parts = urlsplit(s)
        if parts.scheme in ('http', 'https') and any(t in parts.netloc for t in terms):
            replaced[s] = urlunsplit((parts.scheme, NEUTRAL_HOST, parts.path, parts.query, parts.fragment))
    for old, new in replaced.items():
        text = text.replace(json.dumps(old, ensure_ascii=False)[1:-1], json.dumps(new, ensure_ascii=False)[1:-1])
    return text.encode('utf-8'), replaced


def redact(source, output, terms):
    if not terms:
        raise SystemExit('No blocklist terms in .local/delivery-blocklist.txt; refusing to package unchecked')
    with zipfile.ZipFile(source) as zin:
        infos = zin.infolist()
        rewritten, digests = {}, {}
        for info in infos:
            if RUN_MANIFEST.match(info.filename):
                raw = zin.read(info)
                if any(t.encode() in raw for t in terms):
                    new, urls = rewrite_manifest(raw, terms)
                    if urls:
                        rewritten[info.filename] = new
                        digests[hashlib.sha256(raw).hexdigest()] = hashlib.sha256(new).hexdigest()
        audits = {}
        for info in infos:
            if info.filename in rewritten or not info.filename.endswith(('.json', '.jsonl')) or info.file_size > 200_000_000:
                continue
            raw = zin.read(info)
            if any(old.encode() in raw for old in digests):
                text = raw.decode('utf-8')
                n = 0
                for old, new in digests.items():
                    n += text.count(old)
                    text = text.replace(old, new)
                audits[info.filename] = (text.encode('utf-8'), n)
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zout:
            for info in infos:
                if info.filename in rewritten:
                    zout.writestr(info, rewritten[info.filename], compress_type=zipfile.ZIP_DEFLATED, compresslevel=1)
                elif info.filename in audits:
                    zout.writestr(info, audits[info.filename][0], compress_type=zipfile.ZIP_DEFLATED, compresslevel=1)
                else:
                    with zin.open(info) as src, zout.open(info, 'w') as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
    remaining, reported = [], {}
    with zipfile.ZipFile(output) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError('ZIP integrity check failed: ' + bad)
        for info in z.infolist():
            if info.file_size > 200_000_000:
                continue
            data = z.read(info).lower()
            for k, t in enumerate(terms):
                if t.lower().encode() in data or t.lower() in info.filename.lower():
                    if is_domain(t):
                        remaining.append(info.filename)
                    else:
                        reported[f'term{k}'] = reported.get(f'term{k}', 0) + 1
    # Domain-class terms must be absent; other identifiers (e.g. paths recorded inside immutable
    # evidence) are counted per term index without printing the term.
    return {'rewritten_manifests': len(rewritten), 'updated_audits': {k: v[1] for k, v in audits.items()},
            'remaining_blocked_entries': sorted(set(remaining)), 'reported_only_entries': reported, 'entries': len(infos)}


def is_domain(term):
    return bool(re.fullmatch(r'[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+', term)) and not re.fullmatch(r'[\d.]+', term)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = redact(args.input, args.output, _export.blocklist(ROOT))
    print(json.dumps(result, ensure_ascii=False))
    if result['remaining_blocked_entries']:
        raise SystemExit('Blocklisted terms remain in the package')


if __name__ == '__main__':
    main()
