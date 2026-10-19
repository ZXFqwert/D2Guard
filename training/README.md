# D5 训练复现入口

本目录从最终 D5 补训程序提取训练循环、输入构造、指标与校准逻辑，不含教师输出或原训练语料；小样例仅解释 schema，不能复现论文数字。

数据来源：真实开源文档、MCP 工具描述、沙箱输出、真实宿主插入具体任务，以及经裁定恢复的历史合成 request。每行需有 id、raw_text、source_type、label（request/quoted/none）、split、family、origin、language、reviewed。测试仓库整体排除，训练/验证按来源家族隔离；还须准备测试文本排除清单。嵌入余弦隔离及逐样本语义裁定需使用原研究审计流程，不能以本目录字符检查替代；新语料不得声称已复现原准入。

从源码根目录运行（PYTHONPATH=src:training）：

```sh
python training/build_data.py --input reviewed.jsonl --excluded frozen-test.jsonl --output training/work
# 准备 training/work/protocol.json，bases 指向原版英文/多语言 Laya 的本地路径。
python training/train.py multilingual --smoke
python training/train.py multilingual
python training/evaluate.py --checkpoint training/work/D2Guard-multilingual --data frozen-test.jsonl --temperature <验证集温度> --output aggregate.json
```

超参数沿用 D5：8 epoch 上限、micro-batch 16、encoder LR 1e-5、head LR 5e-5、soft-CE、option shuffle、seed 20261017、AMP、gradient checkpointing；patience 2、min_delta .002，恢复最低验证 NLL 的 epoch；仅验证集拟合温度，阈值固定 .5。保留训练/验证 loss、模型哈希与原版不变检查；训练墙钟 60 分钟。训练后的模型不能自动替换交付权重，需单独完成验收。
