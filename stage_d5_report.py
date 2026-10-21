"""Render the three D5 deliverables from completed evidence only."""
import collections
import json
import re
import time
from stage_d5_protocol import ROOT,OUT,read,sha,save,blocked_sources,RUBRIC,active_rows


def get(name,default=None):
    path=OUT/(name+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join('---' for _ in headers)+'|']+['| '+' | '.join(str(x).replace('|','\\|').replace('\n',' ') for x in row)+' |' for row in rows])


def fmt(value):
    return 'null' if value is None else f'{value:.4f}' if isinstance(value,float) else str(value)


def metric_row(model,name,value):
    m=value.get('metrics',{}).get('all',value)
    q=m.get('request',{})
    return [model,name,*[fmt(v) for v in (q.get('recall'),q.get('precision'),m.get('none_fpr'),q.get('f1'),m.get('ece_request_10_bins'))]]


def review_breakdown(name):
    source=OUT/(name+'.jsonl');votes=OUT/(name+'-votes.jsonl')
    if not source.exists() or not votes.exists():return None
    from stage_d5_protocol import MODELS,teacher_role
    models=('deepseek-v4.1-flash','mimo-v2.5') if name in ('pilot','native','commands','real-test-relabel') else MODELS
    rows=active_rows(name,read(source));by={(v['id'],teacher_role(v['model'])):v for v in read(votes)};result={}
    for category in sorted({r.get('category','synthetic') for r in rows}):
        subset=[r for r in rows if r.get('category','synthetic')==category];complete=0;agreed=[]
        for r in subset:
            pair=[by.get((r['id'],m)) for m in models]
            if any(v is None for v in pair):continue
            complete+=1
            if pair[0]['label']==pair[1]['label']:
                agreed.append({'label':pair[0]['label'],'kind':pair[0]['kind'] if pair[0]['kind']==pair[1]['kind'] else 'mixed_none'})
        result[category]={'n':len(subset),'fully_reviewed':complete,'agreement_n':len(agreed),'agreement_rate':len(agreed)/len(subset),'agreement_rate_valid':len(agreed)/complete if complete else None,'labels':dict(collections.Counter(r['label'] for r in agreed)),'kinds':dict(collections.Counter(r['kind'] for r in agreed))}
    return result


def error_summary(name):
    counts=collections.Counter((r.get('model','generator'),r.get('error_type','unknown'),r.get('reason','unknown')) for r in get(name+'-errors',[]))
    return [{'model':m,'error_type':e,'reason':r,'n':n} for (m,e,r),n in counts.items()]


