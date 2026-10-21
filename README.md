# 双镜 D²Guard 程序源码

2026-10-21 最终功能交付版本：包含 Pi 原生连续会话、自由输入、常驻快镜、Windows 与 Linux 运行、审批续跑、直接注入识别及真实配对补测。最新测试、部署与文档核查见 [最终验收记录](docs/41-final-acceptance-20261021.md)；按赛题拆分的三份 Word 文档见 [submission](submission/)。`docs/` 中较早的阶段报告保留历史结果。

启动控制台后，可在自由对话（http://127.0.0.1:8768/#/chat）直接输入任务、附带文本并连续追问，或在攻防竞技场（#/arena）选择场景进行双路对照，两者都由真实 Pi 执行。ASK 可在网页审批，运行后可查看溯源。共享控制台同时接收一个执行任务，已结束会话的研判归档在后台继续；模型连接由部署端维护。新增 `di-*` 场景覆盖中英文直接输入和相近正常表述。

Git 仓库不含权重与运行原始数据；完整程序包的文件名、大小及 SHA256 见 [交付清单](submission/manifest.json)。下方安装步骤针对含权重的完整程序包。

双镜 D²Guard 是面向大模型智能体的运行时防御系统，由 Python 防护服务、Pi 智能体钩子插件、安全控制台与快镜模型权重组成，可在 Windows 与 Linux 上原生部署。

| 平台 | 首次安装 | 启动控制台 |
|---|---|---|
| Windows 10／11 | 双击 `setup-windows.bat` | 双击 `start-console.bat` |
| Linux | `sh setup-linux.sh` | `sh start-console.sh` |

安装完成后在浏览器打开 http://127.0.0.1:8768/ 。安装、配置、演示与测试步骤见 [使用说明](使用说明.md)。

## 目录

| 目录或文件 | 内容 |
|---|---|
| `src/` | 防护内核（证据库、增量安全链、策略、决策表、溯源、慢镜）、API 侧网关、MCP 中间代理、快镜推理 |
| `extensions/` | Pi 执行前钩子插件与工具边界 |
| `console/` | 安全控制台（服务端与静态前端） |
| `scenarios/` | 竞赛评测场景与演示场景 |
| `weights/` | 快镜 D²Guard-Laya 权重与原版 Laya 基线权重，各附 `SHA256SUMS` |
| `training/` | 快镜训练脚本与数据格式样例（不含训练数据） |
| `tests/`、`acceptance/` | 单元测试与验收证明 |
| `runs/` | `demo-runs.json` 的演示证据与 `supplemental-runs.json` 的全部评测证据（完整程序包内） |
| `lab.py`、`run_evaluation.py`、`verify_v2.py` | 单次运行、配对对照批量评测、证据核验 |
| `tools/` | 安装、配置、控制台启动与打包工具 |

## 关键配置

- 上游模型接口、密钥与本机路径只保存在 `.local/`，该目录不进入程序包。
- 项目训练的 D²Guard-Laya 快镜使用 `weights/D2Guard-multilingual`，温度 1.2114818，阈值 0.5，模式 `taint_gate`；加载时校验 `SHA256SUMS`。环境与算力机配置见 [`docs/39-runtime-and-compute-handoff.md`](docs/39-runtime-and-compute-handoff.md)。
- 无 CUDA 时快镜自动使用 CPU 推理。
- 控制台启动时一次加载模型，各会话独立维护安全状态。用 `python tools/verify_delivery_sources.py` 核对本机、算力机和提交包的公共运行源码。
- 当前 Responses 模型支持显式思考控制，部署配置设为 `reasoning_capable: true`。Pi 的 `--thinking off` 会由此发送 `reasoning.effort=none`，避免服务端默认开启思考。其他接口应确认支持后再启用；每轮清单记录此配置。
- 生成程序包请运行 `build-submission.bat` 或 `sh build-submission.sh`，不要直接压缩含本地配置与虚拟环境的目录。
