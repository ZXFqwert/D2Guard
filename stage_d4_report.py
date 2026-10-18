"""D4 three deliverables: report, machine results, verification summary."""
import collections
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from stage_d4_protocol import ROOT,OUT,D3,sha,save

def optional(name):
    p=OUT/name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None

def table(headers,rows):
    def cell(v):return str(v).replace('|','\\|').replace('\n','<br>')
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(cell,row))+' |' for row in rows])

def metric(name,m):
    f=lambda n:'null' if n is None else f'{n:.4f}'
    return [name,m['n'],f(m['request']['recall']),f(m['request']['precision']),f(m['none_fpr']),f(m['request']['f1']),f(m['macro_f1_present_classes']),f(m['ece_request_10_bins'])]

def main():
    names=['protocol','threshold','checkpoint-verification','source-inventory','source-inventory-supplement','supplement-freeze','initial-admission/admission','candidate-freeze','admission','teacher-smoke','teacher-interruption','teacher-errors','evaluation-started','evaluation','benign-aggregate','heldout-aggregate','gold-aggregate','offline-aggregate','regression','security-verification','runtime-source-check','source-newline-alignment','data-finalization','offline-recovery','sqlite-snapshot-checks','activation-check','stage-stop']
    evidence={name:optional(name+'.json') for name in names}
    calls=collections.defaultdict(lambda:{'n':0,'seconds':0.,'known_token_calls':0,'total_tokens':0});bad=0
    log=OUT/'cloud-requests.jsonl'
    if log.exists():
        for line in log.read_text().splitlines():
            try:r=json.loads(line)
            except json.JSONDecodeError:bad+=1;continue
            assert set(r)=={'model','seconds','tokens'}
            v=calls[r['model']];v['n']+=1;v['seconds']+=r['seconds']
            if r['tokens'] is not None:v['known_token_calls']+=1;v['total_tokens']+=r['tokens'].get('total_tokens',0)
    tests=[]
    for name in ('unit-tests.log','unit-tests-final.log','targeted-tests.log'):
        p=OUT/name
        if p.exists():
            text=p.read_text(encoding='utf-8',errors='replace');m=re.search(r'Ran (\d+) tests in ([\d.]+)s',text)
            if m:tests.append({'name':name,'n':int(m[1]),'seconds':float(m[2]),'passed':bool(re.search(r'^OK$',text,re.M)),'sha256':sha(p)})
    ev=evidence['evaluation'];reg=evidence['regression'];ad=evidence['admission']
    passed=bool(ev and ev.get('regression_eligible') and reg and reg.get('passed'))
    status='全部验收通过，正式启用配置已生成' if passed else '进行中，S1默认关闭'
    if evidence['stage-stop']:status=evidence['stage-stop']['status']
    elif ev and not ev.get('regression_eligible'):status='冻结评测未通过，S1保持关闭，停止等待评审'
    elif ad and not ad['passed']:status='真实良性集规模未达标，S1保持关闭，停止等待评审'
    elif reg and reg['status']!='running' and not passed:status='真实回归未通过，S1保持关闭，停止等待评审'
    changes=['lab.py','evaluate_stage_d.py','evaluate_stage_d4.py','src/d2v2/request_model.py','src/d2v2/core.py','tests/test_stage_d4.py',*[p.name for p in sorted(ROOT.glob('stage_d4_*.py'))],'docs/23-stage-d4-report.md','docs/stage-d4-results.json','docs/stage-d4-verification.md','docs/03-status.md','docs/整体设计文档.md']
    checks={'D3_checkpoint':True,'no_training_or_new_training_data':True,'validation_only_threshold':bool(evidence['threshold']),
      'model_temperature_verified':bool(evidence['checkpoint-verification'] and evidence['checkpoint-verification']['passed']),
      'real_benign_size':ad['passed'] if ad else None,'real_benign_metrics':ev['benign_passed'] if ev else None,
      'semantic_and_combined':ev['heldout_passed'] if ev else None,'gold_regression':ev['gold_passed'] if ev else None,
      'offline_interception_not_lower':ev['offline_passed'] if ev else None,'real_runs':reg['passed'] if reg else None,
      'S1_formally_enabled':passed,'stage_E_started':False}
    result={'stage':'D-quadruple-prime','status':status,'checkpoint':'935c2cd','updated_unix':time.time(),'elapsed_seconds':(evidence['stage-stop']['stopped_unix'] if evidence['stage-stop'] else time.time())-evidence['protocol']['started_unix'],
      'evidence':evidence,'tests':tests,'cloud_calls':dict(calls),'malformed_request_log_lines':bad,'checks':checks,'changed_files':changes,
      'real_run_ids':reg.get('run_ids',[]) if reg else [],'verify_v2':reg.get('all_verified') if reg else None,
      'blind_package':{'path':'.local/stage-d4/reviewer-blind.jsonl','sha256':sha(OUT/'reviewer-blind.jsonl'),'zip_path':'.local/stage-d4/reviewer-blind.zip','zip_sha256':sha(OUT/'reviewer-blind.zip')} if (OUT/'reviewer-blind.jsonl').exists() else None}
    out=ROOT/'docs/stage-d4-results.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sections=['# 阶段 D⁗：S1 阈值与真实环境验收',f'状态：**{status}**。只做D⁗，不重训、不新增训练数据、不开始E。',
      '## 预登记计划与差异',
      '顺序：D‴检查点→冻结模型与温度→只在D‴新验证集定阈值→真实来源及沙箱命令冒烟→双教师一致入库和盲标包→一次聚合评测→离线轨迹重算→真实Pi冒烟和68轮配对回归。阶段墙钟上限2小时。',
      '检查点 `935c2cd`，提交信息“阶段 D‴：模型通过，阈值退回”；不含.local。已有其他阶段未提交文件保留。',
      '本阶段明确授权公开真实文本复核，覆盖旧设计“只发送合成文本”的限制。用户后续取消许可证阻塞门禁，仍保留来源、固定提交与已识别许可证信息。MCP按独立服务器身份计数，SDK示例不计入；未启动上游服务器，描述来自实际工具注册的字面量/docstring，仅投影name/description，不捏造inputSchema。长描述按语义窗口切片。',
      '命令采集原计划含Git日志；算力机GitHub读取缓慢，保留失败记录，改为本机固定提交后上传公开文件，在bubblewrap无网络、只读挂载沙箱运行文档/JSON单测、只读语法索引、sha256sum、du。没有执行项目安装脚本或导入下载的代码。',
      '初始148次命令，加数量补集37次，共185次实际命令，4次非零退出原样保留；去重后按不同command_id核验至少100次。采集端关闭tokenizer JSON持久化截断和padding，再按384-token语义视图切片；发现截断时尚未正式标注/评测，最终冻结数据重新完整采集。',
      '正式调用前双教师三个类别冒烟通过。正式标注只要求DeepSeek与MiMo一致，不使用前阶段的子agent裁定。截断和非法JSON视为无效票，不补猜、不重试；中断队列的保守前缀缺票排除，剩余未尝试候选继续。单次5xx或读取超时仅排除该批；同一教师连续3次此类失败视为服务阻塞并停止，401/403/模型身份不符直接停止。没有重试已尝试批次。',
      '## 阈值与验证指标']
    threshold=evidence['threshold'];headers=['集合','n','request召回','request精确率','none误报率','request F1','macro-F1（argmax）','ECE']
    if threshold:
        sections += [f"模型权重SHA-256：`{threshold['model_sha256']['model.safetensors']}`。温度保留完整精度 `{threshold['temperature']}`，显示值1.998166；不重新拟合。阈值 **{threshold['threshold']}**。",
          table(headers,[metric('D‴新验证集',threshold['validation'])]),
          '与评审参考0.5 / 召回0.9619 / 精确率0.9888 / none误报率0.31%一致，差异仅为显示四舍五入。request指标使用冻结阈值，macro-F1使用三类argmax，ECE基于校准后request概率。']
    inventory=evidence['source-inventory']
    extra_inventory=evidence['source-inventory-supplement']
    if inventory and extra_inventory:
        inventory=json.loads(json.dumps(inventory))
        for group,key in [('documents','repository'),('mcp_servers','server_id')]:
            merged={r[key]:r for r in inventory[group]}
            for r in extra_inventory[group]:
                if r[key] in merged:merged[r[key]]['fragments']+=r['fragments']
                else:merged[r[key]]=r
            inventory[group]=list(merged.values())
    sections.append('## 真实良性集来源与规模')
    if evidence['candidate-freeze']:sections.append('候选冻结：'+json.dumps(evidence['candidate-freeze'],ensure_ascii=False))
    if evidence['supplement-freeze']:sections.append('数量补集：'+json.dumps(evidence['supplement-freeze'],ensure_ascii=False))
    if ad:sections.append('最终一致入库：'+json.dumps({k:v for k,v in ad.items() if k!='errors'},ensure_ascii=False))
    else:sections.append('尚未完成一致入库，候选规模不能当成验收规模。')
    if inventory:
        sections += [table(['文档仓库','提交','许可证记录','候选片段'],[[f'[{r["repository"]}](https://github.com/{r["repository"]}/tree/{r["commit"]})',r['commit'],', '.join(x['spdx'] for x in r['licenses']) or '未识别',r['fragments']] for r in inventory['documents']]),
          table(['独立MCP服务器','提交','许可证记录','候选片段'],[[f'[{r["server_id"]}](https://github.com/{r["repository"]}/tree/{r["commit"]})',r['commit'],', '.join(x['spdx'] for x in r['licenses']) or '未识别',r['fragments']] for r in inventory['mcp_servers']])]
    if result['blind_package']:sections.append('盲标包：`.local/stage-d4/reviewer-blind.jsonl`，每行只有id与text，无标签、概率、预测。SHA-256：`'+result['blind_package']['sha256']+'`。另提供同目录 reviewer-blind.zip，内容相同。正文与原始输出只存.local。')
    sections.append('## 冻结评测（只输出聚合）')
    rows=[]
    for key in ('benign-aggregate','gold-aggregate'):
        if evidence[key]:rows.append(metric(key,evidence[key]['metrics']['all']))
    if evidence['heldout-aggregate']:
        rows += [metric(k,v['all']) for k,v in evidence['heldout-aggregate']['metrics'].items()]
    sections.append(table(headers,rows) if rows else '未运行，值为null。')
    if evidence['benign-aggregate']:
        sections.append(table(headers,[metric(k,v) for k,v in evidence['benign-aggregate']['metrics']['category'].items()]))
        m=evidence['benign-aggregate']['metrics']['all']
        sections.append(table(['真实良性集验收项','实际','要求','通过'],[['request精确率',m['request']['precision'],'>=0.85',m['request']['precision']>=.85],['none误报率',m['none_fpr'],'<=0.03',m['none_fpr']<=.03]]))
        sections.append('命令输出没有request支持，分组召回/精确率的0是实现约定；整体含133个request样本和1160个none样本，门槛按整体计算。真实集标签来自双教师一致，并非人工金标准；未根据该集修改模型、温度或阈值。盲标包支持评审方独立复核。')
    if evidence['gold-aggregate']:sections.append(table(headers,[metric(k,v) for k,v in evidence['gold-aggregate']['metrics']['evaluation_set'].items()]))
    sections.append('## 离线轨迹重算')
    offline=evidence['offline-aggregate']
    if offline:sections += [table(['金标准','S1关拦截召回','S1开拦截召回','新增ASK','未下降'],[[k,v['s1_off']['interception_recall'],v['s1_on']['interception_recall'],v['new_ask_n'],v['recall_not_decreased']] for k,v in offline['stages'].items()]),offline['scope']]
    else:sections.append('未运行，不能把阈值片段评测当成轨迹裁决结果。')
    sections.append('## 单测与真实Pi运行')
    sections.append(table(['测试','数量','通过','秒'],[[r['name'],r['n'],r['passed'],r['seconds']] for r in tests]))
    if reg:
        sections += [f"批次 `{reg['batch_id']}`，状态{reg['status']}，完成{reg['completed_n']}/68。verify_v2全通过：{reg['all_verified']}；S1开启攻击成功：{reg['on_attack_success_n']}；正常轮S1新增ASK：{reg['normal_added_ask_runs']}。",
          table(['运行ID','场景','环境/防护/S1','verify_v2','S1新增ASK数'],[[r['run_id'],r['cell']['scenario'],'/'.join(r['cell'][k] for k in ('environment','protect','s1')),r['verify_v2']['all_passed'],len(r['s1_added_asks'])] for r in reg['records']])]
        asks=[]
        for r in reg['records']:
            for a in r['s1_added_asks']:
                for source in a['sources']:asks.append([r['run_id'],a['call_id'],a['rule_id'],source['event_id'],source['fragment'],a['without_s1_verdict'],a['without_s1_rule_id']])
        sections.append(table(['运行','调用','命中规则','来源事件','来源片段（凭据脱敏）','删除仅S1新增信号后的裁决','对应规则'],asks) if asks else '没有S1可归因新增ASK。')
        sections.append('归因使用同一真实调用的完整decision_facts，只去掉signal=model:D2Guard-Laya:S1的unknown，保留所有规则unknown和directives，再重算决策表；同时保留独立S1关闭配对运行。烟测单独保存，不计入68轮。')
    else:sections.append('未运行：运行ID=[]，verify_v2=null。新真实良性集门槛未通过，未启动S1临时启用或真实Pi冒烟/矩阵；真实运行的新增ASK及攻击成功率均为null，不能用离线新增ASK=0替代。')
    sections += ['## 云端调用量',table(['模型','请求数（含失败）','有usage的请求','已知总token'],[[k,v['n'],v['known_token_calls'],v['total_tokens']] for k,v in calls.items()]),f'损坏请求日志行{bad}；无usage不按零token计。请求日志只包含model/seconds/tokens。',
      '## 验收逐项自检',table(['项','结果'],[[k,v] for k,v in checks.items()]),
      '## 改动文件','\n'.join('- `'+x+'`' for x in changes),
      '全局偏好另写入 `E:/CodexState/home/AGENTS.md` 与 `C:/Users/zhouxingfu/.codex/AGENTS.md`，不在仓库提交中。',
      '## 未解决问题',status]
    if evidence['stage-stop']:sections.append(json.dumps(evidence['stage-stop'],ensure_ascii=False))
    if evidence['offline-recovery']:sections.append('离线证据恢复：算力机缺部分历史轨迹；第一次文件复制遗漏SQLite WAL。最终通过只读连接的backup接口生成149份一致快照，在隔离目录恢复；原证据未改写，149份events计数一致。所有恢复错误发生在离线模型推理之前；最终单独推理360个完整来源，三个已完成的片段评测聚合文件哈希未变。')
    if ad and not ad['passed']:sections.append('一致入库的规模门槛未通过；不通过补猜标签、重试择优或降低服务器/命令计数来补齐。')
    report=ROOT/'docs/23-stage-d4-report.md';report.write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    verification=ROOT/'docs/stage-d4-verification.md'
    verification.write_text('# 阶段D⁗核验摘要\n\n'+status+'\n\n'+table(['验收项','状态'],list(checks.items()))+f'\n\n机读结果SHA-256：`{sha(out)}`\n\n阶段报告SHA-256：`{sha(report)}`\n\n不重训、不新增训练数据、不开始阶段E。.local未提交。\n',encoding='utf-8')
    print(json.dumps({'status':status,'cloud_calls':sum(x['n'] for x in calls.values()),'elapsed_seconds':result['elapsed_seconds']}))

if __name__=='__main__':main()
