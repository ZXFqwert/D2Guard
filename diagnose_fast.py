"""Offline input/feature diagnosis. No Pi, tool side effects, model API or training.

Reconstructs the actual classifier arguments from recorded events, including the
policy engine's mutations BEFORE classification. Counterfactual labels are not
new live defense results. Full inputs are retained only in ignored local output.
"""
import argparse
import ast
from collections import Counter, defaultdict
import contextlib
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from core_guard import CoreGuard, TOOLS
from d2core.mirrors import _forward_distilled
from d2core.models import ProposedAction


def tokens(text, plan, chain):
    combined = f'{text}\n[PLAN]{plan}\n[CHAIN]{json.dumps(chain, sort_keys=True, ensure_ascii=False)}'.casefold()
    result = set(re.findall(r'[a-z0-9_./:-]{2,}|[\u4e00-\u9fff]{2,}', combined))
    result.update([f"__anchor:{chain.get('anchor_type', 'unanchored')}", f"__tool:{chain.get('proposed_tool', 'none')}"])
    if chain.get('taint_active'):
        result.add('__taint:active')
    if float(chain.get('max_coverage_ratio') or 0) >= .5:
        result.add('__cov:high')
    if int(chain.get('secret_ledger_count') or 0) > 0:
        result.add('__secrets:present')
    return result


def logits(spec, feature_set):
    hidden = list(spec['b1'])
    for token in sorted(feature_set):
        index = spec['vocab'].get(token)
        if index is not None:
            hidden = [h+w for h,w in zip(hidden,spec['w1'][index])]
    hidden = [max(0,h) for h in hidden]
    result = {}
    for head, names in [('nature',spec['nature_classes']),('align',spec['align_classes'])]:
        values = [bias+sum(h*row[i] for h,row in zip(hidden,spec['w_'+head])) for i,bias in enumerate(spec['b_'+head])]
        result[head] = dict(zip(names,values))
    result['label'] = [max(result[h],key=result[h].get) for h in ('nature','align')]
    result['deviant_minus_expected'] = result['align']['deviant']-result['align']['expected']
    return result


class CaptureFast:
    def __init__(self, delegate):
        self.delegate, self.inputs = delegate, []

    def classify(self, text, plan='', state_chain=None):
        result = self.delegate.classify(text,plan,state_chain)
        self.inputs.append({'text':text, 'plan':plan, 'state_chain':copy.deepcopy(state_chain),
                            'returned_label':result.model_dump(mode='json'), 'trace':copy.deepcopy(self.delegate.last_trace)})
        return result

    @property
    def last_trace(self):
        return self.delegate.last_trace


def reconstruct(folder):
    audit = [json.loads(s) for s in (folder/'audit.jsonl').read_text(encoding='utf-8').splitlines()]
    core_log = [json.loads(s) for s in (folder/'core.jsonl').read_text(encoding='utf-8').splitlines()]
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    original = {e['call_id']:e for e in core_log if e['type']=='core_decision'}
    captures = []
    with tempfile.TemporaryDirectory() as temp:
        core = CoreGuard(manifest['protection']=='on',temp,{'base_url':'','api_key':'','main_model':'disabled','api_style':'responses'},lambda *args:None)
        spy = CaptureFast(core.fast)
        core.fast = core.engine.fast = spy
        for event in audit:
            start = len(spy.inputs)
            if event['type']=='guard_decision':
                action = ProposedAction(session_id=core.state.session_id,call_id=event['call_id'],agent_id=event['agent_id'],
                    tool_name=TOOLS[event['tool']],tool_args=event['args'],current_plan='')
                core.engine.decide(core.state,action,review=False)
            else:
                core.observe(event)
            for captured in spy.inputs[start:]:
                captured.update(event_type=event['type'],call_id=event.get('call_id'),tool=event.get('tool'))
                if event['type']=='guard_decision' and event['call_id'] in original:
                    old = original[event['call_id']]
                    captured['recorded_model_label'] = old['fast']['model_label']
                    captured['logged_state_before'] = old['state_before']
                    captured['actual_chain_diff_from_logged_before'] = {
                        k:{'logged_before':old['state_before'].get(k),'actual_model_input':v}
                        for k,v in captured['state_chain'].items() if old['state_before'].get(k)!=v}
                captures.append(captured)
    return captures


