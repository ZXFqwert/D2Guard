# D²Guard-Laya 运行环境与算力机交接

更新：2026-10-21

这份页面是当前运行入口的唯一交接记录。早期阶段报告中的模型选型和实验目录可能描述当时状态；执行新实验、部署或核验时，以本页和 `.local` 中的实际配置为准。

## 1. 项目核心模型

**项目核心为自行训练并冻结的 D²Guard-Laya S1 多语言模型。**

| 用途 | 位置 | 说明 |
|---|---|---|
| 交付/便携副本 | 根工作区 `交付件/03-程序源码/weights/D2Guard-multilingual/` | 随源码包提供，含 `model.safetensors`、tokenizer、encoder 和 `SHA256SUMS` |
| GPU 实验副本 | `/home/roots/d2guard-next-lab-20261016/.local/stage-d5-supplement/D2Guard-multilingual` | 由算力机 resident inference 加载；不进入公开交付包 |
| 本地配置入口 | `.local/s1.json` | 由部署端生成；不要复制到提交包 |
| 配置模板 | `s1-config.example.json` | 使用相对路径 `weights/D2Guard-multilingual`，用于新环境生成配置 |

**主库 `d2guard-next/weights/` 当前没有权重；Git 不携带权重。** 本机演示使用已安装的便携源码；需要在主库执行推理时，应显式使用便携权重或已验证的 resident descriptor，不能把主库旧 `remote_only` 配置视为模型缺失。

已核验的 GPU 运行参数：`schema=d5-request-v1`、`selected=multilingual`、`decision_mode=taint_gate`、`activation=production`、`threshold=0.5`、`device=cuda:0`、temperature `1.2114818096160889`。`model.safetensors` SHA-256 为 `7e96b8c58d52eb6bfc1801b89231217287cfb2ba5d800cc6478f663cbc281fb1`；算力机实际文件哈希与该值一致。

`weights/Laya-original-english/` 和 `.local/laya.json` 是独立的英文基线/原生 tokenizer 组件。它们不等于 D²Guard-Laya，也不能作为当前快镜模型的替代品。Pi 的上游大语言模型同样不是这个防护模型，二者职责不同。

## 2. 本地 Windows 环境

主库为 `d2guard-next`，便携源码为 `交付件/03-程序源码`。本地上游接口、密钥、绝对路径和 resident descriptor 只在 `.local`，不得打印、提交或打包。

使用项目安装脚本生成 `.local/provider.json`、`.local/laya.json`、`.local/s1.json` 后，启动 `start-console.bat`，访问 `http://127.0.0.1:8768/`。没有 CUDA 时 S1 自动走 CPU；有 CUDA 时按 `.local/s1.json` 的 `device` 运行。模型权重、温度、阈值不要在测试中临时改动。`device=cuda:0` 是上述 GPU 核验值；本机便携配置实测为 `cpu`。

2026-10-21 本机路径核验：

| 组件 | 实际位置及版本 |
|---|---|
| 程序 Python | `交付件/03-程序源码/.venv-windows/Scripts/python.exe`，3.12.12 |
| 系统 Python（运维与无模型测试） | `C:/Python313/python.exe`，3.13.2 |
| Node / npm | `D:/nodejs/node.exe`，24.15.0；npm 11.17.0 |
| 项目 Pi | `交付件/03-程序源码/.local/pi-runtime/node_modules/@earendil-works/pi-coding-agent/`，0.85.1 |
| 全局 Pi | `%APPDATA%/npm/pi.cmd`，0.85.1；部署启动器优先使用项目 npm prefix |

项目安装器是 `tools/setup_runtime.py`，配置器是 `tools/configure_delivery.py`，启动器是 `tools/console_launcher.py`。不要把系统 Python 3.13 与便携 Python 3.12 混为同一个环境。

文档渲染和 Office 检查使用 Codex bundled runtime；当前运行时路径由 `load_workspace_dependencies` 动态发现，不要把临时版本目录写进项目配置。

## 3. 正确的 GPU 项目与服务

本轮项目部署是：

- 项目目录：`/home/roots/d2guard-preview-20261020`
- systemd 用户服务：`d2guard-preview.service`
- resident inference 使用的 Python：`/home/roots/d2guard-next-lab-20261016/.venv/bin/python`
- 远端 Python 3.12.3，Node 22.22.1；preview 的 `.local/pi-runtime` 指向 lab 项目的同名目录。
- resident descriptor：项目 `.local/inference-*.json`（含访问令牌，禁止读取或输出内容）
- 推理配置：项目 `.local/s1.json` 的等价部署配置，实际加载上述 D²Guard-Laya GPU 权重

不要操作 `/home/roots/d2guard-current` 或 `d2guard-unified.service`。它们属于旧的 D2guard_desk/D2guard_core 工程，不是本项目的预览服务。重启前先检查本项目 `/api/active-job` 是否为 `null`，确认没有在途任务；只在空闲时重启 `d2guard-preview.service`。

## 4. Pi 与远端 Python/Node

算力机项目使用独立 Python venv 和项目私有 npm 前缀，避免调用系统中不匹配的 Pi：

```bash
cd /home/roots/d2guard-preview-20261020
source .venv/bin/activate
export D2_INFERENCE_DESCRIPTOR="$PWD/.local/inference-<active>.json"
export npm_config_prefix="$PWD/.local/pi-runtime"
export PATH="$PWD/.local/pi-runtime/bin:$PATH"
pi --version                         # 固定 0.85.1
python run_evaluation.py --scenario <scenario> --repeats 3 --workers 1 --timeout 180
```

真实 Pi 会话必须由 `lab.py`/`run_evaluation.py` 通过原生 RPC 创建；不要回放事件、预设 Agent 动作或把模型失败改写成通过。补充实验使用 `d2-test-` 合成凭据。

## 5. SSH 访问

根工作区 `.local/direct-input-20261020/remote.py` 是受限访问封装，默认连接 `roots@10.33.0.30` 并进入上面的预览目录。它从根 `.local/DEVOPS_ACCESS.local.md` 和用户 SSH 目录读取私有认证材料；这些文件内容、密码、私钥和 descriptor token 不写入日志。

常用操作（在根工作区执行）：

```powershell
python .local/direct-input-20261020/remote.py exec "systemctl --user status d2guard-preview.service --no-pager"
python .local/direct-input-20261020/remote.py exec "curl -fsS http://127.0.0.1:8768/api/active-job"
python .local/direct-input-20261020/remote.py exec-venv-file .local/<private-check-script>.py
python .local/direct-input-20261020/remote.py upload src/evaluation_scenarios.py scenarios/<scenario>.json
```

`exec-venv-file` 使用远端项目 venv；上传路径相对主库。任何重启、源码同步或模型替换都要先做空闲检查并留存核验结果。

## 6. 模型身份核验

不读取密钥即可核对核心模型：

1. 检查 `weights/D2Guard-multilingual/SHA256SUMS` 和 `model.safetensors` 哈希。
2. 检查 `.local/s1.json` 的 `selected`、`decision_mode`、`activation`、`threshold` 与本页一致。
3. 通过 resident metadata 检查 `content.schema=d5-request-v1`、`content.models.multilingual` 和同一 `model.safetensors` SHA-256。
4. 检查本轮 `runs/<run-id>/decisions.jsonl` 的 `core_started`；`content_model_error` 必须为空，不能只凭文件路径推断模型已加载。

如果三处身份不一致，停止补测并先修复配置；不要把英文原版 Laya 的成功启动当成 D²Guard-Laya 已加载。
