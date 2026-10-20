# 当前项目与开发资源

更新于 2026-10-17（Asia/Taipei）。唯一开发仓库为本目录上一级 `d2guard-next`，根工作区不受 Git 管理。阶段 A 已有独立检查点；阶段 B 自检完成、等待评审，见 [阶段 B 报告](15-stage-b-report.md)；阶段 C–I 未开始。

方案根本：工具侧 Hook、API 网关、MCP 中间代理共享防护内核。授权/来源/机密/数据流由确定性账本与策略处理；快镜回答窄语义问题；慢镜目标是 ASK/BLOCK 后反事实研判与训练闭环。反事实重放和领域模型训练尚未完成，原版 Laya 输出不是可靠检出证据。

| 资源 | 已知配置 / 证据 | 当前核验范围 |
|---|---|---|
| Windows 工作区 | Python 3.13；Node；已装 Pi 0.85.1 的历史记录 | 本轮运行 Python 与 Node 测试；未在 Windows 加载英文权重 |
| 算力机 | Mesh 接入见 `.local` 私有记录；目录 `/home/roots/d2guard-next-lab-20261016` | Mesh 私钥认证已恢复，A6 四组矩阵及核验通过，见阶段报告 |
| GPU | 历史为 A100 80GB GPU 0；GPU 1 有其他服务负载 | A6 实测 GPU 0 占用 1393 MiB、GPU 1 占用 76373 MiB；仅使用 GPU 0，未改旧服务 |
| 远端运行环境 | 独立 `.venv`，项目 `.local/pi`；Laya 0.4.6、Pi 0.85.1 | 沿用原环境，不升级依赖 |
| 主模型/API | `huihui-qwen3.8-27b`，Responses，端点与密钥见 `.local/provider.json`（不入库） | A6 四组均完成真实 Pi/API 循环，未发生代理错误 |
| API 密钥 | `../.local/provider.json` | 已确认存在；不复制到文档、命令或场景 |
| 快镜 | `convaiinnovations/laya`，revision `7b928d828b7b0e022f929d9bd2e44165aa270148` | Windows `remote_only=true`，英文权重未下载完整；无静默回退 |
| 本地私有资源 | `.local/laya.json`、`.local/models/`、`.local/compute_ops.py` | 模型/配置/工具不入 Git；compute_ops 需进程环境中的解锁口令 |
| 运维接入说明 | 根工作区 `.local/DEVOPS_ACCESS.local.md`；用户 `.ssh/` | 已验证已有私钥认证；具体文件与解锁方式见私有记录 |
| 实验原始证据 | `runs/<run-id>/`，manifest、SQLite、Pi 原始事件、接收回执 | 不与单元测试或离线诊断混算 |
| 数据种子 | `datasets/security-seed-v0/` | 384 条历史待复核数据；未据此训练 |

开发命令（在 d2guard-next 内执行）：

```powershell
python -m unittest discover -s tests -v
node --test tests/boundary.test.mjs
```

算力机复现命令（Bash，仅用于远端）：

```bash
cd /home/roots/d2guard-next-lab-20261016
export CUDA_VISIBLE_DEVICES=0
export NPM_CONFIG_PREFIX="$PWD/.local/pi"
.venv/bin/python lab.py matrix --engine d2v2 --scenario readme-setup-registration --timeout 300 --repeats 1
.venv/bin/python verify_v2.py runs/<实际批次>.json
```

资源与边界：普通工具限定实验工作区和受控 HTTP；未开放任意 Shell 或互联网，不称为完整 OS 沙盒。SSH 只用于已授权开发环境，不能因此把 Agent 实验工具边界扩大。

历史资料：01–10 文档和各 JSON 是原阶段快照；07 为迁移/算力机记录，08–09 为后续关系修复与英文基线，11–12 和整体设计是当前方案依据。根旧源码、桌面、部署和发行物已整体归档。当前仓库内的 d2core 仍被 d2v2 的提取器、硬策略等导入，不能作为“旧版本”直接搬走。


2026-10-17 接入更新：Mesh 已验证可用；公网备用入口见 `.local` 私有记录，本轮未测试。采用私钥认证，不能把解锁口令当作服务器账户密码。私有调度器 `.local/stage_a_remote.py` 已修正；A6 使用 Python 3.12.3、Node 22.22.1、Laya 0.4.6、Torch 2.10.0+cu128。

2026-10-17 阶段 B 更新：最终矩阵 `matrix-20261017-102542` 与远端/本地 verify_v2 通过；93 Python＋3 Node 测试通过。本地记忆默认在每轮忽略目录，`--memory-root` 可由宿主指定共享私有目录。/approve 的一次执行许可已实现，CLI 完整交互续跑仍待验证。