def training_audit(spec, script):
    # Execute ONLY the two deterministic dataset helper definitions; no torch,
    # training loop, model loader or main() from the historical file is executed.
    tree = ast.parse(script.read_text(encoding='utf-8-sig'))
    subset = ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and
        n.name in {'build_dataset','tokenize_chain_sample'}],type_ignores=[])
    namespace = {'random':random,'json':json,'re':re}
    exec(compile(subset,str(script),'exec'),namespace)
    data = namespace['build_dataset'](20261015)
    split = int(len(data)*.85)
    groups = {'all':data,'train':data[:split],'validation':data[split:]}
    counts = {}
    for name, rows in groups.items():
        pairs = Counter((r['state_chain']['proposed_tool'],spec['align_classes'][r['align']]) for r in rows)
        counts[name] = {'size':len(rows),'tool_alignment':[{'tool':t,'alignment':a,'count':n} for (t,a),n in sorted(pairs.items())],
            'empty_plan_by_alignment':dict(Counter(spec['align_classes'][r['align']] for r in rows if not r['plan'])),
            'alignment_counts':dict(Counter(spec['align_classes'][r['align']] for r in rows)),
            'unique_text_templates':len({re.sub(r'\s*\[(?:step|trace)=\d+\]|\s*#\d+$|summary_\d+', '',r['text']).strip() for r in rows})}
    frequency = Counter(t for r in data[:split] for t in namespace['tokenize_chain_sample'](r['text'],r['plan'],r['state_chain']))
    vocabulary = {t:i for i,(t,n) in enumerate([(t,n) for t,n in sorted(frequency.items(),key=lambda kv:(-kv[1],kv[0])) if n>=2][:512])}
    correct = Counter()
    for r in data[split:]:
        pred = _forward_distilled(spec,r['text'],r['plan'],r['state_chain'])
        nature = pred[0]==spec['nature_classes'][r['nature']]
        alignment = pred[1]==spec['align_classes'][r['align']]
        correct.update(nature=int(nature),alignment=int(alignment),joint=int(nature and alignment))
    # Template overlap, not just duplicate full rows: changing trace numbers does
    # not create an independent linguistic/generalization test.
    template = lambda r: re.sub(r'\s*\[(?:step|trace)=\d+\]|\s*#\d+$|summary_\d+', '',r['text']).strip()
    train_templates = {template(r) for r in data[:split]}
    return {'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(), 'groups':counts,
        'reconstructed_vocab_matches_checkpoint':vocabulary==spec['vocab'],
        'validation_correct_counts':dict(correct),'validation_size':len(data)-split,
        'validation_rows_with_text_template_seen_in_training':sum(template(r) in train_templates for r in data[split:])}


def diagnose(folder, out):
    weights = ROOT/'src/d2core/weights/laya_d2_distilled.json'
    spec = json.loads(weights.read_text(encoding='utf-8'))
    captured = reconstruct(folder)
    selected = next(c for c in captured if c['event_type']=='guard_decision' and c['tool']=='fs_write')
    text,plan,chain = selected['text'][:8192],selected['plan'][:4096],selected['state_chain']
    actual = tokens(text,plan,chain)
    forward = logits(spec,actual)
    variants = {}
    def add(name,txt=text,pl=plan,ch=chain):
        variants[name] = {'label':list(_forward_distilled(spec,txt,pl,ch)),
                         'deviant_minus_expected':logits(spec,tokens(txt,pl,ch))['deviant_minus_expected']}
    add('actual')
    add('same_delta_with_logged_prior_state',ch=selected['logged_state_before'])
    add('same_delta_without_chain',ch={})
    add('chain_only_no_delta',txt='')
    add('same_delta_tool_changed_to_fs_read',ch={**chain,'proposed_tool':'fs.read'})
    add('same_delta_without_recent_call_sequence',ch={**chain,'prior_call_chain':[]})
    task = (folder/'task.txt').read_text(encoding='utf-8')
    add('counterfactual_user_task_in_plan_slot_NOT_a_real_plan',pl=task,ch={**chain,'has_plan':True})
    impacts=[]
    for token in actual & spec['vocab'].keys():
        ablated = logits(spec,actual-{token})
        impacts.append({'token':token,'label_without_token':ablated['label'],
            'delta_in_deviant_margin_when_removed':forward['deviant_minus_expected']-ablated['deviant_minus_expected']})
    impacts.sort(key=lambda r:r['delta_in_deviant_margin_when_removed'],reverse=True)
    # Removing all aliases of the tool identity is a feature intervention, not a
    # valid action or permission change. Retain this distinction in the report.
    without_write = {t for t in actual if 'fs.write' not in t}
    variants['remove_all_fs_write_features_only'] = logits(spec,without_write)
    moved = tokens('',plan,{**chain,'untrusted_extra_field':text})
    # Extra field name might be unknown; compare the actual active vocabulary.
    known = lambda ts: ts & spec['vocab'].keys()
    report = {'kind':'offline_fast_input_diagnosis_not_live_run','run_id':folder.name,'call_id':selected['call_id'],
        'weights_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),
        'audit_sha256':hashlib.sha256((folder/'audit.jsonl').read_bytes()).hexdigest(),
        'input':selected,'checkpoint_shape':{'vocab_size':len(spec['vocab']),'hidden_dim':len(spec['b1'])},
        'reconstructed_forward':forward,'matched_features':sorted(known(actual)),
        'feature_counts':{'total':len(actual),'matched':len(known(actual))},'variants':variants,
        'leave_one_feature_out':impacts,
        'moving_entire_delta_to_chain_extra_field_preserves_model_features':known(actual)==known(moved),
        'training':training_audit(spec,ROOT.parent/'D2guard_core/offline_training/train_d2_laya.py'),
        'all_recorded_decision_labels_reproduced':all(list(_forward_distilled(spec,c['text'][:8192],c['plan'][:4096],c['state_chain']))==c['recorded_model_label']
            for c in captured if c['event_type']=='guard_decision' and c.get('recorded_model_label')),
        'notes':['Exact classifier inputs reconstructed from actual observations; no tools executed.',
                 'Margins are raw logits, not calibrated probabilities. Counterfactual outputs are not defense successes.']}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['run_id','checkpoint_shape','feature_counts','all_recorded_decision_labels_reproduced','variants']},ensure_ascii=False,indent=2))
    print('TOP_FEATURES',json.dumps(impacts[:8],ensure_ascii=False))
    print('TRAINING',json.dumps(report['training'],ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir',type=Path)
    parser.add_argument('--out',type=Path,default=ROOT/'.local/diagnostics/fast-input.json')
    args=parser.parse_args()
    diagnose(args.run_dir,args.out)
