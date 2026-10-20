# 双镜 D²Guard 可运行源码

这是 Python 防护服务、Pi Agent 插件、网页控制台和模型权重组成的完整项目，源码不是单个 exe。

Windows 首次部署运行 `setup-windows.bat`；配置完成后双击 `start-console.bat`，访问 http://127.0.0.1:8768/ 。文件、HTTP、MCP、子 Agent、记忆及命令/Git 工具均使用 Windows 本机运行环境，不需要 Linux 虚拟机。详见 [Windows 使用说明](WINDOWS-使用说明.md)。

`src/` 是防护内核与模型推理；`extensions/` 是 Pi 插件；`console/` 是控制台；`scenarios/` 是测试场景；`weights/` 包含两个冻结模型；`tests/` 是单元测试；`acceptance/` 是原验收证明；`training/` 提供训练代码与数据格式，不包含原训练数据；`runs/` 按 `demo-runs.json` 随包提供历史演示与新增 Windows 核验记录。

Windows 使用项目独立 `.venv-windows`。上游模型 API 配置和本机路径只保存在 `.local`。新的真实运行追加到 `runs/`，保留失败和挂起结果。控制台记忆场景先由真实 Agent 写入，再使用独立会话读取。

S1 使用 weights/D2Guard-multilingual，温度 1.2114818096160889，阈值 0.5，默认 taint_gate。冻结权重和校准参数未因 Windows 适配改变。原版英文 Laya 基线保留，Windows 按需加载。

Linux 仍可按上一级部署文档建立 venv、安装 requirements-core.txt 和 requirements-gpu.txt、安装固定 Pi 0.85.1，运行 tools/configure_delivery.py；启用命令/Git 时设置 D2_HOST_EXEC=1。配置工具自动生成 .local/s1.json，无需另外把示例 CUDA 配置导出到环境变量。start-console.sh 提供历史演示查看。

生成提交 ZIP 请使用 build-submission.bat，勿直接压缩带本地配置和环境的整个目录。
