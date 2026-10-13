# 双镜 D²Guard: 基于快慢双系统与增量 JSON 状态流的大模型智能体防御系统

> **赛事名称**：“华为杯”第五届中国研究生网络安全创新大赛  
> **参赛赛道**：揭榜挑战赛  
> **赛题方向**：赛题 5 —— 面向大模型智能体与 MCP 工具链的提示注入与工具滥用的检测防御技术（出题单位：安天科技集团）  
> **系统架构**：**【工具侧 Hook】 + 【API 侧网关】 $\leftrightarrow$ 【共享防护内核（D²Guard Core）】**  
> **核心机制**：**$D^1$（Dual-System 快慢双系统） + $D^2$（Delta-JSON 增量状态流与安全状态聚合）**  
> **三大接口**：`extract(event)` $\to$ `update_state(state, extracted)` $\to$ `decide(state, proposed_action)`

---

## 一、 系统总体架构：前线双探针与中央决策大脑

系统由三大紧密协作的部件构成闭环：
1. **【部件 1: 工具侧 Hook】**：守在工具执行侧，物理拦截本地工具、MCP 与子 Agent 执行（执行刹车闸）；
2. **【部件 2: API 侧网关】**：守在大模型通信侧，抓取 Prompt 增量与模型候选调用，审计数据外泄（模型观测哨）；
3. **【部件 3: 共享防护内核】**：中央决策大脑，持久化存储增量 JSON，维护**安全状态聚合机**，运行**策略引擎 + 快慢双系统**，回传裁决控制参数。

```mermaid
flowchart TD
    subgraph RemoteLLM["外部大模型服务"]
        LLM["DeepSeek-v3.2 API"]
    end

    subgraph Probes["两大前沿探针 (Probes)"]
        Gateway["【部件 2: API 侧网关】(模型进出观测哨)<br/>• 拦截 Prompt 请求与模型输出<br/>• 抓取增量 Prompt 与候选调用<br/>• 防止敏感凭据外泄发往外部模型"]
        Hook["【部件 1: 工具侧 Hook】(执行刹车闸)<br/>• 挂接 Agent 工具执行咽喉<br/>• 拦截 fs / net / exec / git / mcp / subagent<br/>• 接收内核指令物理踩刹车 (阻断/放行)"]
    end

    subgraph AgentSpace["宿主智能体环境"]
        AgentCore["Agent 核心业务逻辑 (ReAct / 规划)"]
    end

    subgraph D2GuardCore["【部件 3: 共享防护内核 (D²Guard Core)】(中央大脑)"]
        EventStore["1. 增量事件流存储 (D2Event 流)"]
        StateAggregator["2. 【安全状态聚合机】update_state()<br/>• 任务与有效授权锚点 (防长文本稀释)<br/>• 已读敏感数据登记薄 (Secret Ledger: 明文与Base64)<br/>• 因果调用拓扑图 (Call Graph) · 累计外发记录"]
        DualEngine["3. 规则 + 快慢双系统决策中枢 decide()<br/>• L0: 策略 DSL 引擎 + exec Shell AST 分析<br/>• L1: 【快镜】Laya 400M (本地定型初筛，设计目标 <20ms)<br/>• L2: 【慢镜】DeepSeek (按需唤醒 <5%, 输出中文判词)"]
    end

    subgraph OSTools["底层操作系统工具执行层"]
        Tools["本地文件 (fs) / 网络 (net) / 命令 (exec) / 代码库 (git) / MCP Server"]
    end

    AgentCore <-->|模型调用通道| Gateway
    Gateway <-->|中继转发| LLM
    Gateway -->|1. 推送 Prompt 增量与模型输出 JSON| EventStore
    D2GuardCore -.->|2. 下发 Prompt 脱敏/拦截指令| Gateway

    AgentCore -->|准备调用工具| Hook
    Hook -->|3. 推送工具动作 JSON, 申请裁决| D2GuardCore
    EventStore --> StateAggregator --> DualEngine
    DualEngine -->|4. 回传裁决控制参数| Hook

    Hook -->|ALLOW: 放行调用| Tools
    Hook -->|BLOCK: 阻断执行| AgentCore
```

---

## 二、 三大核心接口运行逻辑

系统所有防御机制均通过三个极简、清晰的 Python 核心接口实现：

### 1. `extract(event) -> ExtractedData`
* **代码确定性提取**：解析文件绝对路径、目标网络域名、用 `bashlex` 解析 Shell 抽象语法树（管道、重定向、子 Shell）、正则扫描私钥与敏感 Canary 标记；
* **模型主观语义初筛**：由【快镜】Laya（421M 双向编码器，本地部署）给出定型分类信号（判断外部增量是正常资料还是指令诱导，当前动作是预期步骤还是越权行为）。模型结论作为风险参考分，不可推翻硬规则。

