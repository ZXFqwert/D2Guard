# 阶段 H 核验摘要

检查点：`3dea9ae`；批次：`stage-h-20261019-161046`。

执行率：996/996 (100.00%)；保留尝试 1004。来源：机读结果 execution/records。
证据核验失败轮：0；全部 verify_v2 通过轮：993。模型失败不自动等于证据失败。
冻结文件：132；当前不一致：[]；本机/算力机规范化源码核对：{'files': 132, 'mismatches': []}。
初始132文件清单漏列两份旧d2core JSON：D2guard_contract.json与weights/laya_d2_distilled.json。另用Git检查点3dea9ae补做追溯核对，不改原清单；全部运行manifest与检查点、当前算力机文件一致。来源：source_check/additional_manifest_files及records/*/manifest/source_mismatches。
本机抽样：全部失败加固定种子 10% 随机轮；详见机读结果 local_verification。
本机复核：111/111结论一致；全部失败轮加10%随机抽样，详见机读结果local_verification/runs与selection。

本批运行的场景、内核、扩展、S1参数未修改；交付件未动，未全量重跑。本机只读trace展示修复未部署到本批，另报离线核对。原始证据仍在 runs，私有协议与中间结果在 .local/stage-h。
