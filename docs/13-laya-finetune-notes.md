# 13 · Laya 微调接口核验（阶段 D）

2026-10-17。先读源码，再实现；以下针对本机与算力机均已安装的 `laya==0.4.6`，不依赖最新网页推测接口。

## 已阅读的官方材料

- [官方模型卡](https://huggingface.co/convaiinnovations/laya/blob/main/README.md) 链接的 [微调 notebook](https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb)。下载字节 SHA256：`033b3f2bd511eab8ecf90d91cb893df581a4152fa1dc949ecae0ba20ee6bb89a`。
- 安装包 `laya/train.py`：SHA256 `c325941f275a90b486d00c3ca28dc4ee1ece795218fdaa7c67818d711ee79645`。
- 安装包 `laya/calibrate.py`：SHA256 `8db2bcbe8566c46740f27039e5838c4e0f3380600120e267ee658bf252cfd48f`。
- 同时检查 `train_cli.py`、`common.py` 的序列构建与选项呈现，以及 `agent.py` 的问题校验/运行接口。来源快照保存在忽略目录 `.local/stage-d-sources/`。

## 已确认的调用契约

`load_checkpoint(model_dir)` 返回 `(model, tokenizer, cfg)`，模型初始为 CPU fp32。目录包含 `model.safetensors`、`rl_agent_config.json`、`encoder/` 和 `tokenizer/`。此函数会调用 `_fix_tokenizer_config`，故输入必须使用私有工作副本，不能直接指向需要保持不变的原版目录。

训练行格式是 `{state, questions, gold}` 或 `{state, questions, expected}`。`gold[qid].probabilities` 是按选项键索引的分布；`expected[qid]` 是选项键。训练元数据不放入 `state`。S1 使用中立选项 A/B/C/D，S2 每项使用 A/B 二选一，避免 NOUL 偏置。S1 的来源类型可以进入视图，但标签、split、模板家族、来源数据集和策略判断不能进入。

`items_from_rows(tok, rows, max_len, head_max_len)` 返回 `(items, skipped)`。内部会截断 state，且序列构建还会扣除题头占用；因此调用前必须用实际 tokenizer 检查片段 ≤256 token、完整序列能容纳，不把自动截断当作预算验证。任何 skipped 都应阻止正式训练。

`train_model(model, tok, items, config, device, max_len, head_max_len, on_epoch_end=None, parallel=False)` 原位更新模型并返回逐 epoch 平均 loss。`TrainConfig` 支持 `loss='soft-ce'|'rlcd'`、分开的 encoder/head 学习率、micro batch、梯度累积、AMP、梯度检查点、随机种子及 `shuffle_options=('choice',)`。

官方 notebook 是双 T4、4 epoch、micro batch 8、每卡累积 4、encoder/head LR 2.5e-5/1e-4、RLCD。此项目可用单 A100，但不能占用另一张已有任务的 GPU。英文完整序列上限仍为 512，多语言上限 1024；不会照抄 notebook 的英文 1024。

`calibration_records(model, tok, items, device, max_len, head_max_len, batch_size=16)` 返回 `(qtype, logits, target, k)`。温度与阈值拟合必须只输入验证集；此函数也可只抽取评测 logits，不作拟合。`fit_temperature_map(records)` 返回 `temperature`、`temperature_by_options`、`n_by_bucket`。内置桶是如 `choice:3-5` 的范围，并非精确选项数；本项目按语义问题（S1 或各 S2）与精确 K 单独调用 `fit_one_temperature` 并保存独立映射，避免混合不同头。

`fit_abstention_thresholds` 可对校准后的最大概率拟合拒答阈值；是验证集经验错误率约束，不是统计保证。本项目预先固定目标误差，再拟合阈值，保留集和 C/C2 不参与。验证样本不足时必须报告未校准，不套用默认温度后宣称完成。

`save_checkpoint(model, tok, cfg, path)` 会写 fp16 safetensors、encoder config、tokenizer 和配置；可覆盖给定目录，因此调用方必须禁止原目录、现有输出目录及符号链接目标。模型命名为 D²Guard-Laya，并记录每个文件哈希和原版前后哈希。

## 与默认流程的差异

不能直接使用 `finetune()` 的随机 `split_calibration()`：本项目要求模板家族、领域、来源数据集不可跨划分。使用底层接口分别传入冻结训练和验证数据，校准完成后才读取评测集。官方 notebook 中的校准失败回退也不采用，失败即报告未完成。

阶段 D 只训练 S1/S2；A1/A2 继续使用原版未校准输出并按决策表处理，不能因 S1 训练而声称动作语义已校准。S1/S2 的输入/输出、模型哈希与阈值需独立记录。

执行中用户确认：仅微调多语言版，保留两个原版；委托 Codex 裁定标签。独立 Gemma4/Qwen 双教师已核验，最终 404 条准入。GPU 接口冒烟通过；一次正式训练已完成（4 epoch、micro batch 8、累积 1、soft-CE、680 问题项、90.51 秒），验证集逐问题校准。原版和发布产物使用独立工作副本，全部哈希不变。D5 表明真实金标准迁移退化，具体指标和限制见阶段报告；没有重训。
