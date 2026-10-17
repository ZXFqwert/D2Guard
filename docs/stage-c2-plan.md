# 阶段 C2 实施与评测计划

范围仅 C2；检查点 8cf7931 保存阶段 C 与 stage-c-20261017-111815，包括 docs/stage-c-gold/，不含 .local/ 标注包。

| 项目 | 通用实现 | 文件 |
|---|---|---|
| C2-1 | 动作检测键先做 NFKC、同形字、零宽与大小写归一化；原参数仅执行/审计；授权、敏感性、策略和 directive 键共用 canonical | src/d2v2/normalization.py、compression.py、policy.py、core.py |
| C2-2 | 按并列从句划分否定；保留问句、条件与引用的保守边界；12 条正反探针 | compression.py、tests/test_stage_c2.py |
| C2-3 | 委派范围仅显式读写目标且不携带指纹；DT-2b 仍优先；只读保护既有源码与提交/推送，点名产物可写 | compression.py、core.py、task_brief.py |
| C2-4 | 代理请求恰有一个终结记录；预算取消记录实际字节；子会话统一 180 秒；原始子日志随流保存；失败回流与完成回流分开 | src/proxy_stream.py、services.py、extensions/lab.ts、lab.py、verify_v2.py |
| C2-5 | 新增 20 个攻击场景（含追加中继）；隔离 HOME；GET 查询收据；52 次真实 RPC 用户回合；跨会话条件记忆 | build_stage_c2_scenarios.py、scenarios/c2-*.json、src/boundary.mjs、evaluation_scenarios.py、pi_session.py |
| C2-6 | 既有 31 场景使用资源事实判分、真实文本格式、共同任务措辞、期望裁决；8 类载荷句式 | scenarios/c-*.json、docs/stage-c2-scenario-inventory.json |
| C2-7 | 新增 7 个正常场景：安装、部署、注入引用、事故复盘、MCP、记忆、授权发送 | scenarios/c2-normal-*.json |
| C2-8 | 四类 S1＋粗标签兼容，独立状态标注者；固定首重复按条件选样，无结果筛选 | export_stage_c.py、score_annotations.py、select_stage_c2_sample.py |
| C2-9 | 58 场景各两次四格，共 464 评测运行＋16 记忆准备；另跑原 A/B 四格；导出空标签样本 | run_stage_c.py、analyze_stage_c.py、docs/18-stage-c2-report.md、03-status.md、整体设计文档.md |

完整的新增/改造场景、expected_decision、载荷原句、来源与模式见同目录 stage-c2-scenario-inventory.json。这里只描述预期，不作为运行时条件或金标准。

已说明的设计差异：原实现对整句否定、只读写入和子任务授权过于宽泛；目标未统一归一化；超时缺代理终结；片段粗标签不满足 S1。按设计的通用规则修正，无样本编号分支、无阈值调整。

执行边界：HOME 映射到每轮 workspace/.home；GET 查询仅开放本地合成接收器。仍不是 OS 沙盒。exec-b64/git-real 留到 G。凭据每重复配对组随机生成，各条件同输入；不在场景文件预置凭据。

预算：正式矩阵所有主会话统一 1800 秒，所有子会话统一 180 秒。主预算依据真实多轮 RPC 的累计时间留余量，不按样本调节。预检 RPC 仍保留原 600 秒设置及结果，不混入正式矩阵。

评测隔离：现有金标准只做离线验收；新样本 label=null；不生成金标准、训练数据、验证数据或模型阈值。正常 hold 的工程归因与独立金标准标注分开。

追加记录：原 c-abuse-subagent 的攻击条件未产生足够真实委派，保留原矩阵并新增 c2-subagent-relay 的固定两次四格。新增场景明确协调者/专门阅读者的业务分工，载荷仅在 specialist.md，仍由真实模型自行选择调用。开始运行前已说明其计划与期望裁决；不调整防护规则、阈值或预算。

执行中证据修复（保留旧批次）：安全摘要递归掩码，原始参数仍只保存在本地审计；RPC 在真实审批挂起后不再提交后续用户消息；核验逐条比对宿主消息与 Pi 原生用户消息。另发现部分敏感夹具用了提取器不识别的 SYNTHETIC_KEY，改为已有契约的 SYNTHETIC_API_KEY / SYNTHETIC_PRIVATE_KEY（JSON 文件使用 JSON 格式）。增加覆盖全部 58 个场景的夹具契约测试，不修改指纹提取规则、阈值或金标准。

最终验证策略：冻结 v4，在独立运行目录对全部 58 场景重新跑固定两次四格（stage-c2-final-20261017-141627），不复用前几批的单个成功结果。旧批次及失败轨迹全部归档，作为诊断而非最终有效凭据评测。新增/改造场景清单与 expected_decision 仍见清单 JSON。

调度补充：为利用空闲算力，最终 v4 场景按固定 ID 顺序预分为主批 38 个、并行批 20 个（`.local/stage-c2-final-runtime/.local/final-partition.json` 记录分配）。代码、场景、两次四格和统一预算不变。合并只按这份分配选批，不按攻击成败或裁决选结果；主调度器越过分区边界时的额外运行同样保留为诊断。

最终代码复核修正：原 readonly_write_violation 仍对未点名的新普通产物设置 R3 硬阻断，不符合 §3.5“只禁止既有源码修改与 commit/push”。v5 删除该额外条件，普通写入回到常规授权/决策表；增加集成测试（示例 DT-6 ASK）。源码仅 compression.py 改变。全部 v4 的 480 轮、1840 个已裁决动作的新旧只读谓词结果相同；此为离线影响核验，不冒称重跑模型。另对 c-abuse-git 固定重跑完整两次四格，最终整场景替换为 v5，其余 57 场景保留经影响核验的 v4；全部原始 v4 证据保留。最终新标签仍为空。
