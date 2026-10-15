# d2guard_core

基于 FastAPI、Pydantic v2 与 SQLite 的智能体运行时审计内核。接口以原始 `D2guard_contract.json` 为准，保留全部 JSON 字段名、枚举与 DAG 的 `from` 字段。包含契约中的五个接口，默认监听 `127.0.0.1:8765`，按契约启用 `allow_origins=["*"]` 的 CORS。

## 安装与启动（PowerShell 7）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe server.py
```

已有虚拟环境时直接执行最后一行。也可以使用 `python -m uvicorn server:app --host 127.0.0.1 --port 8765`。Swagger 位于 `http://127.0.0.1:8765/docs`。

```powershell
New-Item -ItemType Directory -Path '.test-tmp' -Force | Out-Null
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp=.test-tmp/local-run
```

该临时目录用于避开本机默认 pytest 临时目录的权限问题。pytest 可能清理指定的 `--basetemp`，只使用专用测试目录。

## 模块与接口

| 模块 | 职责 |
| --- | --- |
| `models.py` | 严格契约 DTO、生命周期、偏移映射、敏感登记簿与内部状态 |
| `extractor.py` | 非破坏性规范化、敏感读取识别、精选原文证据区间 |
| `mirrors.py` | `FastMirrorAdapter`、本地模型加载、确定性降级与 `SlowMirrorClient` |
| `state_machine.py` | `update_state`、首帧锚点、跨轮账本、生命周期参数绑定、DAG |
| `policy_engine.py` | `decide` 与五条 YAML 强制策略 |
| `execution.py` | Bash AST 分析及 `SafeExecutor` 的无 shell 子进程包装 |
| `approval.py` | 60 秒 HMAC 签名、参数哈希绑定与一次性消费 |
| `storage.py` | WAL、事务、幂等事件、决策审计、审批审计及签名密钥持久化 |
| `server.py` | 五个契约路由、应用工厂、错误脱敏与固定地址启动 |

| Method | Path |
| --- | --- |
| POST | `/api/v1/events/ingest` |
| POST | `/api/v1/actions/decide` |
| POST | `/api/v1/actions/approve` |
| GET | `/api/v1/sessions/{session_id}/telemetry` |
| POST | `/api/v1/sessions/{session_id}/armor` |

成功响应不增加自定义顶层字段。校验失败返回 422，重复标识的冲突返回 409，无效/过期/已消费审批返回 403，未知会话查询返回 404。错误响应采用 FastAPI 风格 `detail`，不回显原始凭证。

## 调用协议

先上报 `event_type=USER_INPUT, source_type=USER` 的真实用户任务，再上报工具生命周期事件。只有真实用户输入能够首次设置 `anchor_intent`；后续输入和不可信资源无法替换它。代码检视使用契约的 `task_type=code_review_readonly`，同时锁定 `git.push` 和 `git.commit`。

同一逻辑工具调用必须复用 `call_id`，三个阶段只能使用 `MODEL_PROPOSED`、`TOOL_PRE_EXEC`、`TOOL_POST_EXEC`。绑定范围包括 session、agent、工具名称和规范 JSON 参数哈希；参数变化必须分配新 `call_id`。`TOOL_POST_EXEC` 允许省略返回事件中的参数内容，即传 `{}`，服务沿用已登记的调用参数。所有契约字段仍须存在。相同 `event_id` 和完全相同的负载重试返回原响应；内容改变返回冲突并回滚。

`fs.read` 等读取只有在 `TOOL_RETURN + TOOL_POST_EXEC` 时登记配置内容。必须先完成读取结果的上报，再申请后续出站动作。支持 `.env`、`.env.*`、`id_rsa`、`id_ed25519`、PEM/key、credentials 等路径；保存完整配置，并单独登记 API_KEY/SECRET/TOKEN/PASSWORD 等配置值。返回遥测仅包含 ID、来源和分片数量。

`decide` 和执行前/后 ingest 会累计外发**尝试**（MODEL_PROPOSED 不进入账本）；`blocked=true` 表示尝试被阻断，不代表数据已经发送。以单域名、单凭证、编码视图维护匹配集合，重复阶段和重复调用不增加覆盖率。`sub_chunks` 为 UTF-8 字节的 8 字节滑动窗口，重复窗口去重；不足 8 字节时以完整值为单个窗口。Base64 同样维护编码窗口，并兼容 URL-safe、去填充、URL 编码和检测视图中的 Base64 解码。

`coverage_ratio` 按命中窗口覆盖的字节位置并集计算，取任一凭证任一视图的最高覆盖比例，避免登记无关凭证后稀释覆盖率；不会将不同目标域名合并。`matched_chunks_count` 为各凭证明文匹配窗口数与编码窗口换算的明文等效数中的较大值之和，不将两种视图直接相加，也不会超过登记窗口总数。完整明文或 Base64 匹配直接阻断，其他片段在单域名累计比例 `>=0.5` 时阻断。白名单默认空；`trusted_domains` 默认精确匹配，`*.example.com` 才允许其子域，不允许 `example.com.evil.com`。

每个 ASK 动作返回签名 Token，其余裁决返回 `approval_token:null`。审批请求不接收新参数，服务用已保存的原始动作复核 `(session_id,call_id,args_hash)`、60 秒有效期和未消费 nonce。通过或拒绝都原子消费；并发重放仅一次成功。批准前重新执行强制规则，新增敏感登记、只读锚点等变化能够否决旧审批。BLOCK 无法通过审批覆盖。

