# D²Guard 总装版

在本目录使用 PowerShell 7。需要 Python 3.11+、Node.js 22+。首次安装依赖需要网络；依赖就绪后，无 GPU、无模型权重、无云端 API Key 均可运行。

## 一键启动

```powershell
python start_all.py
```

也可双击 `start_all.bat` 或 `启动D2Guard-Desk.bat`。启动器检查 8765/5173 端口，准备依赖、构建前端，等待内核契约健康检查通过，再启动页面服务和 Electron。关闭桌面窗口或按 Ctrl+C 会回收本次启动的子进程。端口已被占用时直接说明冲突，不会杀死已有进程。

```powershell
# 浏览器模式
python start_all.py --web

# 已构建时快速启动；适合离线演示
python start_all.py --no-build

# 只启动后台服务，供 HTTP 联调使用
python start_all.py --headless --no-build
```

内核：`http://127.0.0.1:8765`；工作台：`http://127.0.0.1:5173`。日志在 `output/logs/`。

若 npm 的脚本审批设置跳过了 Electron 下载，启动器会打开同一个浏览器工作台。需要补齐桌面运行时，可联网执行：

```powershell
Set-Location D2guard_desk
node node_modules/electron/install.js
Set-Location ..
```

## 桌面界面与模型接入（2026-10-15）

前端改为固定侧栏与五个独立页面：防护总览、执行工作台、场景库管理、溯源分析、设置与接入。默认普通模式，左下角启用铠甲后展开 14px 几何外框（窄屏为 12px）。所有裁决、审批和开关继续使用原有 5 个 HTTP 契约。

设置页或输入坞的模型胶囊可配置 Base URL、API Key、主模型与慢镜模型，支持 Chat Completions 和 Responses。保存后立即同步内核并持久化到本机数据库，浏览器只保存无密钥配置；空密钥表示保留已保存值，勾选清除才会移除。主模型建议工具动作后仍经原有 Hook 裁决。无 Key 时降级为本地任务登记与结构化复核。当前已录入的测试模型为 `huihui-qwen3.8-27b`，使用 Responses 协议；密钥不包含在源代码或报告中。

新增 `/api/desktop/` 接口负责配置读写、真实模型列表测试、主模型规划、运行健康、独立快慢镜耗时、原文 Token 证据和 YAML 策略只读查询。原有契约文件、`d2guardClient.ts`、`AgentHarness.ts`、`D2GuardHook.ts`、启动守护器和 Electron 启动逻辑均保持不变。内核新增 `desktop_api.py`，并在 `server.py`、`mirrors.py` 中接入扩展。

场景库支持增删改查、筛选、JSON 导入导出和真实运行。DAG 按实际依赖分层，时序视图、字符/Token 染色和 Markdown/JSONL 导出使用内核证据。统计累计范围为当前桌面打开后的会话；“合规任务成功率”指合规申请获内核授权比例，不代表外部工具已经执行。

## 演示

1. 运行剧本 2，查看真实读取的测试凭据、跨轮覆盖率和红色 BLOCK 节点。第一个 8 字节片段放行，第二个达到覆盖阈值后阻断。
2. 关闭左侧铠甲，再运行同一剧本，所有动作都由内核返回 ALLOW。每次演练会新建会话并保留开关状态。
3. 开启铠甲，运行剧本 6，体验 ASK 单次批准或拒绝；令牌有效期为 60 秒。
4. 自由输入支持任务文本，或显式动作 JSON：

```json
{"initial_task":"只读检视项目 README","tool_name":"git.push","tool_args":{"remote":"origin/main"}}
```

所有安全结论来自内核；图谱来自 telemetry。剧本载荷和 `public/fixtures/` 是明确的验收测试输入。工作台演示真实审计与授权结果，不执行恶意网络传输、远端推送或系统文件写入，也不伪造这些操作的成功返回。需要接入生产 Agent 时，应将实际工具执行器挂在同一裁决/审批闭环之后。

## 复验

```powershell
# 根目录：内核原有测试 + 最终总装验收，共 192 项（原有 174 项 + 模型扩展 16 项 + 双模式部署 2 项）
.\D2guard_core\.venv\Scripts\python.exe -m pytest -q --junitxml=output/pytest-results.xml

# 先启动 headless 服务，再在另一个终端运行
npm --prefix D2guard_desk run test:integration

# 停止运行中的服务后，测试端口冲突、健康等待和异常进程回收
python scripts/verify_supervisor.py
```

UI 回归使用 Playwright CLI，服务启动后执行：

```powershell
npx.cmd --yes --package @playwright/cli playwright-cli -s=d2guard-final open http://127.0.0.1:5173
npx.cmd --yes --package @playwright/cli playwright-cli -s=d2guard-final run-code --filename scripts/ui_acceptance.js
npx.cmd --yes --package @playwright/cli playwright-cli -s=d2guard-final close
```

本次重构验收结果见 `output/frontend-redesign-results.json`，真实远程模型结果见 `output/live-model-results.json`。最新截图位于 `output/playwright/`：

- `normal-mode.png` / `armor-mode.png`：普通工作台和铠甲外框。
- `dashboard.png`：真实累计统计和快慢镜耗时曲线。
- `scenario-library.png`：六大场景管理页。
- `trace-analysis.png` / `trace-evidence.png` / `trace-timeline.png`：溯源、染色与时序。
- `settings-model.png` / `mobile-workbench.png`：真实模型配置和窄屏适配。

`ui_acceptance.js` 包含 `ui_redesign_flows.js` 与 `ui_redesign_management.js` 两阶段验收。使用独立 Playwright 会话；完整验收会运行真实模型、创建演练会话、导出证据和临时自定义场景（完成后清除）。远程测试需已在设置页配置可用模型。历史总装验收说明保留在 `D²Guard 最终总装验收报告.md`。


## 可分发桌面程序与服务器部署

Windows 发行包自带内核，解压后双击 `D2Guard.exe`；源码打包执行 `pwsh -File scripts/build-desktop.ps1`。两种模式与旧版 Arena 的兼容方式见 [部署说明](deployment/README.md)。服务器更新执行 `bash deployment/deploy.sh --pull`。

打包版验收：`node scripts/verify-desktop.cjs /path/to/playwright`，需要先在桌面设置中配置模型以验证自然语言规划。