### 2. `update_state(state, extracted) -> SecurityState`
* **安全状态聚合机**：解决“单看增量会丢失多轮记忆”的致命问题；
* 记录用户初始任务（不可篡改不变锚点）、更新已读敏感数据登记薄（记录文件路径、数据 ID、明文与预存 Base64 编码）、累积外发域名历史与因果调用链；
* **轻量防爆炸**：内存中只存元数据与事件 ID 引用，100 步长程任务内存占用设计目标保持在 **< 100 KB**。

### 3. `decide(state, proposed_action) -> ActionVerdict`
* **规则评估**：策略 DSL 检查路径黑名单（`~/.ssh`）、检测请求体中是否包含此前读取的敏感数据（原文及 Base64 编码匹配）、拦截危险 Shell 管道命令；
* **慢镜仲裁**：存在疑点时唤醒【慢镜】DeepSeek，只输入精选证据包，输出结构化中文判词；
* **控制参数回传**：向宿主 Hook 回传 `{"verdict": "BLOCK", "reason": "..."}`，Hook 在底层物理掐断工具调用。

---

## 三、 赛题五项核心能力逐项对齐

| 赛题要求 | 双镜 D²Guard 落地实现 |
| :--- | :--- |
| **能力 1：多源注入识别** | 网关与 Hook 截获用户输入、外部 Web/文档/源码/MCP 返回、记忆召回等每一个事件，快镜毫秒级初筛。 |
| **能力 2：意图-计划-动作对齐** | 状态聚合机保留初始任务锚点，慢镜仅比对精选证据包，输出标准结构化中文裁判理由。 |
| **能力 3：细粒度策略与三态决策** | 内核执行 YAML 声明式策略 DSL 与 AST 检查，回传 `ALLOW` / `ASK` / `BLOCK` 参数给 Hook 严格执行。 |
| **能力 4：跨 MCP 与子 Agent 溯源** | 事件流自带 `parent_id` 链条，内核一键直接导出交互式 HTML 攻击溯源 DAG 大屏。 |
| **能力 5：对抗鲁棒性** | 前置清洗器处理多语言、Unicode、注释与编码；安全状态机独立持久化，天然免疫长上下文稀释。 |

---

## 四、 快速上手与工程目录结构

### 1. 运行环境准备
```bash
conda create -n d2guard python=3.10 -y
conda activate d2guard

pip install openai pydantic jinja2 python-dotenv bashlex pyyaml
# 本地决策小模型 (支持 CPU / 普通 GPU，显存 < 1GB)
pip install laya
```

### 2. 项目目录结构
```
创新大赛/
├── .env                          # 远程模型 API 密钥配置 (已存在)
├── README.md                     # 项目介绍与架构说明 (已更新)
├── 00_比赛要求与最终交付.md       # 赛题官方指标逐项分解 (已更新)
├── 01_系统框架与实现方案.md       # 架构三大部件与三大接口详述 (已更新)
├── 02_实验场景与验收方案.md       # 状态消融实验与客观验收标准 (已更新)
├── 03_开发交接与启动说明.md       # 9 天冲刺计划与启动指导 (已更新)
├── d2guard/                      # 【D²Guard 防护中枢源码】
│   ├── __init__.py
│   ├── hook.py                   # 部件 1: 工具侧 Hook (执行刹车闸)
│   ├── gateway.py                # 部件 2: API 侧网关 (模型进出观测哨)
│   ├── core.py                   # 部件 3: 共享防护内核中枢 (中央大脑)
│   ├── extract.py                # 接口 1: 确定性事实与快镜语义抽取
│   ├── state_aggregator.py       # 接口 2: 安全状态聚合机与敏感数据薄
│   ├── decide.py                 # 接口 3: 策略 DSL 匹配与慢镜深度裁判
│   ├── fast_mirror.py            # 【快镜】System 1 (本地 Laya 400M)
│   ├── slow_mirror.py            # 【慢镜】System 2 (DeepSeek 裁判)
│   ├── provenance_dag.py         # 因果事件流直接导出 HTML DAG 图
│   └── normalizer.py             # 7 类对抗样本规范化清洗器
├── agent/                        # 被保护的真实 Agent 环境
│   ├── react_agent.py            # ReAct Agent 核心实现
│   └── tools/                    # 受控工具集 (fs, net, exec, git, mcp)
├── policies/                     # 安全策略配置目录 (YAML)
│   └── default_policy.yaml
├── benchmarks/                   # 12 类典型场景与 7 类对抗测试集
└── run_eval.py                   # 自动化攻防对比与消融评测套件
```
