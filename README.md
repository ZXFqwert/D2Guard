# 双镜 D²Guard 程序源码

2026-10-20 同步版本：已合入 Windows 运行与审批续跑、跨会话记忆、模型设置、攻防大屏，以及用户输入直接注入识别。当前状态与验证边界见 [同步核查记录](docs/35-sync-review-20261020.md)；按赛题拆分的三份 Word 文档见 [submission](submission/)。`docs/` 中较早的阶段报告保留历史结果。

同学预览入口：[安全控制台](https://agent.li33.art/safe/preview/)。该入口展示 20 份选定真实演示证据，支持大屏、场景库、历史对照及溯源浏览；公开入口只读，运行、审批与模型配置使用本机控制台。

Git 仓库不含权重、运行原始数据与 1.39 GB 交付压缩包；完整程序包的文件名、大小及 SHA256 见 [交付清单](submission/manifest.json)。下方安装步骤针对含权重的完整程序包。

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
| `scenarios/` | 正式评测场景与演示场景 |
| `weights/` | 快镜 D²Guard-Laya 权重与原版 Laya 基线权重，各附 `SHA256SUMS` |
| `training/` | 快镜训练脚本与数据格式样例（不含训练数据） |
| `tests/`、`acceptance/` | 单元测试与验收证明 |
| `runs/` | `demo-runs.json` 列出的演示与验收运行证据 |
| `lab.py`、`run_evaluation.py`、`verify_v2.py` | 单次运行、配对对照批量评测、证据核验 |
| `tools/` | 安装、配置、控制台启动与打包工具 |

## 关键配置

- 上游模型接口、密钥与本机路径只保存在 `.local/`，该目录不进入程序包。
- 快镜使用 `weights/D2Guard-multilingual`，温度 1.2114818，判定阈值 0.5，判定模式 `taint_gate`；加载时校验 `SHA256SUMS`。
- 无 CUDA 时快镜自动使用 CPU 推理。
- 生成程序包请运行 `build-submission.bat` 或 `sh build-submission.sh`，不要直接压缩含本地配置与虚拟环境的目录。