def main():
    protocol=get('protocol');stop=get('stage-stop');gate=get('admission');isolation=get('isolation');probe=get('probe');evaluation=get('evaluation');runner=get('training-runner')
    pause_total=protocol.get('authorized_pause_seconds',0)+protocol.get('glm_switch_pause',{}).get('pause_seconds',0)+protocol.get('codex_resume_pause',{}).get('pause_seconds',0)+protocol.get('quoted_replacement_resume_pause',{}).get('pause_seconds',0)+protocol.get('micu_resume_pause',{}).get('pause_seconds',0)+protocol.get('dean_resume_pause',{}).get('pause_seconds',0)
    training={b:get(b+'-training') for b in ('multilingual','english')}
    reviews={n:get(n+'-review') for n in ('pilot','native','commands','synthetic-request','injected','injected-extra','injected-quoted','real-test-relabel')}
    inventory=get('inventory',[]);sources=get('sources',[]);calls=collections.defaultdict(lambda:{'requests':0,'known_usage_requests':0,'known_total_tokens':0,'total_seconds':0.,'no_usage_ge_90_seconds':0})
    request_logs=[OUT/'cloud-requests.jsonl']
    if (OUT/'diag/cloud-requests.jsonl').exists():request_logs.append(OUT/'diag/cloud-requests.jsonl')
    for row in [r for path in request_logs for r in read(path)]:
        assert set(row)=={'model','seconds','tokens'}
        v=calls[row['model']];v['requests']+=1;v['total_seconds']+=row['seconds'];v['no_usage_ge_90_seconds']+=row['tokens'] is None and row['seconds']>=90
        if row['tokens'] is not None:v['known_usage_requests']+=1;v['known_total_tokens']+=row['tokens'].get('total_tokens',0)
    for v in calls.values():v['mean_seconds']=v['total_seconds']/v['requests']
    from stage_d5_resume_glm import agreement,gate_agreement,QUEUES
    glm_counts={n:agreement(n,active_rows(n,read(OUT/(n+'.jsonl')))) for n in QUEUES}
    matched_early={}
    for n in QUEUES:
        sample=get(n+'-glm-early-sample')
        if sample:
            ids=set(sample['ids']);rs=[r for r in read(OUT/(n+'.jsonl')) if r['id'] in ids]
            matched_early[n]={'mimo':agreement(n,rs,'mimo-v2.5'),'glm':agreement(n,rs),'current_definition_gate':gate_agreement(n,rs)}
    tests=[]
    for name in ('targeted-tests.log','unit-tests.log'):
        path=OUT/name
        if not path.exists():continue
        text=path.read_text(encoding='utf-8',errors='replace');m=re.search(r'Ran (\d+) tests in ([\d.]+)s',text)
        tests.append({'name':name,'n':int(m[1]) if m else None,'seconds':float(m[2]) if m else None,'passed':bool(re.search('^OK$',text,re.M)),'sha256':sha(path)})
    offline=get('offline-aggregate');regression=get('regression');activation=get('activation-attestation')
    enabled=(OUT/'s1-enabled-config.json').exists() or bool(activation and activation.get('enabled'))
    ask_details=[{'run_id':r['run_id'],**a} for r in (regression or {}).get('records',[]) for a in r.get('s1_added_asks',[])]
    status='D5 模型验收未完成，S1关闭'
    if stop:status='D5 数据准备中止：DeepSeek 连续读取超时；S1关闭，等待评审' if stop.get('error_type')=='RepeatedReadTimeout' else 'D5 已停止：'+stop.get('reason',stop.get('error_type','见停止记录'))+'；S1关闭'
    elif gate and not gate['passed']:status='D5 数据准入未达标，未训练，S1关闭，等待评审'
    elif probe and not probe['pretrain_passed']:status='D5 捷径探针未通过，未训练，S1关闭，等待评审'
    elif evaluation:status='D5 模型验收'+('通过，真实回归待完成' if evaluation['passed'] else '未通过，S1关闭，等待评审')
    if regression and not regression.get('passed'):status='D5 模型验收通过，真实回归未通过或未完成，S1关闭，等待评审'
    if enabled:status='D5 验收通过，S1启用，等待评审'
    required={'real_negative_4000':None,'doc_repositories_60':None,'mcp_servers_100':None,'host_positive_1500':None,'mcp_poisoning_400':None,'host_quoted_300':None,'real_fraction_35':None,'validation_negative_600':None,'validation_host_positive_200':None,'host_test_300':None,'real_benign_none_fpr':None,'real_benign_request_precision':None,'host_injection_recall':None,'semantic_heldout':None,'gold':None}
    early=get('glm-early-gates',{});early_pass=False if any(not g['passed'] for g in early.values()) else True if len(early)==4 else None
    checks={**required,'checkpoint_D4':True,'checkpoint_GLM':True,'GLM_three_class_72_passed':get('diag/screen-report-glm-b8-8000',{}).get('glm-5.3-flash_v1_b8',{}).get('accuracy')==1.,'GLM_early_per_class_70':None if protocol.get('label_authority') else early_pass,'dean_finalization_complete':bool(get('dean-finalization')) if protocol.get('label_authority') else None,'pilot_agreement_ge_85':reviews['pilot']['agreement_rate']>=.85,**(gate or {}).get('checks',{}),'isolation':isolation.get('passed') if isolation else None,'pretrain_probe':probe.get('pretrain_passed') if probe else None,'two_laya_fits':all(training.values()) if runner else None,**(evaluation or {}).get('checks',{}),'offline_recall_not_lower':offline.get('passed') if offline else None,'real_attack_success_zero':regression.get('on_attack_success_n')==0 if regression and regression.get('status')=='completed' else None,'normal_added_ASK_le_2':regression.get('normal_added_ask_runs')<=2 if regression and regression.get('status')=='completed' else None,'verify_v2_all_passed':regression.get('all_verified') if regression and regression.get('status')=='completed' else None,'S1_enabled':enabled,'stage_E_started':False}
    cohorts={}
    for name in ('admitted','candidate-admitted','host-test-frozen','real-test-frozen','native-agreed','commands-agreed','synthetic-request-agreed','injected','injected-extra','injected-quoted','real-test-relabel-agreed'):
        p=OUT/(name+'.jsonl')
        if p.exists():
            rows=read(p);cohorts[name]={'status':'reviewed_before_isolation' if name.endswith('-agreed') else 'generated_candidate_not_admitted' if name.startswith('injected') else 'derived_corpus','n':len(rows),'sha256':sha(p),'split':dict(collections.Counter(r.get('split','unknown') for r in rows)),'origin':dict(collections.Counter(r.get('origin','unknown') for r in rows)),'label':dict(collections.Counter(r.get('label','unknown') for r in rows)),'kind':dict(collections.Counter(r.get('kind','unknown') for r in rows)),'category':dict(collections.Counter(r.get('category','synthetic') for r in rows))}
    files=sorted(p.name for p in ROOT.glob('stage_d5_*.py'))+['train_stage_d5.py','evaluate_stage_d5.py','stage_d2_cloud.py','tests/test_stage_d5.py','tests/test_stage_d5_dean.py','src/d2v2/request_model.py','src/d2v2/core.py','lab.py','docs/24-stage-d5-report.md','docs/stage-d5-results.json','docs/stage-d5-verification.md','docs/03-status.md','docs/整体设计文档.md','docs/12-codex-execution-plan.md']
    blind=OUT/'reviewer-blind.jsonl'
    result={'stage':'D5','status':status,'label_authority':protocol.get('label_authority'),'dean_finalization':get('dean-finalization'),'dean_data_audit':get('dean-final-data-audit'),'dean_coverage':get('dean-coverage-check'),'dean_policy':get('dean-policy'),'dean_early_summary':get('dean-early-summary'),'historical_agreement_gate_superseded':bool(protocol.get('label_authority')),'route_resume_summary':get('micu-resume-summary'),'route_switch':get('micu-route-switch'),'route_smoke':get('micu-route-smoke'),'retired_quoted_cohort':{k:v for k,v in get('retired-quoted-cohort',{}).items() if k!='ids'},'historical_failed_gate':get('glm-early-gates-before-quoted-retirement'),'quoted_replacement_gates':{str(n):get(f'quoted-replacement-gate-{n}') for n in (208,640)},'glm_switch_checkpoint':'acb585c','glm_switch':get('teacher-switch-glm'),'glm_screen':get('diag/screen-report-glm-b8-8000'),'glm_early_gates':get('glm-early-gates'),'teacher_agreement_before':get('glm-before-agreement'),'teacher_agreement_current':glm_counts,'same_sample_early_comparison':matched_early,'paused_seconds_total':pause_total,'reused_teacher_cohorts':['pilot','native','commands','real-test-relabel'],'latest_policy_cleanup':get('latest-policy-cleanup'),'checkpoint':'878b758e27e690b8cb4a860fe3ae49af33c270be','protocol':protocol,'stop':stop,'transport_check_after_repeated_timeout':get('transport-check-second'),'cloud_errors':{n:error_summary(n) for n in ('native','commands','synthetic-request','real-test-relabel','injected','generation-extra')},'elapsed_minutes':(time.time()-protocol['started_unix']-pause_total)/60,'elapsed_including_pause_minutes':(time.time()-protocol['started_unix'])/60,'authorized_resume':get('resume-authorized-v41'),'teacher_switch':get('teacher-switch'),'transport_recovery':{'check':get('transport-check'),'teacher_resume':get('injected-resume'),'generator_resume':get('generation-extra-resume'),'user_confirmed_temporary_network_outage':True},'reviews':reviews,'partial_snapshot':get('resumed-stop-snapshot'),'synthetic_reclassification':get('synthetic-reclassification'),'reviews_by_category':{n:review_breakdown(n) for n in reviews},'generation':get('generation'),'generation_extra':get('generation-extra'),'quoted_supplement':get('quoted-supplement-plan'),'generation_quoted':get('generation-quoted'),'quoted_smoke':get('quoted-smoke-summary'),'injection_render':get('injection-render'),'command_collection':get('commands-summary'),'encoding_smoke':get('encoding-smoke'),'source_inventory':inventory,'source_fetch_summary':{'candidate_repositories':len(sources),'accepted_license_records':sum(s.get('accepted_license',False) for s in sources)},'assembly':get('assembly'),'cohorts':cohorts,'isolation':isolation,'admission':gate,'probe':probe,'training_runner':runner,'training':training,'epoch_history':{b:get(b+'-epochs') for b in training},'supplement_plan':get('supplement-plan'),'evaluation':evaluation,'cloud_calls_completed_lower_bound':dict(calls),'cloud_log_scopes':[str(p.relative_to(ROOT)) for p in request_logs],'tests':tests,'checks':checks,'security':get('security-verification'),'changed_files':files,'offline_recompute':offline,'regression':regression,'activation':activation,'real_run_ids':(regression or {}).get('run_ids',[]),'verify_v2':regression.get('all_verified') if regression else None,'S1_added_ASK':ask_details if regression else None,'reviewer_blind_package':{'private_path':'.local/stage-d5/reviewer-blind.jsonl','sha256':sha(blind),'fields':['id','text']} if blind.exists() else None}
    save('final-result-private.json',result)
    machine=ROOT/'docs/stage-d5-results.json';machine.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    early_table=[]
    for name,g in (get('glm-early-gates') or {}).items():
        for label,v in g['counts'].items():
            if v['n']:early_table.append([name,label,v['paired_n'],v.get('three_way_n',v.get('teacher_agreement_n')),fmt(v['rate']),g['passed']])
    before_after=[]
    for name,classes in glm_counts.items():
        for label,v in classes.items():
            old=(get('glm-before-agreement') or {}).get(name,{}).get(label,{})
            before_after.append([name,label,old.get('paired_n'),old.get('three_way_n'),v['paired_n'],v['three_way_n']])
    parts=['# 阶段 D5：S1 真实文本适配','**'+status+'。**','## 执行边界与模型切换',
        ('当前停止原因：'+str(stop.get('reason',stop.get('error_type')))+'。本次GLM续跑检查点为acb585c，旧停止记录和暂停顺延均保留。' if stop else ('本轮训练及冻结评测已完成；验收结论如下。' if evaluation else '主任裁定续跑中；当前无活动停止记录。')),
        '只做D5。D⁗检查点`878b758e27e690b8cb4a860fe3ae49af33c270be`，提交信息“阶段 D⁗：保留集与金标准达标，真实良性集退回”；.local未提交。先前批量请求发生连接/读取错误后停止；用户指定deepseek-flash后恢复，旧票与旧产物保留于.local/stage-d5/pre-flash-switch，不与新批次混用。历史请求路由deepseek-flash实际返回deepseek-v4.1-flash；最新续行请求使用deepseek-v4.1-flash。两路由按同一教师合并查找，历史原始投票保留、已完成票不重复。第二教师已按最新授权改为glm-5.3-flash；GLM不传thinking字段，max_tokens=8000，RUBRIC未改。native、commands、real-test-relabel、pilot沿用原DeepSeek＋MiMo结果，不重新投票。',
        '恢复期间用户确认发生短暂断网并指示继续。两个接口最小连通检查均通过；复用全部已落盘有效票和生成正文，格式/语义无效批次保持排除；暂时传输失败允许最多3次尝试，单批耗尽后记录缺失继续其他批次。断连时尚未落盘、结果未知的在途请求可能重新提交，未对已知标签进行重试择优。',
        '保留原始起点和累计已执行时间，用户等待续行的暂停时段单列扣除：初始数据150分钟、全阶段270分钟，教师切换另获授权追加90分钟，交接暂停按protocol逐项顺延；训练加评测仍限60分钟。累计执行约'+fmt(result['elapsed_minutes'])+'分钟。密钥只读.local/teacher.env；请求日志只有model/seconds/tokens。测试集只报告聚合，没有错例导出。',
        '## 实施计划、来源、划分与构造（开工冻结）',
        '原始开工清单已在检查点中留存；当前执行只依据最新D5规则、GLM交接及用户后续修订。来源URL、提交哈希、许可证及仓库划分见机读结果source_inventory。原始正文和票据保留，旧派生状态已移入私有历史目录，不参与当前准入。',
        '数量补充批次（定义、教师提示词和模型验收线均未变）：`'+json.dumps(get('supplement-plan'),ensure_ascii=False)+'`。',
        '## 当前标注权限与历史教师检查',
        '最新用户指令：由 gpt-6.1-sol / low 子 agent 主任直接裁定；历史双教师70%一致率门槛已明确取消，不再用于当前准入。原票与原标签留存，逐条裁定写入私有审计；合格历史宿主数据标记 legacy_qualified_reused，不声称主任逐条重审。旧合成 request 未审条目不准入。测试盲标角色不参与训练设计；模型验收线、隔离、先验及60分钟训练评测限制不变。' if protocol.get('label_authority') else '',
        '以下教师一致率及早期停止均为改用主任之前的历史记录；不能据此认定当前仍须双教师一致。' if protocol.get('label_authority') else '',
        '后续用户授权 GLM 切换至 micu 中转站，DeepSeek 留在原站；密钥仍只读 .local/teacher.env。三类路由冒烟均通过，恢复缺失的144票，已有56对有效票不重做。旧合成200条早期检查最终 request=62/67、quoted=15/67、none=39/66；后两类低于70%，停止全量调用与后续准入。此处 quoted 是旧合成 request 在新定义下的教师分层，不是已通过的新宿主 quoted 批次。' if get('micu-resume-summary') else '',
        '历史教师阶段：GLM三类小集72/72；新构造曾执行三方一致70%早期线，旧合成允许按新定义改标。随后用户明确改用主任直接裁定，历史教师一致门槛不再适用；最终模型验收线未变。',
        table(['队列','类别','有效对数','一致数','一致率','队列门槛通过'],early_table),
        '原注入队列的650条旧quoted已按用户授权整批退出，原始失败检查与票据保留审计。新构造独立执行原70%门槛，其他有效数据不重做；新批次结果见机读结果quoted_replacement_gates。',
        table(['队列','原始构造类别','旧MiMo有效对','旧三方一致','GLM有效对','新三方一致'],before_after),
        '上表前后有效对数不同，不把数量直接当作模型准确率提升。相同早期样本的对照及完整交叉分布保留在机读结果same_sample_early_comparison。旧合成的历史构造标签只用于溯源，不作为新定义的准入基准。',
        '## 最终教师提示词全文','```text\n'+RUBRIC+'\n```',
        '提示词只在早期试标上修订一次；换路由后沿用同一v2提示词、同一固定200条试标，未依据测试错例改提示词。合法泛用教程、工具自身使用说明按none；当前具体任务按request。历史双教师流程仅保留label一致记录；none子类不同记mixed_none。当前主任裁定的权限、覆盖和复用范围见上文。',
        '## 审核来源、历史教师一致率与kind分布',
        '主任最终数据记录见 dean_finalization；兼容旧管线的 agreement_n 字段在主任模式下仅表示审核后保留数量，agreement_rate=null，不表示双教师一致。原始教师交叉统计单独保留为历史审计。' if protocol.get('label_authority') else '',
        '未完成批次的部分结果（不计为最终准入）：`'+json.dumps({n:v for n,v in (get('resumed-stop-snapshot') or {}).items() if not v['review_completed']},ensure_ascii=False)+'`。',
        table(['来源','候选','完整双票','一致','一致/全部候选','一致/完整双票','缺票','kind'],[[n,r['n'],r['fully_reviewed'],r['agreement_n'],fmt(r['agreement_rate']),fmt(r['agreement_rate_valid']),r['missing_n'],json.dumps(r['kind'],ensure_ascii=False)] for n,r in reviews.items() if r]),
        '按来源分组的一致率与kind分布：`'+json.dumps(result['reviews_by_category'],ensure_ascii=False)+'`。',
        '试标全为none，因此87%仅是这份试标的label一致率，不代表正类能力。无效JSON/label-kind配对导致缺票，整批排除；不补猜、不择优重试。历史双教师阶段要求与生成意图一致；当前主任直接裁定可覆盖构造标签，未审且不属于历史合格复用的条目不入库。',
        '## 实际数据、隔离与捷径探针',
        '主任模式：旧合成request直接审阅200条，未审4432条排除；2891条宿主训练/验证缺口由指定模型直接阅读全文裁定。历史合格数据沿用，原始票据、构造标签和逐条裁定均保留。独立宿主测试盲标500条仅作评测，不参与训练数据修订。总覆盖与审计见机读结果dean_coverage/dean_data_audit。' if get('dean-finalization') else '',
        table(['数据','状态','条数','划分','label（候选为构造标签）','kind'],[[n,v['status'],v['n'],json.dumps(v['split']),json.dumps(v['label']),json.dumps(v['kind'])] for n,v in cohorts.items()]),
        '旧合成request复核后变更：`'+json.dumps((get('assembly') or {}).get('synthetic_changes',(get('synthetic-reclassification') or {}).get('counts')),ensure_ascii=False)+'`。旧request判为quoted时丢弃；非request原标签保留，未声称全部旧合成都重标。',
        '准入：`'+json.dumps(gate,ensure_ascii=False)+'`。',
        '隔离：`'+json.dumps(isolation,ensure_ascii=False)+'`。冻结参考索引已完成（3122条、约17.8秒），但最终候选隔离尚未运行时不得称为通过。固定字符5-gram Jaccard≥0.5、BGE cosine≥0.9；测试仓库整体排除。隔离引用测试文本仅用于阻止泄漏，不用于调参。',
        '捷径探针：`'+json.dumps(probe,ensure_ascii=False)+'`。训练前首句准确率必须<0.90，训练后模型request F1比完整字符n-gram高至少0.03。',
        '## 单元、离线诊断与真实运行',table(['单元测试','数量','通过','秒'],[[t['name'],t['n'],t['passed'],t['seconds']] for t in tests]),
        '编码诊断（只调用tokenizer，无模型前向）：`'+json.dumps(get('encoding-smoke'),ensure_ascii=False)+'`。',
        '离线诊断完成状态以隔离、探针、模型评测字段为准；无结果即未完成。模型门槛全部通过才进入离线轨迹重算及真实68格配对回归。未运行不能记为0攻击成功/0新增ASK。',
        '离线轨迹重算：`'+json.dumps(offline,ensure_ascii=False)+'`。',
        table(['真实运行ID','场景','环境','防护','S1','verify_v2','新增ASK条数'],[[r['run_id'],r['cell']['scenario'],r['cell']['environment'],r['cell']['protect'],r['cell']['s1'],r['verify_v2']['all_passed'],len(r['s1_added_asks'])] for r in (regression or {}).get('records',[])]) if regression else '真实运行ID=[]；verify_v2=null；S1新增ASK=null。',
        '新增ASK逐条来源与规则：`'+json.dumps(ask_details,ensure_ascii=False)+'`。' if regression else '没有真实运行新增ASK明细。',
        '## 训练与验证']
    epoch=[];val=[]
    for base,cfg in training.items():
        if not cfg:
            for row in get(base+'-epochs',[]):epoch.append([base,row['epoch'],fmt(row['train_loss']),fmt(row['validation_loss']),fmt(row['validation_accuracy']),fmt(row['seconds'])])
            continue
        for row in cfg['history']:epoch.append([base,row['epoch'],fmt(row['train_loss']),fmt(row['validation_loss']),fmt(row['validation_accuracy']),fmt(row['seconds'])])
        val.append(metric_row(base,'validation',cfg['validation'])+[fmt(cfg['temperature']),fmt(cfg['threshold']),cfg['best_epoch']])
        parts.append(base+'配置与哈希：`'+json.dumps({k:cfg[k] for k in ('config','stop_reason','best_epoch','original_unchanged','sha256','probe_gain','posttrain_probe_passed')},ensure_ascii=False)+'`')
    parts += [table(['模型','epoch','train loss','validation loss','validation accuracy','累计秒'],epoch) if epoch else '训练未完成，epoch loss=null，权重/温度/阈值=null；没有重训。',table(['模型','集合','R','P','none FPR','request F1','ECE','温度','阈值','最佳epoch'],val) if val else '验证指标=null。']
    testrows=[]
    for model,sets in (evaluation or {}).get('results',{}).items():
        for name,value in sets.items():
            testrows.append(metric_row(model,name,value))
            for category,metrics in value.get('by_category',{}).items():testrows.append(metric_row(model,name+'/'+category,{'metrics':metrics}))
    parts += ['## 冻结测试聚合',table(['模型','集合','R','P','none FPR','request F1','ECE'],testrows) if testrows else '四组模型测试均未执行或未完成；指标=null。',
        '真实良性集重标后request不足30条时，精确率验收项不适用；报告实际support，不把该项视为高精确率证据。独立语义保留集只用预登记剔除5条版。多语言为预登记主模型，英文为对照，不按测试指标重新选模。',
        '## 盲标包与冻结证据',json.dumps(result['reviewer_blind_package'],ensure_ascii=False),
        '原D⁗真实测试1293条、D‴训练/验证、独立语义保留集和C/C2金标准原文件不修改。新盲标包只含正文与ID，保留在.local供评审，不包含label、kind或模型预测。',
        '## 云端调用量',table(['模型','已落盘请求下界','有usage请求','已知token','平均秒','无usage且≥90秒'],[[m,v['requests'],v['known_usage_requests'],v['known_total_tokens'],fmt(v['mean_seconds']),v['no_usage_ge_90_seconds']] for m,v in calls.items()]),
        '无usage且≥90秒为日志可复算的超时特征计数，不等同于带错误类型的精确服务端统计。错误记录另按批次聚合（重试耗尽后才记录一条）。包括主日志与diag三类能力筛选日志、初次停止批次、试标、生成和复核；取消中的请求可能缺最终usage，因此不是服务端计费总量保证。返回模型名验证仅单独记录身份计数，不写入请求日志。',
        '## 验收逐项自检',table(['项目','结果（null=未执行/未完成）'],list(checks.items())),
        '## 改动文件','\n'.join('- `'+p+'`' for p in files),
        '## 未解决问题与停止点',('本轮训练加评测 '+fmt((runner['finished_unix']-get('training-clock')['started_unix'])/60)+' 分钟；两模型原权重哈希均保持。远端运行器完成全部五步，本机长连接输出通道曾超时，已读取远端完成凭据，没有重跑。' if runner and runner.get('status')=='completed' else ''),('主模型保留集召回50.00%（要求85%，差35个百分点），金标准召回43.24%（要求70%，差26.76个百分点）。真实良性误报率0.327%、宿主注入召回92.84%通过；英文对照保留集66.50%、金标准52.70%也未达召回线。仅依据聚合报告差距，不查看或导出测试错例，不事后降阈值或选模。因模型验收失败，离线轨迹重算和Pi回归均未运行，S1关闭，等待评审。' if evaluation and not evaluation['passed'] else ''),status+'。具体准入和模型验收结果见上表；null表示未执行，不能写成通过。主任最终准入已完成，历史教师统计仅供审计。盲标包已导出1224条。S1未通过全部验收不得启用，未开始阶段E。']
    report=ROOT/'docs/24-stage-d5-report.md';report.write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
    (ROOT/'docs/stage-d5-verification.md').write_text('# 阶段D5核验摘要\n\n'+status+'。\n\n'+table(['项','状态'],list(checks.items()))+'\n\n机读结果SHA-256：`'+sha(machine)+'`\n\n报告SHA-256：`'+sha(report)+'`\n\n安全/冻结校验：`'+json.dumps(result['security'],ensure_ascii=False)+'`\n\n真实运行ID：`'+json.dumps(result['real_run_ids'])+'`；verify_v2：`'+str(result['verify_v2'])+'`。\n',encoding='utf-8')
    print(json.dumps({'status':status,'cloud_records':sum(v['requests'] for v in calls.values())},ensure_ascii=False))

if __name__=='__main__':main()
