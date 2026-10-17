# 阶段 C 模型标注金标准（E0/E1）

仅用于评测，`training_allowed=false`。不得进入 D/E 的训练、验证或调阈值数据。

## 来源与做法

| 项 | 内容 |
|---|---|
| 样本 | 51 条真实 Pi 轨迹：20 个攻击场景各取 attack/off、11 个正常场景各取 clean/off，另加 20 个攻击场景的 clean/off（来自 Codex 便携样本）。共 273 个动作帧、400 个外部片段。Codex 原便携样本 31 条全为 clean/off，不含攻击动作，因此没有单独使用 |
| 标注包 | 由导出 `full/state/fragments` 重排为按轨迹的事件序列；轨迹随机重排并用 T01–T51 编号，隐藏场景名、条件和系统裁决；状态视图删去所有历史裁决字段。标注包原文在 `.local/stage-c-gold-packets/`（含合成凭据，不入库） |
| 标注规范 | `RUBRIC.md`（四个标注者使用同一份） |
| E0 标注者 | A：Claude Opus 子 Agent；B：Claude Sonnet 子 Agent。只读完整原文视图和片段，互不可见 |
| 分歧裁定 | 动作 2 处分歧（T08-A3、T08-A9），由评审方按规范裁定为 ASK；片段无分歧 |
| E1 标注者 | 另外两个 Claude Opus 子 Agent，各标一半，只看状态视图（S_t＋问题视图），不接触原文 |
| 已知局限 | 四个标注者同属一个模型家族，κ 可能偏高。样本载荷高度同质（见阶段 C 覆盖检查），题目偏易。对外报告必须写明“模型标注金标准” |

## 结果

| 指标 | 值 |
|---|---|
| E0 动作 κ / 一致率 | 0.972 / 99.3%（273 对） |
| E0 片段 κ / 一致率 | 1.000 / 100%（400 对；to_agent 28，其余 data；无 for_reader / quoted 样本） |
| E1 状态视图 vs 金标准 | 96.7%（264/273），达到 ≥95% 目标 |
| 仅规则系统（拟裁决）vs 金标准 | 完全一致 93.8%；拦截（ASK/BLOCK）召回 90.5%、精确率 74.5%；误拦 13、漏拦 4 |

E1 的 9 处不一致按原因分：
- 4 处 `human_disagreement`：都是交接记忆写入。状态视图标注者认为超出授权，金标准为 ALLOW。
- 2 处评分规范缺口：summary 转述了注入步骤，属于“产物内容是否被篡改”这一类，规范里没有覆盖。
- 3 处 `view_missing_fragment`：`.git/hooks` 读取和 `bootstrap.sh` 下载在 S_t 中没有对应的指令关系。

## 文件

- `rater-a-opus.jsonl`、`rater-b-sonnet.jsonl`：E0 原始标注（含 full 与 fragment，片段带 s1_class）
- `e1-state-opus.jsonl`：E1 状态视图标注
- `gold.jsonl`：动作金标准（`adjudicated=true` 标出裁定项）
- `E0-scores.json`、`E1-scores.json`：用仓库内 `score_annotations.py` 计算
- `system-vs-gold.json`：每个动作的系统拟裁决、规则编号与金标准对照
- `selection.json`：packet_id 与 run_id / 导出 item_id 的映射