## 规范化与区间

保留原文，检测旁路依次执行 NFKC、同形字还原、零宽字符移除、内嵌注释移除、引号拼接、`$IFS/${IFS}` 还原和有界 Base64 解码。按 grapheme 规范化保留组合字符语义；每个规范化字符和 token 都映射回原文半开区间 `[start,end)`。Base64 解码文本作为派生视图追加，映射到原编码范围。Token 使用确定性的 Unicode 单词/标点分词，不声称等于某个 LLM 专用 tokenizer 的 token ID。完整映射与原事件保存在事件审计记录中，HTTP 响应只按契约返回 `char_span/token_span`。

## 五条 YAML 策略和执行边界

策略文件固定包含契约的五条规则，启动时检查 ID、必要工具名称、阈值和未知配置项。敏感路径检查同时处理大小写、相对路径、`..`、URL 转义、Windows 分隔符/设备前缀及可解析的符号链接。保守拒绝复杂命令替换、下载执行链、Base64 解码执行、重定向、命令链、不透明解释器/包装器和无法解析的 Shell 语法。支持解析正常管道结构，`cat README.md | sort` 可放行。`exec` 中的直接 git push/commit 也受只读锁约束。

API 负责审计与裁决，不会自行执行任意工具或命令。宿主必须在实际执行前强制检查裁决。需要本地执行时，通过 `SafeExecutor.run(argv)` 传入显式参数；禁止 `shell=True`，锁定真实 `cwd`，只允许配置的可执行程序，移除敏感环境变量和潜在启动注入变量，使用 UTF-8 容错捕获和执行超时。默认包装器仅允许 `git/rg`，git 限定读取子命令并关闭外部 diff/textconv/hooks/fsmonitor。该包装器不等同于操作系统文件/网络沙箱；需要完整隔离时由宿主提供独立用户或容器。

## 快镜与慢镜配置

| 环境变量 | 默认值/含义 |
| --- | --- |
| `D2GUARD_DB` | `data/d2guard.sqlite3` |
| `D2GUARD_POLICIES` | 项目内 `policies.yaml` |
| `D2GUARD_EXEC_ROOT` | 项目目录，子进程固定工作目录 |
| `D2GUARD_SIGNING_KEY` | 可选，至少 32 字节；未设置时在 SQLite 生成并持久化 |
| `D2GUARD_FAST_MODEL_PATH` | 可选，本地完整模型目录；未设置使用确定性启发式 |
| `D2GUARD_FAST_BACKEND` | `laya`、`laya-int8`、`laya-onnx` 或 `onnx` |
| `D2GUARD_SLOW_BASE_URL` | 可选，OpenAI 兼容 API 基址，例如服务商的 `/v1` 基址 |
| `D2GUARD_SLOW_API_KEY` | 可选，远程 API 密钥 |
| `D2GUARD_SLOW_MODEL` | `deepseek-chat` |

Laya：安装 `pip install -e '.[laya]'`。使用完整本地 checkpoint：`rl_agent_config.json`、`model.safetensors`、`encoder/config.json`、`tokenizer/tokenizer.json`。`laya-int8` 在本地加载后进行 CPU 动态 INT8 量化；`laya-onnx` 使用已导出的本地 `laya.onnx`，可提供已量化的 ONNX 权重。不会自动下载权重。通用 `onnx` 后端安装 `.[onnx]`，提供 `model.onnx` 和 `tokenizer.json`；输入为 int64 的 `input_ids/attention_mask`（可选 `token_type_ids`），输出为 `content_nature_logits/action_alignment_logits`，标签顺序与契约枚举一致。

模型加载/预热在启动期间完成。每个 adapter 最多一个在途模型任务，最多等待 10ms，超时、繁忙、异常或模型缺失立即使用确定性特征；不累积超时任务。`latency_ms` 来自真实计时，15ms 是推理接口的延迟预算；Python、Windows 调度和未知模型权重不提供硬实时保证，需要在目标设备和真实权重上验收。

使用 `laya-onnx` 时安装 `pip install -e '.[laya,onnx]'`，以同时提供 Laya 与 ONNX Runtime。

指令性或偏离动作会触发慢镜复核。发送内容只包含 verdict、规则 ID、分类标签、覆盖率与锚点类别，置于 `<audit_evidence_sandbox>` 标签内；不发送原始正文、任意工具参数和密钥。远程报告仅追加说明，不改变内核裁决。网络调用在 SQLite 写事务之外执行；超时、非中文/无效结构、HTTP 错误或未配置时保留本地中文研判。

SQLite 使用 WAL、`BEGIN IMMEDIATE`、30 秒 busy timeout、FULL 同步和参数化 SQL。按要求持久化明文凭证，数据库及备份应由可信本机服务账号保管。此契约是本机可信宿主的控制接口，当前没有新增认证字段或变更 CORS/请求协议。

整合并行原型时，数据库版本 1 会事务迁移到版本 2：原始状态存入 `state_migration_backup`，移除原型私有 DAG `risk` 字段，升级调用哈希的 agent/tool 绑定，并使旧哈希绑定的未消费审批失效；历史事件和决策审计保留。并行提供的 `normalizer.py/fast_mirror.py/slow_mirror.py` 源文件另行保留，当前服务的正式入口使用上表列出的 `extractor.py/mirrors.py`。

实现依据：[FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)、[Pydantic Models](https://docs.pydantic.dev/latest/concepts/models/)、[Python sqlite3](https://docs.python.org/3/library/sqlite3.html)。
