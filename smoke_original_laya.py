"""Infrastructure smoke check only; synthetic empty facts are NOT defense evidence."""
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from original_laya import OriginalLaya


def main():
    root = Path(__file__).parent
    model = OriginalLaya(root / '.local/laya.json')
    probes = []
    for _ in range(3):
        model.classify_security({'authorization_known': False, 'active_risk_refs': []},
            {'event_kind': 'tool_return', 'facts': [], 'coverage_complete': False})
        if not model.last_trace['model_used']:
            raise RuntimeError('Original Laya did not produce a usable untruncated answer: '+str(model.last_trace.get('error_type')))
        probes.append(model.last_trace)
    result = {'kind': 'original-checkpoint-infrastructure-smoke-only',
        'production_backend_switched': False, 'security_accuracy_validated': False,
        'metadata': model.metadata, 'probes': probes,
        'median_probe_ms': statistics.median(x['latency_ms'] for x in probes),
        'note': 'Synthetic empty evidence. No Agent, attack, tools or remote LLM was run. Not a latency percentile benchmark.'}
    (root / 'docs/original-laya-readiness.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'model_used':True,'production_backend_switched':False,
        'median_probe_ms':result['median_probe_ms'],'probe_labels':[x['final_label'] for x in probes]}))


if __name__ == '__main__':
    main()
