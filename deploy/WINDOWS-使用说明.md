# 双镜 D²Guard Windows 使用说明

本程序由 Python 防护服务、Pi 原生 Agent、网页控制台和随包模型权重组成。源码是可编辑的 `.py`、`.ts`、`.js` 等文件；`.bat` 是启动入口。赛题要求交付程序源码，本程序不依赖单文件 `.exe`。

## 启动

1. 新电脑先安装 Python 3.12、Node.js 22.19 或以上、Git for Windows，并将它们加入 PATH。预留约 8 GB 磁盘，推荐 16 GB 内存。
2. 双击 `setup-windows.bat`，安装项目独立环境及固定版本 Pi，按提示填入上游模型接口地址、API Key、模型名称和接口类型。第一次安装需要联网。已有配置会保留。
3. 双击 `start-console.bat`，打开 <http://127.0.0.1:8768/>。首次安装完成后的启动不需再次安装依赖。本项目工作区也提供外层 `启动双镜D2Guard.bat`。
4. 在“自由对话”（`/#/chat`）直接输入任务、附带文本资料并连续追问；在“攻防竞技场”选择场景开始防护关／开对照；“护航模式”运行单次场景；“溯源分析”查看证据。

关闭启动窗口即可停止控制台。运行期间保持窗口打开。端口已被占用时会明确报错，不应重复启动另一套服务。

## 运行方式

Windows 原生 Python 和 Node 执行服务与 Agent。命令和 Git 工具通过 Git for Windows 自带 Bash 执行，不需要 Linux 虚拟机或 WSL。超时由 Windows Job Object 清理子进程树。文件、网络、命令、Git 与 MCP 的实验范围保持和原 Linux 版一致。

快镜 D²Guard-Laya 使用随包冻结权重；无 CUDA 时自动配置 CPU。控制台启动时加载并预热模型，后续任务复用已加载模型，各会话安全状态独立。Windows 使用只读 FP32 权重映射降低页面文件占用，约 1.29 GB 派生文件只保存在 `.local`，并与原权重转换值核查一致。原版英文 Laya 基线仅在需要问答时加载。权重、温度与阈值均未更换。

Pi 仍需要可用的上游模型 API；随包的是防护模型，不是 Pi 所用的大语言模型。离线可查看演示和补测证据，实时执行需要接口连通。页面“攻防大屏”的正式评测汇总来自原研究批次，不是本机实时测速结果。自由对话沿用 Pi 原生 RPC，会话中可停止生成；结束后证据在后台归档，可立即新建对话。

跨会话记忆由 `memory_write` / `memory_read` 工具实现。选择记忆场景后，控制台会先运行真实写入会话，再给新的读取会话独立复制记忆。竞技场的两个分支使用相同初始记忆和测试凭据；读取会话的文件、网页和 MCP 资源为干净版本，使攻击只通过记忆进入。无需手动在网页录入，也不是 Pi 的全局设置。

## 本地配置与验证

配置位于 `.local/provider.json`、`.local/laya.json`、`.local/s1.json`，均为当前机器生成。更换电脑需重新运行安装配置，不复制带旧绝对路径的配置文件。目录名 `requirements-gpu.txt` 是历史命名，在 Windows 上也用于安装 CPU 运行所需的模型依赖。

在程序目录打开 PowerShell，可运行：

```powershell
$env:PYTHONPATH = "$PWD/src;$PWD/tests"
& .\.venv-windows\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
npm test
& .\.venv-windows\Scripts\python.exe verify_v2.py runs/<run_id>
```

实时任务按完成状态查看：ALLOW 表示放行，ASK 表示未执行且等待人工确认，BLOCK 表示阻断。网页会弹出待审批的工具、参数和理由。点击“批准本次并继续”后，当前原生 Pi 会话执行这一调用并继续任务；点击“拒绝本次并继续”则跳过该调用。批准仅对本次参数生效，不能批准硬性 BLOCK。刷新页面可恢复当前待审批任务。审批有效期 5 分钟，过期跳过；旧版已经结束的 ASK 记录不能直接续跑，需要重新发起。不能把挂起当作业务完成。

网页交互运行的单次模型输出预算为 8,192 token，写入记忆和竞技场两路使用相同设置，以免思考输出占满较小预算。命令行离线评测仍默认 2,048，可用 `--max-output-tokens` 显式指定；预算记录在每轮 manifest。

## 生成提交包

双击 `build-submission.bat`，按清单打包源码、权重和 `demo-runs.json`、`supplemental-runs.json` 所列证据，排除本机 `.local` 配置、虚拟环境及缓存，并检查 ZIP 完整性。已有同名 ZIP 时停止，保留原包。`python tools/verify_delivery_sources.py` 可核对运行源码与随包哈希清单。请使用打包入口，不要直接压缩已安装运行环境的整个文件夹。

真实多轮会话、两端推理一致性和常驻配对复核见 `acceptance/resident-runtime-20261020/`，新增直接输入识别的两轮配对补测见 `acceptance/direct-input-20261020/`。历史评测与不同配置的补测分别统计。
