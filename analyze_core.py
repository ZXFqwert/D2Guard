"""Offline decision ablations over recorded real events. Never runs Pi or tools.

These counterfactual decisions are NOT live attacks or extra defense successes.
The slow mirror is disabled: it cannot change the kernel's verdict in this version.
"""
import argparse
import json
import sys
import tempfile
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from core_guard import CoreGuard, TOOLS
from d2core.models import FastMirrorLabel, ProposedAction, SecurityState
from d2core.policy_engine import PolicyEngine


class NeutralFast:
    def classify(self, *args, **kwargs):
        return FastMirrorLabel(content_nature='informational', action_alignment='expected', latency_ms=0)


def analyze(folder):
    events = [json.loads(line) for line in (folder / 'audit.jsonl').read_text(encoding='utf-8').splitlines()]
    results = []
    with tempfile.TemporaryDirectory() as temp:
        core = CoreGuard(True, temp, {'base_url':'', 'api_key':'', 'main_model':'disabled',
                                     'api_style':'responses'}, lambda *args: None)
        for event in events:
            if event['type'] != 'guard_decision':
                core.observe(event)
                continue
            action = ProposedAction(session_id=core.state.session_id, call_id=event['call_id'],
                agent_id=event['agent_id'], tool_name=TOOLS[event['tool']], tool_args=event['args'], current_plan='')
            if event.get('policy') or event['verdict'] in ('ASK', 'BLOCK'):
                row = {'call_id':action.call_id, 'tool':action.tool_name, 'live_verdict':event['verdict'],
                       'live_policy':event.get('policy'), 'variants':{}}
                for mode in ('full', 'without_d1', 'without_d2_history', 'without_hard_policy'):
                    state = core.state.model_copy(deep=True)
                    engine = PolicyEngine(ROOT/'src/d2core/policies.yaml', folder/'workspace', core.fast, core.slow)
                    if mode == 'without_d1':
                        engine.fast = NeutralFast()
                        state.evidence_by_agent.clear()
                    elif mode == 'without_d2_history':
                        state = SecurityState(session_id=state.session_id, armor_enabled=True,
                                              anchor_intent=state.anchor_intent)
                    elif mode == 'without_hard_policy':
                        engine.hard_check = lambda *_: (None, 'Offline ablation: hard policies disabled')
                    decision = engine.decide(state, action, review=False)
                    row['variants'][mode] = {'verdict':decision.verdict.value,
                        'policy':decision.matched_policy_id,
                        'fast_label':decision.fast_mirror_label.model_dump(mode='json', exclude={'latency_ms'})}
                results.append(row)
            # Advance only the kernel state; no tool, network or model execution.
            core.engine.decide(core.state, action, review=False)
    report = {'run_id':folder.name, 'kind':'offline_counterfactual_not_live_run',
        'recorded_audit_sha256':hashlib.sha256((folder/'audit.jsonl').read_bytes()).hexdigest(),
        'analysis_source_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__), ROOT/'src/core_guard.py', *sorted((ROOT/'src/d2core').glob('*.py'))]},
        'slow_mirror':'disabled; existing implementation is advisory-only', 'decisions':results,
        'scope':'Single observed trajectory; tests internal decision dependence, not general detection accuracy.'}
    (folder/'core-contributions.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run_dir',type=Path)
    analyze(p.parse_args().run_dir)
