"""Collect aggregate evidence into the single stage result deliverable."""
import argparse
import collections
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'.local/stage-d2'


def load(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def collect(status, reason):
    rounds={}
    for folder in sorted(OUT.glob('round-*')):
        if not folder.is_dir():continue
        evidence={}
        names=['generation-clock','generation-smoke','format-smoke','generation-summary','supplement-started',
               'supplement-summary','candidate-composition','isolation-smoke','before-supplement-isolation',
               'isolation','admission','probe','training-source-manifest','training-evaluation-clock',
               'training-runner','selected-before-heldout','round-evaluation','preparation-status',
               'generation-improvement','reuse-manifest','preparation-source-manifest','generation-source-manifest']
        names += [base+'-'+suffix for base in ('english','multilingual','modernbert') for suffix in ('smoke','training')]
        for name in names:
            value=load(folder/(name+'.json'))
            if isinstance(value,dict):
                value={k:v for k,v in value.items() if k not in ('rejections','discarded_disagreement_ids','discarded_missing_vote_ids')}
            evidence[name]=value
        admitted=folder/'admitted.jsonl'
        if admitted.exists():
            rows=[json.loads(line) for line in admitted.read_text(encoding='utf-8').splitlines() if line.strip()]
            part=[row for row in rows if row['split']!='public_heldout']
            nominal=sum(row['transform']!='plain' for row in part)
            invisible=sum(row['transform']=='unicode' and not re.search('[Ａ-Ｚａ-ｚ０-９]',row.get('raw_text','')) for row in part)
            evidence['obfuscation_crosscheck']={'n':len(part),'nominal_nonplain_n':nominal,
                'unicode_without_visible_fullwidth_alnum_n':invisible,
                'conservative_fraction':(nominal-invisible)/len(part) if part else None,
                'method':'Do not count a unicode-marked row without fullwidth letters/digits as an effective typography variant; dilution remains a semantic generation contract.'}
        rounds[folder.name]=evidence
    calls=collections.defaultdict(lambda:{'requests':0,'reported_usage_requests':0,'missing_usage_requests':0,
                                         'sum_seconds':0.,'reported_tokens':collections.Counter()})
    for line in (OUT/'cloud-requests.jsonl').read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        if set(row)!={'model','seconds','tokens'}:raise ValueError('Unexpected request log fields')
        aggregate=calls[row['model']];aggregate['requests']+=1;aggregate['sum_seconds']+=row['seconds']
        if row['tokens']:
            aggregate['reported_usage_requests']+=1;aggregate['reported_tokens'].update(row['tokens'])
        else:aggregate['missing_usage_requests']+=1
    python_log=(OUT/'unit-tests.log').read_text(encoding='utf-8',errors='replace')
    node_log=(OUT/'node-tests.log').read_text(encoding='utf-8',errors='replace')
    python_counts=re.findall(r'Ran (\d+) tests?',python_log)
    node_counts=re.findall(r'(?m)^(?:#|ℹ) tests (\d+)\s*$',node_log)
    unit={'python':{'count':int(python_counts[-1]) if python_counts else None,'passed':bool(re.search(r'\nOK\s*$',python_log)),
                    'log_sha256':hashlib.sha256((OUT/'unit-tests.log').read_bytes()).hexdigest()},
          'node':{'count':int(node_counts[-1]) if node_counts else None,'passed':bool(node_counts) and bool(re.search(r'(?m)^(?:#|ℹ) fail 0\s*$',node_log)) and bool(re.search(r'(?m)^(?:#|ℹ) pass '+node_counts[-1]+r'\s*$',node_log)),
                  'log_sha256':hashlib.sha256((OUT/'node-tests.log').read_bytes()).hexdigest()}}
    focused=OUT/'focused-tests.log'
    if focused.exists():
        content=focused.read_text(encoding='utf-8',errors='replace')
        counts=re.findall(r'Ran (\d+) tests?',content)
        unit['stage_d2_recheck']={'count':int(counts[-1]) if counts else None,'passed':bool(re.search(r'\nOK\s*$',content)),'log_sha256':hashlib.sha256(focused.read_bytes()).hexdigest()}
    artifacts=['protocol','implementation-clarifications','input-protocol','teacher-qualification-ready',
               'old-model-diagnostic','old-probe','gemma-diagnostic','model-sources','pretrained-verification',
               'final-selection','final-cloud-teachers','final-evaluation','regression-verification','secret-audit',
               'transport-change','final-evaluation-source-manifest','final-evaluation-transport-decoupling',
               'final-copy-preflight','final-evaluation-timing','teacher-replacement-authorization',
               'teacher-replacement-started','teacher-replacement-smoke','teacher-replacement-result',
               'teacher-replacement-partial','teacher-replacement-format-diagnostic','final-cloud-teachers-partial',
               'teacher-replacement-smoke-resume','teacher-replacement-named-smoke-resume',
               'teacher-replacement-none-smoke-diagnostic','s1-disabled-verification','final-consistency-verification',
               'final-cloud-teachers-outcome','teacher-replacement-missing-repair']
    result={'stage':'D-double-prime','status':status,'reason':reason,'collected_unix':time.time(),
            'accepted_checkpoint':subprocess.check_output(['git','rev-parse','a8bca80'],cwd=ROOT,encoding='utf-8',errors='replace').strip(),
            'unit_tests':unit,'rounds':rounds,'cloud_calls':dict(calls),
            'cloud_total_requests':sum(v['requests'] for v in calls.values()),
            'cloud_usage_note':'Provider-reported token fields are summed independently; missing usage is unknown, not zero. Sum of request durations is not wall time.',
            'returned_model_names':load(OUT/'returned-models.json'),
            'artifacts':{name:load(OUT/(name+'.json')) for name in artifacts},
            'public_sources':load(OUT/'round-1/public-sources.json'),
            'stage_e_started':False}
    local_final=result['artifacts']['final-evaluation']
    cloud_final=result['artifacts']['final-cloud-teachers'] or result['artifacts']['final-cloud-teachers-outcome']
    result['final_comparison']={
        'complete':bool(local_final) and bool(cloud_final) and all(v.get('complete') for v in cloud_final.values()),
        'models':{**({k:v for k,v in local_final['models'].items() if k!='cloud_teachers'} if local_final else {}),**(cloud_final or {})},
        'assembly_only_no_new_inference':True,
        'note':'Local models completed before replacement teacher. Their original final-evaluation artifact remains immutable; combine independently finalized references here.'}
    exclusions=load(OUT/'exclusions.json')
    current={name:(ROOT/name).exists() and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected
             for name,expected in exclusions['source_sha256'].items()}
    result['isolation_references']={'manifest_sha256':hashlib.sha256((OUT/'exclusions.json').read_bytes()).hexdigest(),
        'gold_exclusion_units':len(exclusions['frozen']),'payload_sentence_units':len(exclusions['payload_sentences']),
        'thresholds':exclusions['thresholds'],'source_sha256':exclusions['source_sha256'],
        'current_source_matches':current,'all_sources_unchanged':all(current.values())}
    source_files=sorted(ROOT.glob('stage_d2_*.py'))+[ROOT/'train_stage_d2.py',ROOT/'evaluate_stage_d2.py',ROOT/'tests/test_stage_d2.py']
    result['local_support_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'.local/stage_d2_repair_v25.py',ROOT/'.local/stage_d2_finish_report.py'] if p.exists()}
    result['stage_d2_changed_files']=[str(p.relative_to(ROOT)) for p in source_files]+['docs/21-stage-d2-report.md','docs/stage-d2-results.json','docs/stage-d2-verification.md','docs/03-status.md','docs/整体设计文档.md']
    result['implementation_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    target=ROOT/'docs/stage-d2-results.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 阶段 D″ 核验摘要','',f'状态：**{status}**。{reason}','',
           f'- 已验收检查点：`{result["accepted_checkpoint"]}`；D′0 独立提交，D″ 改动未混入。',
           f'- Python：{unit["python"]["count"]} 项，日志确认通过：{unit["python"]["passed"]}；Node：{unit["node"]["count"]} 项，通过：{unit["node"]["passed"]}。',
           f'- C/C2 金标准、片段导出和场景来源哈希：{len(current)} 个文件，全部保持冻结时内容：{all(current.values())}。',
           '- 隔离阈值：字符 5-gram Jaccard ≥0.5、BGE-M3 cosine ≥0.9；原文与载荷句式排除，软件任务领域保留。',
           '- 请求日志字段仅为模型名、耗时、token 数；不包含正文、认证头或密钥。',
           f'- 云端模型调用总数：{result["cloud_total_requests"]}；缺失 usage 单独计数，不视为零 token。','']
    for name, evidence in rounds.items():
        lines += [f'## {name}','']
        isolation=evidence.get('isolation');admission=evidence.get('admission');probe=evidence.get('probe')
        lines += [f'- 隔离：{isolation["split"] if isolation else "未完成"}。',
                  f'- 准入：{admission["passed"] if admission else "未完成"}；本轮新候选三方一致 {admission["unanimous_n"] if admission else "未知"} 条。',
                  f'- 原样复用训练：{admission.get("reused_training_n",0) if admission else 0} 条；验证：{admission.get("reused_frozen_validation_n",0) if admission else 0} 条；保留：{admission.get("reused_frozen_heldout_n",0) if admission else 0} 条。',
                  f'- 训练前捷径门槛：{probe["pretrain_passed"] if probe else "未运行"}。']
        for base in ('english','multilingual','modernbert'):
            training=evidence.get(base+'-training')
            if training:
                best=min(training['history'],key=lambda row:row['validation_loss'])['epoch']
                lines.append(f'- {base}：恢复 epoch {training["best_epoch"]}，是否为验证 loss 最低 epoch：{best==training["best_epoch"]}；原版权重未改动：{training["original_unchanged"]}。')
            else:lines.append(f'- {base}：没有已完成训练记录。')
        lines.append('')
    final=result['artifacts']['final-evaluation'];regression=result['artifacts']['regression-verification']
    lines += ['## 冻结评测与真实回归','',
              f'- 最终金标准评测：{("通过" if final["gold_passed"] else "未达线") if final else "未执行"}。',
              f'- S1 验收启用资格：{final["enable_s1"] if final else False}。',
              '- 独立语义召回：所选第二轮英文 Laya 为 170/210（80.95%），低于 85%；金标准通过不能抵消该缺口。',
              '- 真实回归：'+('详见机读文件中的 regression-verification 运行 ID、核验与抽样记录。' if regression and regression.get('runs') else '未执行；没有本阶段运行 ID 或 verify_v2 结果，不引用旧阶段批次替代。'),
              f'- 最终七对照覆盖完整：{result["final_comparison"]["complete"]}；替换教师仅用于最终参照，训练三方标注不改写。',
              f'- 已知教师密钥扫描通过：{bool(result["artifacts"].get("secret-audit") and result["artifacts"]["secret-audit"].get("passed"))}。',
              '- MiMo v2.5：362/364 唯一输入、1012/1014 加权片段有效；缺 request 与 none 各 1，完整指标不可得，子集指标单列。',
              '- 未开始阶段 E。','',
              '完整分布、每 epoch loss、模型与源码哈希、模型指标和调用量见 `stage-d2-results.json`；解释与验收逐条自检见 `21-stage-d2-report.md`。','']
    (ROOT/'docs/stage-d2-verification.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':status,'rounds':len(rounds),'cloud_total_requests':result['cloud_total_requests'],'output':str(target)}))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--status',required=True)
    p.add_argument('--reason',required=True)
    a=p.parse_args()
    collect(a.status,a.reason)
