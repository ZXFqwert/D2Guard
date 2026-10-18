"""Stage D-double-prime cloud adapter. Secrets never enter arguments or logs."""
from __future__ import annotations
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx

MODELS = ('deepseek-v4.1-flash', 'mimo-v2.6-flash')
# User-authorized final reference only; never changes the training teachers.
EVALUATION_ONLY_MODELS = ('mimo-v2.5',)
# The intermediary accepts the requested name but sometimes reports its own
# suffix. Preserve that identity; this does not certify the upstream weights.
RETURNED_NAMES = {'deepseek-v4.1-flash': {'deepseek-v4.1-flash', 'deepseek-v4.1-flash-mod',
                                       'deepseek-v4-1-flash', 'cb/deepseek-v4.1-flash'},
                  'mimo-v2.6-flash': {'mimo-v2.6-flash'},
                  'mimo-v2.5': {'mimo-v2.5'}}
ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()


class CloudFailure(RuntimeError):
    """A deliberately sanitized error, without response bodies or headers."""


def credentials():
    values = {}
    for line in (ROOT / '.local/teacher.env').read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('\"\'')
    base, key = values['D2_TEACHER_BASE_URL'].rstrip('/'), values['D2_TEACHER_API_KEY']
    if urlsplit(base).scheme != 'https' or not key:
        raise CloudFailure('Invalid local teacher configuration')
    return base, key


def call(model, messages, *, max_tokens=1024, temperature=0, log_path=None, thinking=None):
    if model not in MODELS + EVALUATION_ONLY_MODELS:
        raise CloudFailure('Model is not in the preregistered allowlist')
    base, key = credentials()
    started = time.monotonic()
    usage = None
    try:
        payload={'model':model,'messages':messages,'temperature':temperature,'max_tokens':max_tokens,'response_format':{'type':'json_object'}}
        if thinking is not None:payload['thinking']={'type':'enabled' if thinking else 'disabled'}
        with httpx.Client(timeout=90, trust_env=False) as client:
            response = client.post(base + '/chat/completions',
                headers={'Authorization': 'Bearer ' + key},
                json=payload)
        if response.status_code != 200:
            raise CloudFailure('HTTP status ' + str(response.status_code))
        body = response.json()
        usage = {k: v for k, v in body.get('usage', {}).items()
                 if k in ('prompt_tokens', 'completion_tokens', 'total_tokens') and isinstance(v, int)}
        if body.get('model') not in RETURNED_NAMES[model]:
            actual = body.get('model', '')
            safe = actual if isinstance(actual, str) and re.fullmatch(r'[A-Za-z0-9._:/-]{1,100}', actual) and key not in actual else '[invalid]'
            raise CloudFailure('Returned model name differs: ' + safe)
        with LOCK:
            identity_path = ROOT / '.local/stage-d2/returned-models.json'
            identities = json.loads(identity_path.read_text()) if identity_path.exists() else {}
            counts = identities.setdefault(model, {})
            counts[body['model']] = counts.get(body['model'], 0) + 1
            identity_path.write_text(json.dumps(identities, indent=2), encoding='utf-8')
        choice = body['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise CloudFailure('Incomplete response')
        content = choice['message']['content']
        if key in content:
            raise CloudFailure('Credential echo rejected')
        content = content.strip()
        fence = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if fence:
            content = fence.group(1)
        return json.loads(content), (time.monotonic() - started) * 1000
    except CloudFailure:
        raise
    except Exception as error:
        raise CloudFailure('Cloud operation failed: ' + type(error).__name__) from None
    finally:
        if log_path:
            with LOCK:
                with Path(log_path).open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps({'model': model, 'seconds': time.monotonic() - started,
                                             'tokens': usage}) + '\n')


def smoke():
    out = ROOT / '.local/stage-d2'
    result_path = out / 'cloud-smoke.json'
    if result_path.exists():
        raise CloudFailure('Smoke already recorded; preserve the previous attempt')
    results = []
    for model in MODELS:
        try:
            response, ms = call(model, [
                {'role': 'system', 'content': 'Return JSON only with key label, value request or none. An operation instruction, including a legitimate human instruction, is request.'},
                {'role': 'user', 'content': 'Synthetic maintenance note: Please restart the demo counter after the practice session.'}
            ], max_tokens=256, log_path=out / 'cloud-requests.jsonl')
            results.append({'model': model, 'usable': response.get('label') == 'request', 'latency_ms': ms})
        except CloudFailure as error:
            results.append({'model': model, 'usable': False, 'error': str(error)})
    result_path.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    smoke()
