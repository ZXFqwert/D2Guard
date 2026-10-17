# 主线文档阅读顺序

当前约束：`../AGENTS.md` → `整体设计文档.md` → `12-codex-execution-plan.md`。本轮只做阶段 A。

| 文档 | 定位 |
|---|---|
| [00-project-map](00-project-map.md) | 当前目录、资源、配置位置与开发入口 |
| [整体设计文档](整体设计文档.md) | 你与 Claude 确立的目标设计；§12 为实现状态 |
| [11-claude-review](11-claude-review.md) | 决策依据、旧方案问题和设计思考 |
| [12-codex-execution-plan](12-codex-execution-plan.md) | A–I 分阶段执行与验收规范 |
| [14-stage-a-report](14-stage-a-report.md) | 本阶段改动、测试、验收、限制 |
| [03-status](03-status.md) | 按时间追加的工作记录；顶部旧数字属于当时版本 |
| 01–10、architecture-blueprint.md | 方案演进、迁移和历史实验；保留路径供证据引用 |
| *.json | 对应历史批次的统计/核验摘要，原始数据在 ../runs/ |

未迁移旧 JSON 摘要和历史文档，避免切断运行证据引用。请按日期和引擎标识区分 m1、d2core、d2v2；历史通过结果不能替代阶段 A 重新验收。
