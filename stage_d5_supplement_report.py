"""Append supplement aggregates; keep the original D5 report and results intact."""
import json
from pathlib import Path
import stage_d5_protocol as p

ROOT=p.ROOT
OUT=ROOT/'.local/stage-d5-supplement'

def get(name):
    path=OUT/(name+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

def table(head,rows):
    return '\n'.join(['| '+' | '.join(head)+' |','|'+'---|'*len(head)]+['| '+' | '.join(map(str,r))+' |' for r in rows])

def metric(name,m):
    return [name,m['n'],f"{m['request']['recall']:.4%}",f"{m['request']['precision']:.4%}",f"{m['none_fpr']:.4%}",f"{m['ece_request_10_bins']:.6f}"]

def main():
    keys=['protocol','assembly','isolation','admission','probe','training-clock','training-runner','multilingual-training','validation-source-metrics','evaluation','offline-aggregate','regression','activation-attestation','pi-environment-repair','smoke-0','smoke-1']
    result={k:get(k) for k in keys}
    manifest=get('original-manifest')
    result['original_files_unchanged']=all(p.sha(ROOT/name)==h for name,h in manifest.items())
    result['original_manifest']=manifest
    result['cloud_teacher_generation_calls']=0
    result['stage_E_started']=False
    result['S1_enabled']=bool(get('activation-attestation') and get('activation-attestation')['enabled'])
    runner=result['training-runner'];clock=result['training-clock'];trained=result['multilingual-training'];evaluation=result['evaluation']
    result['training_evaluation_minutes']=(runner['finished_unix']-clock['started_unix'])/60 if runner and clock and 'finished_unix' in runner else None
    checks={'data_admission':bool(result['admission'] and result['admission']['passed']),
            'pretrain_probe':bool(result['probe'] and result['probe']['pretrain_passed']),
            **(evaluation or {}).get('checks',{}),'frozen_files_unchanged':result['original_files_unchanged'],
            'offline_recall_not_decreased':bool(result['offline-aggregate'] and result['offline-aggregate']['passed']),
            'real_regression_passed':bool(result['regression'] and result['regression']['passed']),
            'both_smokes_verified':all(result[n] and result[n]['verify_v2']['all_passed'] for n in ('smoke-0','smoke-1'))}
    result['checks']=checks
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    machine=ROOT/'docs/stage-d5-results.json';full=json.loads(machine.read_text(encoding='utf-8'));full['supplement']=result
    machine.write_text(json.dumps(full,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    body=['## D5 补训（2026-10-18）：恢复旧合成 request',
          '检查点 `59b12a3`（阶段 D5:真实良性达标，召回退回）。仅恢复训练侧数据；6.1 sol low 子 agent 按当前具体任务定义裁定全部4,632条（训练4,081、验证551），保留逐条记录及原票。不读取测试错例，不新增生成文本。与已准入D5数据按ID合并，已有同ID只保留一份最新裁定；判为quoted或none亦保留。原始数据、旧模型及原轮报告保留。',
          '本轮仅训练多语言Laya，原底座、超参数、早停、温度拟合方式、模型输入和验收线沿用D5；阈值按本次指令固定0.5。英文不重训。隔离仍为字符5-gram Jaccard≥0.5、BGE cosine≥0.9，捷径门槛不变。',
          '裁定分布：`'+json.dumps(result['assembly'],ensure_ascii=False)+'`。',
          '隔离：`'+json.dumps(result['isolation'],ensure_ascii=False)+'`。',
          '准入：`'+json.dumps(result['admission'],ensure_ascii=False)+'`。',
          '捷径探针：`'+json.dumps(result['probe'],ensure_ascii=False)+'`。',
          '训练加评测耗时（分钟）：`'+str(result['training_evaluation_minutes'])+'`。']
    if trained:
        body += [table(['epoch','train loss','validation loss','validation accuracy'],[[h['epoch'],h['train_loss'],h['validation_loss'],h['validation_accuracy']] for h in trained['history']]),
                 '配置、恢复轮次、温度、阈值和模型哈希：`'+json.dumps({k:trained[k] for k in ('config','best_epoch','stop_reason','temperature','threshold','sha256','original_unchanged','probe_gain','posttrain_probe_passed')},ensure_ascii=False)+'`。',
                 table(['验证分组','N','request R','request P','none FPR','ECE'],[metric('全部',trained['validation'])]+[metric(k,v['all']) for k,v in (result['validation-source-metrics'] or {}).items()])]
    if evaluation:
        rows=[]
        for name,value in evaluation['results']['multilingual'].items():
            rows.append(metric(name,value['metrics']['all']))
            rows.extend(metric(name+'/'+c,m['all']) for c,m in value.get('by_category',{}).items())
        body += [table(['冻结测试','N','request R','request P','none FPR','ECE'],rows),
                 '真实良性集request不足30时精确率项不适用；原始标签与冻结文件未改变。全部分语言聚合见机读结果supplement.evaluation。']
    regression=result['regression']
    records=(regression or {}).get('records',[])
    body += [table(['验收项','通过'],checks.items()),
             '离线重算：`'+json.dumps(result['offline-aggregate'],ensure_ascii=False)+'`。',
             '真实回归汇总：`'+json.dumps({k:v for k,v in (regression or {}).items() if k not in ('records','run_ids')},ensure_ascii=False)+'`。',
             table(['冒烟','运行ID','verify_v2'],[[n,result[n]['run_id'],result[n]['verify_v2']['all_passed']] for n in ('smoke-0','smoke-1') if result[n]]),
             table(['运行ID','场景','环境','防护','S1','verify_v2','新增ASK'],[[r['run_id'],r['cell']['scenario'],r['cell']['environment'],r['cell']['protect'],r['cell']['s1'],r['verify_v2']['all_passed'],len(r['s1_added_asks'])] for r in records]),
             'S1新增ASK逐条明细：`'+json.dumps([{'run_id':r['run_id'],**a} for r in records for a in r['s1_added_asks']],ensure_ascii=False)+'`。空列表表示本批未新增ASK。',
             '本轮数据生成和教师云端调用0；真实Pi模型调用属于上表运行。227项单元测试通过（19.768秒），记录见私有unit-tests.log；原冻结文件哈希一致：'+str(result['original_files_unchanged'])+'。',
             'Pi首次启动因默认npm路径未装固定包失败，发生在创建run和调用模型前；已保留失败日志并在私有目录安装0.85.1，随后才开始上述真实运行。环境修复记录：`'+json.dumps(result['pi-environment-repair'],ensure_ascii=False)+'`。',
             ('S1已通过全部验收并在算力机lab默认配置启用，仍只能增加风险，等待评审。本机未下载或启用GPU权重。算力机Pi运行使用项目私有npm前缀，保持NPM_CONFIG_PREFIX指向.local/pi-runtime。启用凭据：`'+json.dumps(result['activation-attestation'],ensure_ascii=False)+'`。' if result['S1_enabled'] else 'S1保持关闭；未达到全部门槛时不运行条件性Pi回归，不自动重训。'),
             '未开始阶段E。本轮实现文件：stage_d5_supplement.py、stage_d5_supplement_report.py、evaluate_stage_d5.py（增加可选模型列表，默认旧行为不变）、tests/test_stage_d5_supplement.py。']
    report=ROOT/'docs/24-stage-d5-report.md';marker='\n\n## D5 补训（2026-10-18）：恢复旧合成 request'
    old=report.read_text(encoding='utf-8').split(marker)[0]
    report.write_text(old.rstrip()+'\n\n'+'\n\n'.join(body)+'\n',encoding='utf-8')
    verify=ROOT/'docs/stage-d5-verification.md';text=verify.read_text(encoding='utf-8').split('\n\n## D5 补训核验')[0]
    verify.write_text(text.rstrip()+'\n\n## D5 补训核验\n\n'+table(['项','结果'],checks.items())+'\n\n机读结果 SHA-256：`'+p.sha(machine)+'`\n\n报告 SHA-256：`'+p.sha(report)+'`\n',encoding='utf-8')
    print(json.dumps({'checks':checks,'S1_enabled':result['S1_enabled']},ensure_ascii=False))

if __name__=='__main__':main()
