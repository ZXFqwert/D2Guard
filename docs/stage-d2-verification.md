# 阶段 D″ 核验摘要

状态：**三轮未达独立语义验收线，S1 关闭，停止待评审**。第二轮英文 Laya 通过 C/C2 冻结线，独立语义召回 80.95% 低于 85%；追加 v2.5 对照有效覆盖 1012/1014，另 2 条无有效结果，完整指标不可得。

- 已验收检查点：`a8bca80ab661657646e6479fd931679b5dd7500a`；D′0 独立提交，D″ 改动未混入。
- Python：169 项，日志确认通过：True；Node：3 项，通过：True。
- C/C2 金标准、片段导出和场景来源哈希：229 个文件，全部保持冻结时内容：True。
- 隔离阈值：字符 5-gram Jaccard ≥0.5、BGE-M3 cosine ≥0.9；原文与载荷句式排除，软件任务领域保留。
- 请求日志字段仅为模型名、耗时、token 数；不包含正文、认证头或密钥。
- 云端模型调用总数：19122；缺失 usage 单独计数，不视为零 token。

## round-1

- 隔离：{'semantic_heldout': 935, 'public_heldout': 242, 'validation': 965, 'train': 4340}。
- 准入：True；本轮新候选三方一致 5726 条。
- 原样复用训练：0 条；验证：0 条；保留：0 条。
- 训练前捷径门槛：True。
- english：恢复 epoch 1，是否为验证 loss 最低 epoch：True；原版权重未改动：True。
- multilingual：恢复 epoch 2，是否为验证 loss 最低 epoch：True；原版权重未改动：True。
- modernbert：恢复 epoch 2，是否为验证 loss 最低 epoch：True；原版权重未改动：True。

## round-2

- 隔离：{'train': 2126}。
- 准入：True；本轮新候选三方一致 1944 条。
- 原样复用训练：3854 条；验证：872 条；保留：1000 条。
- 训练前捷径门槛：True。
- english：恢复 epoch 2，是否为验证 loss 最低 epoch：True；原版权重未改动：True。
- multilingual：恢复 epoch 1，是否为验证 loss 最低 epoch：True；原版权重未改动：True。
- modernbert：恢复 epoch 2，是否为验证 loss 最低 epoch：True；原版权重未改动：True。

## round-3

- 隔离：{'train': 2624}。
- 准入：True；本轮新候选三方一致 2406 条。
- 原样复用训练：5798 条；验证：872 条；保留：1000 条。
- 训练前捷径门槛：True。
- english：恢复 epoch 2，是否为验证 loss 最低 epoch：True；原版权重未改动：True。
- multilingual：恢复 epoch 3，是否为验证 loss 最低 epoch：True；原版权重未改动：True。
- modernbert：恢复 epoch 3，是否为验证 loss 最低 epoch：True；原版权重未改动：True。

## 冻结评测与真实回归

- 最终金标准评测：通过。
- S1 验收启用资格：False。
- 独立语义召回：所选第二轮英文 Laya 为 170/210（80.95%），低于 85%；金标准通过不能抵消该缺口。
- 真实回归：未执行；没有本阶段运行 ID 或 verify_v2 结果，不引用旧阶段批次替代。
- 最终七对照覆盖完整：False；替换教师仅用于最终参照，训练三方标注不改写。
- 已知教师密钥扫描通过：True。
- MiMo v2.5：362/364 唯一输入、1012/1014 加权片段有效；缺 request 与 none 各 1，完整指标不可得，子集指标单列。
- 未开始阶段 E。

完整分布、每 epoch loss、模型与源码哈希、模型指标和调用量见 `stage-d2-results.json`；解释与验收逐条自检见 `21-stage-d2-report.md`。
