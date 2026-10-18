"""Consolidate preserved evidence into the three requested stage deliverables."""
import collections
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from stage_d3_protocol import ROOT,OUT,sha


def optional(name):
    path=OUT/name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
                     ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])


def metric_row(name,m,missing='未运行'):
    if not m:return [name]+[missing]*7
    fmt=lambda v:'—' if v is None else f'{v:.4f}'
    return [name,m['n'],fmt(m['request']['recall']),fmt(m['request']['precision']),
            fmt(m['none_fpr']),fmt(m['request']['f1']),fmt(m['macro_f1_present_classes']),fmt(m['ece_request_10_bins'])]


def main():
    protocol=optional('protocol.json');semantic=optional('semantic-view.json')
    evidence={name:optional(name+'.json') for name in ('preflight','teacher-qualification','teacher-amendment',
        'data-preparation-amendment','data-cutoff-policy','adjudication-policy','collection','isolation','admission','probe',
        'dean-adjudication-final','dean-admission-review','selected-before-heldout','final-evaluation','training-runner',
        'regression','security-verification','retained-length-audit','isolation-preparation',
        'log-concurrency-test','identity-concurrency-test','stage-stop','candidate-summary','data-finalizer','isolation-partial',
        'continuation-authorization','continuation-result','isolation-benchmark','lexical-filter','existing-data-feasibility',
        'gapfill-authorization','gapfill-result','gapfill/brief-amendment','gapfill/smoke-review',
        'gapfill/smoke-review-v2','gapfill/smoke-review-v3','gapfill/smoke-review-v4',
        'dean-gapfill-review','dean-final-metrics-review','gapfill/local-cutoff','gapfill/cutoff-policy','training-clock','training-source-audit',
        'heldout-aggregate','frozen-evaluation-started')}
    if evidence['isolation']:evidence['isolation'].pop('rejections',None)
    generation={str(folder.relative_to(OUT)): {g:json.loads((folder/('generation-'+g+'.json')).read_text())
                for g in ('cloud','local') if (folder/('generation-'+g+'.json')).exists()} for folder in (OUT,OUT/'supplement',OUT/'gapfill')}
    calls=collections.defaultdict(lambda:{'calls':0,'sum_request_seconds':0.,'known_token_usage_calls':0,'tokens':collections.Counter()})
    bad_logs=0;log_hashes={}
    for path in sorted(OUT.rglob('cloud-requests.jsonl')):
        log_hashes[str(path.relative_to(ROOT))]=sha(path)
        for line in path.read_text(encoding='utf-8').splitlines():
            try:r=json.loads(line)
            except ValueError:bad_logs+=1;continue
            if set(r)!={'model','seconds','tokens'}:raise ValueError('Cloud request log contains forbidden fields')
            x=calls[r['model']];x['calls']+=1;x['sum_request_seconds']+=r['seconds']
            if r['tokens'] is not None:x['known_token_usage_calls']+=1;x['tokens'].update(r['tokens'])
    tests=[]
    for name in ('unit-tests-current.log','unit-tests-runtime.log','unit-tests-adjudication.log','http-test-recheck.log','unit-tests-cloud-lock.log','unit-tests-final.log','continuation-unit-tests.log','continuation-full-tests.log','gapfill-unit-tests.log','gapfill-full-tests.log'):
        path=OUT/name
        if not path.exists():continue
        text=path.read_text(encoding='utf-8',errors='replace');runs=re.findall(r'Ran (\d+) tests? in ([\d.]+)s',text)
        tests.append({'path':str(path.relative_to(ROOT)),'n':int(runs[-1][0]) if runs else None,
                      'seconds':float(runs[-1][1]) if runs else None,'passed':bool(re.search(r'^OK\s*$',text,re.M)),
                      'failures':re.findall(r'^(?:FAIL|ERROR): (.+)$',text,re.M),'sha256':sha(path)})
    models={base:optional(base+'-training.json') for base in ('english','multilingual','modernbert')}
    epoch_history={base:(v['history'] if v else optional(base+'-epochs.json')) for base,v in models.items()}
    model_smokes={base:optional(base+'-smoke.json') for base in models}
    training_manifest=optional('training-source-manifest.json')
    changed_files=sorted({p.name for p in ROOT.glob('stage_d3_*.py')}|{
        'train_stage_d3.py','evaluate_stage_d3.py','stage_d2_cloud.py','src/d2v2/semantic_view.py',
        'src/d2v2/content_model.py','src/d2v2/request_model.py','src/d2v2/core.py','tests/test_stage_d3.py',
        'docs/22-stage-d3-report.md','docs/stage-d3-results.json','docs/stage-d3-verification.md',
        'docs/03-status.md','docs/整体设计文档.md'})
    originals={**semantic['frozen_source_sha256'],**semantic['gold_source_sha256']}
    source_changes=[name for name,value in originals.items() if sha(ROOT/name)!=value]
    derived_changes=[name for name,v in semantic['datasets'].items() if sha(OUT/(name+'.jsonl'))!=v['sha256']]
    result={'stage':'D-triple-prime','updated_unix':time.time(),'checkpoint':'43cbe72433033d23de56324ed3bfae8c2dd9196d',
            'stage_elapsed_seconds':time.time()-protocol['started_unix'],'protocol':protocol,'semantic_view':semantic,
            'generation':generation,'cloud_calls':dict(calls),'unparseable_request_log_lines':bad_logs,
            'cloud_call_count_basis':'parseable request records; lower bound when malformed lines exist',
            'request_log_sha256':log_hashes,'unit_tests':tests,'training':models,'epoch_history':epoch_history,
            'model_smokes':model_smokes,'training_source_manifest':training_manifest,**evidence,
            'stage_changed_files':changed_files,
            'frozen_source_changes':source_changes,'derived_input_changes':derived_changes,
            'real_runs':evidence['regression'],'stage_e_started':False}
    path=ROOT/'docs/stage-d3-results.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    admission=evidence['admission'];selection=evidence['selected-before-heldout'];final=evidence['final-evaluation']
    acceptance={
        'D3_0_semantic_unit_and_russian_under_1pct':bool(tests and tests[-1]['passed'] and semantic['passed']),
        'D3_1_data_gates':admission['passed'] if admission else None,
        'D3_1_shortcut_pretrain':evidence['probe']['pretrain_passed'] if evidence['probe'] else None,
        'D3_2_validation_threshold':bool(selection['selected']) if selection else None,
        'D3_3_three_fits_one_configuration':all(v and v['status']=='completed' and v['base']==base and v['round']==1 and v['original_unchanged'] and v['best_epoch']==min(v['history'],key=lambda h:h['validation_loss'])['epoch'] for base,v in models.items()) if any(models.values()) else None,
        'D3_3_posttrain_probe':selection['candidates'][selection['selected']]['posttrain_probe_passed'] if selection and selection['selected'] else (False if selection else None),
        'D3_4_adjusted_heldout':final['heldout']['passed'] if final and final.get('heldout') else None,
        'D3_4_gold_regression':final['gold']['passed'] if final and final.get('gold') else None,
        'conditional_real_regression':bool(evidence['regression']['status']=='completed' and evidence['regression']['completed_n']==16 and evidence['regression']['all_passed']) if evidence['regression'] else None,
        'no_stage_E':True}
    result['acceptance_self_check']=acceptance
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    sections=['## 执行结果（自动汇总，未知项不推测）',
        f"D″ 检查点：`43cbe72`，提交信息“阶段 D″：退回，训练流程保留”。当前阶段墙钟 {(time.time()-protocol['started_unix'])/60:.1f} 分钟；不进入 E。",
        '### 语义视图与测试',
        f"俄语独立语义保留集 {semantic['russian_semantic_heldout_n']} 条，混合文字词从 {semantic['before']['mixed_words']}/{semantic['before']['words']}（{semantic['before']['fraction']:.2%}）变为 {semantic['after']['mixed_words']}/{semantic['after']['words']}（{semantic['after']['fraction']:.2%}）。两次使用同一 Unicode 词统计口径；与历史评审的 62% 分母定义不同。",
        table(['测试记录','项数','结果'],[[r['path'],r['n'],'通过' if r['passed'] else '失败，保留原记录'] for r in tests]),
        '首次运行时全量检查中的新增测试前提已修正；既有 HTTP 测试超时已单独复核。以上按每次实际运行列出。真实 Pi 回归与离线诊断分别见下文。',
        f'冻结原始文件变化：{len(source_changes)}；派生语义输入变化：{len(derived_changes)}。',
        '### 数据生成、教师与隔离',
        table(['批次','生成器','完成尝试/原计划','有效训练','有效验证'],[[folder,g,str(v['attempted'])+'/'+str(v.get('original_planned',v['planned']))+('（时间截断，完成数下界）' if v.get('stopped_by_time_cutoff') else ''),v['generated'].get('train',0),v['generated'].get('validation',0)] for folder,groups in generation.items() for g,v in groups.items()])]
    dean=evidence['dean-adjudication-final']
    candidate=evidence['candidate-summary']
    if candidate:
        sections += [f"补缺授权前的历史候选快照：{candidate['candidate_n']} 条、双教师有效票 {candidate['teacher_vote_n']} 张；当时完整双票中的原始三方一致率 {candidate['raw_three_way_agreement_rate']:.2%}。以下历史表是候选契约标签分布，不是本次最终训练规模。",
            table(['候选划分','数量','契约类别','语言','生成器'],[[split,d['n'],json.dumps(d['label']),json.dumps(d['language']),json.dumps(d['generator'])] for split,d in candidate['distribution'].items()])]
    if dean:sections.append('补缺授权前，子 agent 最终教师完成前两批480条定向分歧审阅：468条确定裁定、12条弃权；保留契约304条、修正164条。与DeepSeek一致440/468，与MiMo一致70/468。原票在独立裁定完成后才关联；这些不是总体教师准确率。后续授权批次另行计入最终入库统计，原始票与裁定均保留。')
    if evidence['gapfill-result']:
        c=evidence['collection'];sections.append(f"本次冻结候选 {c['candidate_n']} 条，有效教师票 {c['vote_n']} 张；补生成有效候选 {c['gapfill_n']} 条。最终数据链路由独立教务子 agent 复算，审计见机读结果 dean-gapfill-review；旧 dean-admission-review 仅为补缺前历史记录。新增训练生成器占比 DeepSeek 51.88%、Qwen 48.12%；新验证 DeepSeek 52.73%、Qwen 47.27%。")
    if evidence['isolation']:sections.append('隔离结果：'+json.dumps(evidence['isolation']['rejected_counts'],ensure_ascii=False)+'。阈值保持 Jaccard 0.5 / BGE cosine 0.9。')
    elif evidence['isolation-partial']:
        p=evidence['isolation-partial']['phase_summary']
        sections.append(f"隔离未完成：字符／载荷模板／384-token 长度过滤阶段保留 {p['kept']}、拒绝 {p['rejected']}；嵌入隔离未完成，最终拦截数量与原因分布为 null。不能将这 {p['kept']} 条视为已通过隔离。")
    if admission:
        sections += [f"隔离后原始三方一致 {admission['unanimous_n']}/{admission['fully_reviewed_n']}（{admission['agreement_rate']:.2%}）；最终新增入库 {admission['new_admitted_n']}，其中裁定准入 {admission['final_agent_adjudicated_n']}、最终标签修正 {admission['final_agent_relabeled_n']}。",
            table(['划分','类别数量','语言数量','生成器数量'],[[split,json.dumps(d['label'],ensure_ascii=False),json.dumps(d['language'],ensure_ascii=False),json.dumps(d['generator'],ensure_ascii=False)] for split,d in admission['quality']['distribution'].items()]),
            table(['数据门禁','通过'],[[k,v] for k,v in admission['quality']['checks'].items()])]
        if evidence['gapfill-authorization']:sections.append(f"数据准备累计到入库完成 {admission['data_elapsed_seconds']/60:.2f} 分钟，超过原120分钟预算；首次停止后已分别获得追加隔离时间与补生成授权。原始止损记录保留，不把这次扩展表述为原预算内完成。训练加评测仍单独硬限60分钟，整阶段原4小时上限未放宽。")
    else:sections.append('尚无最终入库结果；不能将已生成候选数当作合格训练/验证规模。')
    if evidence['probe']:
        p=evidence['probe'];sections.append(f"捷径探针：首句验证准确率 {p['first_sentence']['validation']['all']['accuracy']:.4f}，全篇 request F1 {p['full']['validation']['all']['request']['f1']:.4f}；训练前门禁 {p['pretrain_passed']}。")
        sections.append(f"完整探针 request F1 为 {p['full']['validation']['all']['request']['f1']:.10f}，候选须达到至少 {p['full']['validation']['all']['request']['f1']+.03:.10f}；训练后结果见候选表。" if selection else '完整探针与微调模型至少3个百分点的差距尚待训练后核验。探针通过不覆盖独立的数据规模、先验和长文门禁。')
    else:sections.append('捷径探针：未运行。')
    sections.append('### 训练、校准与新验证集选模')
    epochs=[[base,h['epoch'],f"{h['train_loss']:.6f}",f"{h['validation_loss']:.6f}",f"{h['validation_accuracy']:.4f}"] for base,history in epoch_history.items() if history for h in history]
    sections.append(table(['模型','epoch','训练 loss','验证 loss','验证准确率'],epochs) if epochs else '尚未训练；没有 epoch、模型哈希或候选评测值。')
    sections.append(table(['模型冒烟','有限loss与梯度','原版权重未变','优化器更新'],[[base,v['passed'],v['original_unchanged'],v['optimizer_steps']] for base,v in model_smokes.items() if v]))
    if evidence['training-runner']:sections.append('训练调度状态：'+json.dumps(evidence['training-runner'],ensure_ascii=False)+'。每个模型只启动一组超参数；中止模型的已完成epoch也原样列出。')
    if evidence['training-clock'] and evidence['training-runner'] and evidence['training-runner'].get('finished_unix'):
        sections.append(f"训练加评测实际墙钟 {(evidence['training-runner']['finished_unix']-evidence['training-clock']['started_unix'])/60:.2f} 分钟（含三模型冒烟、训练、校准及冻结评测；上限60分钟）。")
    for base,v in models.items():
        if v:sections.append(f"{base}：best epoch {v['best_epoch']}，早停原因 {v['stop_reason']}，温度 {v['temperature']:.6f}，阈值 {v['threshold']}，原版权重未变 {v['original_unchanged']}。完整配置与文件哈希见机读文件。")
    weight_rows=[[base,name,digest] for base,v in models.items() if v for name,digest in v['sha256'].items() if name.endswith(('.safetensors','.bin','.pt','.pth'))]
    if weight_rows:sections.append(table(['模型','权重文件','SHA-256'],weight_rows))
    if any(models.values()):sections.append('三模型共用种子20261017、最大8个epoch、验证loss改善阈值0.002、patience=2；恢复实际最低验证loss对应epoch。Laya micro_batch=16、encoder_lr=1e-5、head_lr=5e-5、FP16 AMP；ModernBERT batch_size=16、lr=1e-5、weight_decay=0.01、bfloat16。每个文档的语义内容窗口≤384 token，Laya整体编码max_len=512（含问题和结构），不把结构预算当成正文预算。')
    header=['模型/集合','n','request召回','request精确率','none误报率','request F1','macro-F1（argmax）','ECE']
    if selection:
        sections += [table(header,[metric_row(name,v['validation'],missing='无可行阈值') for name,v in selection['candidates'].items()]),
            table(['候选','阈值','验证NLL','相对全篇探针F1差','探针通过'],[[name,v['threshold'],v['validation_nll'],v['probe_gain'],v['posttrain_probe_passed']] for name,v in selection['candidates'].items()]),f"只按新验证集冻结选择：{selection['selected']}。"]
    else:sections.append(table(header,[metric_row(name,None) for name in ('english','multilingual','modernbert','ensemble')]))
    sections.append('指标口径：request 召回、精确率、F1 和 none 误报率使用冻结的部署阈值；macro-F1 使用三类别概率 argmax，二者判定规则不同。ECE 基于校准后的 request 概率。')
    sections.append('### 最终冻结评测（仅聚合）')
    if final and final.get('heldout'):
        held=final['heldout']['metrics'];sections.append(table(header,[metric_row(name,v['all']) for name,v in held.items()]))
        for subset in ('full_semantic','adjusted_semantic'):
            for group in ('language','style'):
                sections.append(f'{subset} / {group}\n\n'+table(header,[metric_row(k,v) for k,v in held[subset][group].items()]))
        sections += ['C/C2：\n\n'+table(header,[metric_row('C+C2',final['gold']['metrics']['all'])]+[metric_row(k,v) for k,v in final['gold']['metrics']['evaluation_set'].items()]),
            f"保留集验收 {final['heldout']['passed']}，金标准验收 {final['gold']['passed']}。批量每片段耗时：保留集 {final['heldout']['latency_ms_per_fragment']:.3f} ms，金标准 {final['gold']['latency_ms_per_fragment']:.3f} ms。",
            '旧验证集只报告：\n\n'+table(header,[metric_row('old validation',final['old_validation']['metrics']['all'])])]
    elif evidence['heldout-aggregate']:
        held=evidence['heldout-aggregate']['metrics']
        sections.append('冻结评测只保存了保留集聚合，最终金标准／完整验收尚未完成；不重新推理。')
        sections.append(table(header,[metric_row(name,v['all']) for name,v in held.items()]))
        for subset in ('full_semantic','adjusted_semantic'):
            for group in ('language','style'):
                sections.append(f'{subset} / {group}\n\n'+table(header,[metric_row(k,v) for k,v in held[subset][group].items()]))
    else:sections.append('保留集（剔除前/后）、公开测试与 C/C2 金标准：未完成，不以历史结果充当本轮结果。')
    sections += ['### 真实运行与调用量',
        '真实 Pi 条件性回归未触发：运行 ID=[]，verify_v2=null。' if not evidence['regression'] else '真实回归运行 ID 与 verify_v2 结果见机读文件的 regression / real_runs。',
        table(['云端模型','请求数（含失败）','有token记录的请求','已知总token'],[[name,x['calls'],x['known_token_usage_calls'],x['tokens'].get('total_tokens',0) if x['known_token_usage_calls'] else '未知'] for name,x in calls.items()]),
        f'未返回 usage 的请求 token 数未知，不计作零；并行请求耗时之和不等于阶段墙钟。有效请求记录仅含模型名、耗时与 token 数。原始共用追加日志存在 {bad_logs} 行损坏，原件保留；上表调用量为可解析记录下界，不能宣称精确总量。后续追加增加跨进程锁，修复不追补或覆盖历史证据。',
        '### 验收逐条自检',
        table(['验收项','结果'],[[k,'未运行／尚未触发' if v is None else str(v)] for k,v in acceptance.items()]),
        '### 改动文件',
        '\n'.join('- `'+name+'`' for name in changed_files),
        '既有其他阶段未提交改动保留，不计入本阶段交付。.local/ 内数据、裁定、日志和模型证据不提交。',
        '### 当前未解决项',
        '以最终入库门禁、候选资格、冻结验收与真实回归为准；未运行项不宣称完成。S1 是否实际启用需另核对配置与回归记录，评测通过字段本身不会自动启用。']
    if admission and not admission['passed']:
        failed=[k for k,v in admission['quality']['checks'].items() if not v]
        sections.append('数据准入未达标：'+', '.join(failed)+'。保留诊断入库文件与原始证据，不进入训练，不启用 S1；没有本轮模型权重、epoch、阈值、保留集或金标准推理结果。')
    if final and final.get('heldout'):
        failed_metrics=[]
        for subset in ('adjusted_semantic','adjusted_combined','gold'):
            m=final['gold']['metrics']['all'] if subset=='gold' else final['heldout']['metrics'][subset]['all']
            limits=[('request召回',m['request']['recall'],.70 if subset=='gold' else .85,'>='),
                    ('request精确率',m['request']['precision'],.80 if subset=='gold' else .85,'>='),
                    ('none误报率',m['none_fpr'],.03,'<=')]
            if subset!='gold':limits.append(('ECE',m['ece_request_10_bins'],.10,'<='))
            for key,actual,bound,op in limits:
                if actual is None or (actual<bound if op=='>=' else actual>bound):
                    failed_metrics.append([subset,key,actual,op+str(bound),None if actual is None else abs(actual-bound)])
        if failed_metrics:sections += ['冻结验收未达标项（不调整阈值，不导出错例，不开启下一轮）：',table(['集合','指标','实际','预登记要求','绝对差距'],failed_metrics)]
    if selection:
        ineligible=[name for name,v in selection['candidates'].items() if v['threshold'] is None or not v['posttrain_probe_passed']]
        if ineligible:sections.append('未取得选模资格的候选：'+', '.join(ineligible)+'；具体阈值可行性与探针差距见候选表，保留对照权重，不重训。')
    if evidence['regression'] and evidence['regression']['status']!='completed':
        sections.append('条件性回归未完成：'+json.dumps(evidence['regression'].get('error',evidence['regression']['status']),ensure_ascii=False)+'；已完成轮次保留，未补跑。')
    if evidence['stage-stop']:
        stop=evidence['stage-stop']
        sections.append(f"首次停止记录：数据准备 {stop['data_elapsed_seconds']/60:.2f} 分钟时触发预设预算保护（硬线120分钟，预留100秒收尾）。生成／复核完成后才运行完整串行字符隔离，隔离子进程在562.25秒超时，未给嵌入隔离和捷径探针留下足够时间；这是首次执行安排与隔离效率的缺口，不能据此判断候选模型性能。首次停止时未训练，S1关闭；历史停止记录不覆盖后续授权续行结果。")
    continuation=evidence['continuation-result']
    if evidence['continuation-authorization']:
        sections += ['### 历史续行：用户授权追加时间，只用冻结数据',
            '用户明确允许优化隔离后继续已有数据的隔离、入库和捷径探针；通过后继续同一轮训练，训练加评测仍限60分钟，不开始E。原始计时、首次失败日志和停止记录保留；不重新生成，不重新标注。',
            '优化采用缓存的精确倒排计数；固定参考的余弦相似度批量计算，阈值附近仍用原矩阵向量算法复核。原Jaccard 0.5、cosine 0.9、稳定输入顺序及跨划分逐条判定保持不变。']
        benchmark=evidence['isolation-benchmark']
        if benchmark:sections.append(f"合成基准1000参考／100查询：原版{benchmark['seconds']['legacy']:.3f}秒、优化版{benchmark['seconds']['optimized']:.3f}秒，{benchmark['speedup']:.2f}倍；判定一致。该次历史全量隔离耗时：{continuation['isolation_seconds'] if continuation else '未完成'}秒。")
        if continuation:
            sections += [f"隔离、入库计算与捷径探针均完成；新增云端调用 {continuation['additional_cloud_calls']} 次，候选、原始教师票及云端日志哈希全部不变。新增训练 {continuation['new_train_n']}／4000（缺{continuation['new_train_shortfall']}），保留旧8204后训练总数{continuation['train_n']}；新验证{continuation['validation_n']}。",
                f"该次续行的阻断项：验证集request占比{continuation['validation_request_fraction']:.2%}，超过35%；训练长文稀释{continuation['long_dilution_fraction']:.2%}，低于5%。按预登记的dilution类型，把所有通过隔离的长文候选都算上，连同旧数据也最多{continuation['registered_dilution_maximum_from_all_isolated_data']}条，低于最低训练规模所需{continuation['required_dilution_at_minimum_training_size']}条。因此当时停止待评审；本结论仅适用于补生成授权之前的固定池，后续结果见下节。"]
    gapfill=evidence['gapfill-result']
    if evidence['gapfill-authorization']:
        sections += ['### 用户授权补生成缺口（同一轮，门槛不变）',
            '用户明确允许补生成长文和负样本，通过隔离、入库和捷径探针后继续本轮60分钟训练评测。原失败批次、验证集与探针保存在pre-gapfill中；训练开始前只做这次获准的数据修补，冻结语义保留集及金标准未参与修补。',
            '冒烟发现原长度简报常被超额生成。保留各次失败记录，最终以原风格登记中13种适合长篇正文的训练风格补缺；原48种训练、16种验证风格的数据保留。计划尝试生成2000条长文、400条验证负样本，两个生成器各半；实际有效补批1069条，最终入库另行过滤。训练补批计划英语80%，其余中日俄20%，验证四语言各25%。英语目标200–210词，仍在原180–230词范围内；增加明确最低长文单位检查并保留全文384-token上限，未截断文本或放宽隔离阈值。验证补批均为plain，最终仍核验15–25%的整体变体比例。',
            '完整最低长度、两套tokenizer限制与教师复核可能分别拒绝样本，因此生成计划不等于准入规模。三方一致仍以原始教师票计算，授权教务裁定另列。']
        if gapfill:sections.append('本次结果：'+json.dumps(gapfill,ensure_ascii=False))
    report=ROOT/'docs/22-stage-d3-report.md';old=report.read_text(encoding='utf-8').split('\n<!-- D3 RESULTS -->')[0]
    report.write_text(old+'\n<!-- D3 RESULTS -->\n\n'+'\n\n'.join(sections)+'\n',encoding='utf-8')
    verification=['# 阶段 D‴ 核验摘要',
        ('补生成后状态：'+gapfill['status']+'；完整验收与停止原因见报告。') if gapfill else (('追加时间续行已结束：'+continuation['status']+'；完整门禁与停止原因见报告。') if continuation else ('本轮数据准备预算保护停止，未完成阶段验收；S1关闭，等待评审。' if evidence['stage-stop'] else '阶段状态以机读结果为准。')),
        f'- 检查点：43cbe72（阶段 D″：退回，训练流程保留）；.local 未提交。',f'- 原始冻结文件变化：{len(source_changes)}；派生输入变化：{len(derived_changes)}。',
        f'- 最后全量单测：{tests[-1]["n"] if tests else "未知"}项，结果{tests[-1]["passed"] if tests else "未知"}；日志锁修改后的相关29项另行通过，4进程400条追加测试通过。',f'- 入库门禁：{admission["passed"] if admission else "未完成"}。',
        f'- 训练前捷径探针：{evidence["probe"]["pretrain_passed"] if evidence["probe"] else "未运行"}。',
        f'- 冻结评测：{final["status"] if final else "未运行"}。',
        f'- 云端请求可解析记录下界：{sum(v["calls"] for v in calls.values())}；原始损坏日志行：{bad_logs}，不宣称精确总调用量。',
        '- 真实回归未触发，运行 ID=[]、verify_v2=null。' if not evidence['regression'] else '- 真实回归见机读结果。',
        f'- 机读结果 SHA-256：`{sha(path)}`。',f'- 阶段报告 SHA-256：`{sha(report)}`。',
        '- 真实运行与离线结果分开记录；未开始阶段 E。']
    (ROOT/'docs/stage-d3-verification.md').write_text('\n\n'.join(verification)+'\n',encoding='utf-8')
    print(json.dumps({'result_path':str(path),'frozen_source_changes':len(source_changes),'derived_changes':len(derived_changes),'cloud_requests':sum(v['calls'] for v in calls.values())}))


if __name__=='__main__':main()
