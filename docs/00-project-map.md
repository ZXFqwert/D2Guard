# 当前项目与开发资源

更新于 2026-10-21。唯一开发仓库为本目录上一级 `d2guard-next`，根工作区不受 Git 管理。阶段历史与当前交付状态分开记录；运行环境和算力机接入以[交接手册](39-runtime-and-compute-handoff.md)为准。

方案根本：工具侧 Hook、API 网关、MCP 中间代理共享防护内核。授权/来源/机密/数据流由确定性账本与策略处理；快镜回答窄语义问题；慢镜目标是 ASK/BLOCK 后反事实研判与训练闭环。项目领域模型已经训练并冻结；慢镜只作异步分析，不改变裁决。后文早期开发命令保留历史来源，当前操作以交接手册为准。

| 资源 | 已知配置 / 证据 | 当前核验范围 |
|---|---|---|
| Windows 工作区 | Python/Node 项目环境与版本见[交接手册](39-runtime-and-compute-handoff.md) | 便携权重与 GPU 实际权重哈希一致；主库无权重 |
| GPU 预览部署 | `/home/roots/d2guard-preview-20261020`；`d2guard-preview.service` | 2026-10-21 确认此为本轮项目部署；切勿混同旧 D2Guard_desk/Core 工程 |
| GPU 推理模型 | `.local/stage-d5-supplement/D2Guard-multilingual`（实验资产）；交付副本 `weights/D2Guard-multilingual/` | resident inference 的实际权重 SHA-256 已与交付权重核对一致 |
| 远端运行环境 | 独立 `.venv`、Pi 0.85.1、项目私有 `.local/pi-runtime` npm prefix | 具体 Python、Node、Pi 与 SSH 操作见[交接手册](39-runtime-and-compute-handoff.md) |
| 主模型/API | `huihui-qwen3.8-27b`，Responses，端点与密钥见 `.local/provider.json`（不入库） | 当前补测使用真实 Pi；历史 A6 数据保留 |
| API 密钥 | 部署目录 `.local/provider.json` | 已确认存在；不复制到文档、命令或场景 |
| 快镜 | 项目训练的 D²Guard-Laya，`weights/D2Guard-multilingual/` | 当前快镜；官方英文 Laya 是独立基线/原生 tokenizer 组件，不是该模型 |
| 本地私有资源 | 部署目录 `.local/provider.json`、`.local/laya.json`、`.local/s1.json` | 认证材料与推理路径不入 Git；现行 SSH 使用根工作区 remote.py 封装 |
| 运维接入说明 | 根工作区 `.local/DEVOPS_ACCESS.local.md`；用户 `.ssh/` | 已验证已有私钥认证；具体文件与解锁方式见私有记录 |
| 实验原始证据 | `runs/<run-id>/`，manifest、SQLite、Pi 原始事件、接收回执 | 不与单元测试或离线诊断混算 |
| 数据种子 | `datasets/security-seed-v0/` | 384 条早期种子；不是当前冻结 D5 训练集，当前训练证据见 acceptance/training.json |

开发命令（在 d2guard-next 内执行）：

```powershell
python -m unittest discover -s tests -v
node --test tests/boundary.test.mjs
```

算力机复现命令（Bash，仅用于远端；先按 39 号手册设置 resident descriptor）：

```bash
cd /home/roots/d2guard-preview-20261020
export CUDA_VISIBLE_DEVICES=0
export NPM_CONFIG_PREFIX="$PWD/.local/pi-runtime"
.venv/bin/python lab.py matrix --engine d2v2 --scenario readme-setup-registration --timeout 300 --repeats 1
.venv/bin/python verify_v2.py runs/<实际批次>.json
```

资源与边界：普通工具限定实验工作区和受控 HTTP；未开放任意 Shell 或互联网，不称为完整 OS 沙盒。SSH 只用于已授权开发环境，不能因此把 Agent 实验工具边界扩大。

历史资料：01–10 文档和各 JSON 是原阶段快照；07 为迁移/算力机记录，08–09 为后续关系修复与英文基线，11–12 和整体设计包含方案演进，当前能力与参数以 38–40 为准。根旧源码、桌面、部署和发行物已整体归档。当前仓库内的 d2core 仍被 d2v2 的提取器、硬策略等导入，不能作为“旧版本”直接搬走。


## 历史环境记录（非当前操作说明）

2026-10-17 接入更新：Mesh 已验证可用；公网备用入口见 `.local` 私有记录，本轮未测试。采用私钥认证，不能把解锁口令当作服务器账户密码。私有调度器 `.local/stage_a_remote.py` 已修正；A6 使用 Python 3.12.3、Node 22.22.1、Laya 0.4.6、Torch 2.10.0+cu128。

2026-10-17 阶段 B 更新：最终矩阵 `matrix-20261017-102542` 与远端/本地 verify_v2 通过；93 Python＋3 Node 测试通过。本地记忆默认在每轮忽略目录，`--memory-root` 可由宿主指定共享私有目录。/approve 的一次执行许可已实现，CLI 完整交互续跑仍待验证。
