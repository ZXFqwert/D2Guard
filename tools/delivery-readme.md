# 双镜 D²Guard 可运行源码

这是 Python 防护服务、Pi Agent 插件、网页控制台和模型权重组成的完整项目，源码不是单个 exe。

Windows 首次部署运行 `setup-windows.bat`；配置完成后双击 `start-console.bat`，访问 http://127.0.0.1:8768/ 。文件、HTTP、MCP、子 Agent、记忆及命令/Git 工具均使用 Windows 本机运行环境，不需要 Linux 虚拟机。详见 [Windows 使用说明](WINDOWS-使用说明.md)。

`src/` 是防护内核与模型推理；`extensions/` 是 Pi 插件；`console/` 是控制台；`scenarios/` 是测试场景；`weights/` 包含两个冻结模型；`tests/` 是单元测试；`acceptance/` 是验收与补测证据；`training/` 提供训练代码与数据格式，不包含原训练数据；`runs/` 按 `demo-runs.json` 和 `supplemental-runs.json` 随包提供演示、Windows 核验及全部直接输入补测记录。

Windows 使用项目独立 `.venv-windows`。上游模型 API 配置和本机路径只保存在 `.local`。新的真实运行追加到 `runs/`，保留失败和挂起结果。控制台记忆场景先由真实 Agent 写入，再使用独立会话读取。

S1 使用 weights/D2Guard-multilingual，温度 1.2114818096160889，阈值 0.5，默认 taint_gate。冻结权重和校准参数未因 Windows 适配改变。原版英文 Laya 基线保留，Windows 按需加载。

Linux 按部署文档建立 venv、安装 requirements-core.txt 和 requirements-gpu.txt、安装固定 Pi 0.85.1，运行 tools/configure_delivery.py。配置工具自动生成 .local/s1.json；start-console.sh 启动真实运行控制台。

生成提交 ZIP 请使用 build-submission.bat，勿直接压缩带本地配置和环境的整个目录。

本机启动控制台后访问 http://127.0.0.1:8768/#/arena ，点击“开始双路对决”后执行真实任务。模型配置由部署端维护（见 `.local/provider.json`），ASK 可在网页审批。新增 `di-*` 场景和 `tools/run_direct_input_evaluation.py` 用于直接输入的配对复测，详见 `acceptance/direct-input-20261020/`。

自由输入与连续追问入口为 http://127.0.0.1:8768/#/chat 。前端通过 Pi 0.85.1 原生 RPC 的 prompt/abort 接口连接同一会话；上下文、自动压缩与工具调用循环由 Pi 管理。D²Guard 检查每轮用户输入和每次工具执行，提供审批与证据展示。附带文本按引用资料处理。网页刷新可恢复当前会话；会话结束或闲置 30 分钟后关闭，服务重启不会自动恢复已关闭会话。

控制台启动时加载并预热快镜，后续任务共享模型与分词器，每轮安全状态、工作区、审批和证据独立。常驻进程只监听本机，凭据不传给 Agent；配置或推理源码变化后需重启控制台。Windows 使用经逐字节校验的只读 FP32 权重映射，数值与原 FP16 权重转 FP32 一致，减少页面文件占用；转换文件只位于 .local，不纳入提交包。慢镜研判在后台进行，结束会话后仍可能需要等待证据归档。

对于支持显式思考控制的 Responses 模型，在“模型设置”中勾选相应选项，使 Pi 的关闭思考设置明确传给上游。不支持该参数的接口保持关闭。公网已验证并启用该配置；不同思考配置的实验结果分别统计。
