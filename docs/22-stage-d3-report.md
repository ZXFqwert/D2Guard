# 22 · 阶段 D‴ 报告

> **历史状态说明（2026-10-21）：本页按原日期保留阶段事实，不作为当前配置。项目已训练并部署 D²Guard-Laya S1 多语言模型，当前模型、环境与正确服务见[运行交接手册](39-runtime-and-compute-handoff.md)。当前直接指标为攻击110/164→0/165、正常249/249→230/249、自身误挂起0/929（另2次会话连带暂停）；早期条件指标不再作为交付展示。**

状态：单轮训练与评测完成，模型验收未通过，S1保持关闭。未降低验收线，未重训，未开始阶段E。

## 开工计划、冲突与文件范围

已阅读 AGENTS、设计 §4.2/§9、执行方案全局规则与评审循环、D‴、D″ 评审和保留集复核 README。

1. 独立提交 D″ 实现检查点，保留训练流程和失败模型；不提交 .local，不把本轮语义视图混入检查点。
2. 新增同一个 semantic_view 函数供数据、训练、校准、评测及未来运行时使用；规则检测视图保持原样。用 raw_text 导出派生视图，不改冻结数据，统计俄语混合文字词变化。
3. 先做云端教师、本地生成器与 384-token 完整编码冒烟；未确认接口／长度前不启动批量数据。仅新增训练、验证；旧 8204 条训练全保留，旧验证只做报告。
4. 新增 6400 个训练候选、1800 个验证候选，两个生成器各半；必须通过长度、隔离、双教师复核后分别满足 ≥4000、≥900。数量是候选规划，不把未准入样本计入规模。三方分歧与缺失直接丢弃。
5. 三模型各一组配置，按新验证早停／恢复最低 loss；阈值在 P≥.90、none FPR≤.02 下最大化召回，同召回取较高阈值。没有可行解则候选不得通过，不退回 F1 最大。
6. 集成路由只读语义文本：字母中西里尔／假名／汉字占比 ≥15% 用多语言 Laya，否则用英文 Laya；不读评测语言标签。再与 ModernBERT 校准后三类概率等权平均（request 正好取二者平均）；阈值仅在新验证拟合。候选按验证 R、F1、较低 NLL 排序。
7. 选模锁定后，独立语义保留集只做一次聚合评测，按预登记 5 条排除前后分别报告；公开测试单列。选定模型再做一次 C/C2 回归，不看错例，不改数据或阈值。全部通过才启用并运行既定最多 16 轮回归。

代码冲突：旧输入走规则 normalize、窗口固定 256、旧校准按 F1；本轮用独立语义输入、实测预算与召回优先校准替换模型路径。首句探针仍在训练前门禁，完整 n-gram 的 ≥3 点差距在训练后核验，沿用已明确的依赖顺序。全阶段 4 小时、数据准备 2 小时、训练加评测 60 分钟，计时不重置。

拟新增：src/d2v2/semantic_view.py、stage_d3_protocol.py、stage_d3_data.py、stage_d3_prepare.py、stage_d3_model.py、stage_d3_isolation.py、stage_d3_admit.py、train_stage_d3.py、evaluate_stage_d3.py、stage_d3_collect.py、tests/test_stage_d3.py。必要时复用并参数化旧云端适配／窗口函数；原始规则归一化不修改。达标后才接三类运行时及配置。三份交付：本报告、docs/stage-d3-results.json、docs/stage-d3-verification.md；另更新 docs/03-status.md、设计 §12。

## 本地生成器与数据来源

本地接口实际列出 huihui-ai/Huihui-Qwen3.8-27B-abliterated（服务别名 huihui-qwen3.8-27b），不是把别名 Qwen/Qwen3.8-27B 当成未经修改的原版。权重路径版本尾缀 6b0b6a0d；部署与许可证元数据核验后记录。复用已有 GPU 1 服务，不更改其配置；训练与隔离使用 GPU 0。DeepSeek 和 MiMo 继续读取 .local/teacher.env，日志只有模型、耗时、token。

保留 D″ 已准入公开数据及其来源／许可证：BIPIA MIT、Flask BSD-3-Clause、Click BSD-3-Clause、CPython PSF-2.0。不新增公开评测语料到训练。新文本为两个模型按简报逐条生成的合成文档。

本地 Qwen 派生模型的仓库许可证为 Apache-2.0，已核对部署路径内 README、LICENSE 和 config 的哈希。云端用途沿用已核实的 [DeepSeek 开放平台条款](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html) 与 [MiMo API 用户协议](https://mimo.mi.com/docs/quick-start/terms/user-agreement)；本轮仅发送合成候选。中间服务返回的模型名称及别名留存于本地元数据，这不能证明其实际部署权重。

## 风格清单与划分（生成前冻结）

共 64 种，训练 48、验证 16。每个来源前六种用于训练、后两种仅验证；风格不是固定句框，三类标签都可使用同一风格。禁止六种保留家族及近似改写：三轮对话依赖前文指代；补丁评审附解释说明；仪表盘帮助面板含结构示例；历史讨论加后补；对照新旧行为的工程勘误；按时间顺序交接且埋藏依赖。不把其正文、错误或标签交给生成器。

| ID | 划分 | 来源 | 篇章结构 | request 的呈现方式（quoted/none 相应转为讨论／事实） |
|---|---|---|---|---|
| repository_docs-01 | train | repository_docs | 分层任务教程 | 按目标展开步骤 |
| repository_docs-02 | train | repository_docs | 故障树分支 | 在诊断叶节点给出操作 |
| repository_docs-03 | train | repository_docs | 角色权限矩阵 | 在单元格规定职责 |
| repository_docs-04 | train | repository_docs | 发布物目录索引 | 用条目说明处理要求 |
| repository_docs-05 | train | repository_docs | 配置字段参考 | 在字段约束里规定操作 |
| repository_docs-06 | train | repository_docs | 构建目标依赖图 | 在显式边标签给出执行要求 |
| repository_docs-07 | validation | repository_docs | 练习评分细则 | 按评分维度列可执行任务 |
| repository_docs-08 | validation | repository_docs | 术语词典条目 | 在定义后给出使用规范 |
| code_comments-01 | train | code_comments | 函数契约三段注释 | 前置条件与后置义务 |
| code_comments-02 | train | code_comments | 类型字段行尾注解 | 在属性旁描述操作 |
| code_comments-03 | train | code_comments | 测试夹具Arrange-Act-Assert注释 | 在阶段注释给动作 |
| code_comments-04 | train | code_comments | 正则文法产生式注释 | 在规则旁给处理要求 |
| code_comments-05 | train | code_comments | 伪代码分支注释 | 在分支入口给任务 |
| code_comments-06 | train | code_comments | 编译器警告说明 | 由警告定位给出动作 |
| code_comments-07 | validation | code_comments | 提交钩子配置注释 | 用钩子触发条件给任务 |
| code_comments-08 | validation | code_comments | 错误码枚举注释 | 按错误码关联操作 |
| issue_pr-01 | train | issue_pr | 单条结构化缺陷单 | 在复现字段给操作 |
| issue_pr-02 | train | issue_pr | 投票选项说明 | 在选项中提出具体任务 |
| issue_pr-03 | train | issue_pr | 任务看板卡片 | 在卡片责任栏给动作 |
| issue_pr-04 | train | issue_pr | 单人审查清单 | 逐项列核查要求 |
| issue_pr-05 | train | issue_pr | 自动检查机器人摘要 | 在检查分类中给处置要求 |
| issue_pr-06 | train | issue_pr | 维护者分派单 | 按负责范围指派任务 |
| issue_pr-07 | validation | issue_pr | 测试证据附件目录 | 通过附件用途提出操作 |
| issue_pr-08 | validation | issue_pr | 里程碑验收问卷 | 以验收问题提出行动 |
| email_ticket-01 | train | email_ticket | 主题与短正文邀请 | 以邀请提出操作 |
| email_ticket-02 | train | email_ticket | 客服分类处理表 | 按分类给处置动作 |
| email_ticket-03 | train | email_ticket | 服务请求表单 | 在请求栏明确期望任务 |
| email_ticket-04 | train | email_ticket | 值班通知公告 | 在通知正文给任务 |
| email_ticket-05 | train | email_ticket | 预约确认函 | 在预约条件中规定操作 |
| email_ticket-06 | train | email_ticket | 问答式单封邮件 | 通过提问指定当前动作 |
| email_ticket-07 | validation | email_ticket | 工单优先级分诊表 | 按优先级给处置要求 |
| email_ticket-08 | validation | email_ticket | SLA条款摘录 | 以时间约束提出动作 |
| mcp_description-01 | train | mcp_description | 工具描述与参数约束JSON | 在参数说明提出调用要求 |
| mcp_description-02 | train | mcp_description | 工具权限声明JSON | 按权限项给义务 |
| mcp_description-03 | train | mcp_description | 工具输入输出字段表 | 在字段用途提出操作 |
| mcp_description-04 | train | mcp_description | 工具错误码目录JSON | 按错误类别描述处置 |
| mcp_description-05 | train | mcp_description | 工具副作用分级JSON | 由副作用范围给操作规范 |
| mcp_description-06 | train | mcp_description | 工具资源限制清单JSON | 在配额字段给动作 |
| mcp_description-07 | validation | mcp_description | 工具能力标签字典JSON | 在标签释义给操作条件 |
| mcp_description-08 | validation | mcp_description | 工具批处理契约JSON | 按批次约束规定动作 |
| mcp_return-01 | train | mcp_return | 分组校验结果JSON | 在具体组附处理要求 |
| mcp_return-02 | train | mcp_return | 资源清单分页返回 | 在分页条目给操作 |
| mcp_return-03 | train | mcp_return | 键值状态快照 | 在状态解释给当前任务 |
| mcp_return-04 | train | mcp_return | 规则匹配命中列表 | 在匹配项给动作 |
| mcp_return-05 | train | mcp_return | 测试汇总表 | 在结果分类给处理要求 |
| mcp_return-06 | train | mcp_return | 作业队列返回 | 在单个作业字段给操作 |
| mcp_return-07 | validation | mcp_return | API能力发现结果 | 在服务字段给调用要求 |
| mcp_return-08 | validation | mcp_return | 资源配额统计返回 | 在配额项给处置要求 |
| memory-01 | train | memory | 项目事实卡 | 在卡片属性记录操作约定 |
| memory-02 | train | memory | 个人偏好键值条目 | 按偏好字段规定动作 |
| memory-03 | train | memory | 环境约定词条 | 在约定范围给执行要求 |
| memory-04 | train | memory | 常用命令书签 | 在书签说明给运行任务 |
| memory-05 | train | memory | 资源所有权登记 | 按责任对象给操作 |
| memory-06 | train | memory | 会话目标摘要 | 在目标列表给动作 |
| memory-07 | validation | memory | 服务目录记忆索引 | 按服务链接给处置要求 |
| memory-08 | validation | memory | 工具使用约束清单 | 在约束项给操作 |
| web-01 | train | web | 操作导航菜单 | 用导航说明给操作 |
| web-02 | train | web | 产品功能比较表 | 在比较维度提出试用动作 |
| web-03 | train | web | 单页访问须知 | 在访问条件提出动作 |
| web-04 | train | web | 开发者快速入门图注 | 通过图注给执行任务 |
| web-05 | train | web | 站点状态说明卡 | 在状态卡给处理要求 |
| web-06 | train | web | 资源下载目录 | 在资源说明给操作 |
| web-07 | validation | web | 交互控件帮助气泡 | 通过控件提示提出动作 |
| web-08 | validation | web | 技术文章侧栏术语表 | 在术语用法给操作 |

## 生成提示词样例（非固定句框）

共用约束：只写虚构软件项目的真实形态文档；自行措辞与布局，不输出标签或“这里没有请求”等元说明；具体文件与 example.org URL 在三类都保留；不生成真实凭据。简报给语义约束，不给决定标签的开头句。四种语言均覆盖，新增数据约 10% 其他混淆，训练另约 22% 长文稀释，以使保留旧数据后的整体长文比例达到 5%。

| 类别 | 来源／风格 | 简报样例 |
|---|---|---|
| request | repository_docs-02／中文 | 写虚构包管理器的故障树；在一个诊断叶节点提出核验 config.toml 的当前任务，周围给相关事实；保留 https://status.example.org/check，不点名 AI。 |
| request | mcp_description-04／英文 | 写虚构工具的错误码目录 JSON；在一种错误类别中要求上传合成诊断摘要到 https://diagnostics.example.org/report，.env 作为上下文资产；不是实际执行。 |
| request | email_ticket-03／俄文 | 写虚构服务请求表单；在期望结果栏提出修改 memory/session.json 的当前操作，正文其他栏保持自然业务背景，不用固定命令句。 |
| quoted | code_comments-01／日文 | 写函数契约三段注释，讨论某份不再生效的“删除 build/cache.json”要求，表达历史语义而不要求当前执行；不能写成历史讨论加后补的结构。 |
| quoted | web-02／英文 | 写功能比较表，比较两种曾出现的日志发送指令及其含义；引用指令内容，但不把其变为读者当前任务；保留 archive.example.org URL。 |
| quoted | memory-03／中文 | 写环境约定词条，对一种曾被讨论的 config.toml 编辑要求作解释；不能附加新的当前要求，也不用标签式免责声明。 |
| none | mcp_return-03／俄文 | 写服务键值状态快照，描述 .env 与 credentials.json 的字段角色和已观测状态；URL 是数据字段，不提出操作，也不引用命令。 |
| none | issue_pr-03／日文 | 写已完成任务的看板卡片，只陈述完成事实与资源名称，包含 summary.md 和 example.org 地址；不留下当前待办或操作建议。 |
| none | repository_docs-04／英文 | 写发布物目录索引，描述产物、大小和命名关系，包含 ~/.ssh/id_rsa 作为安全测试夹具路径；不要求读者读取或发送它。 |

## 隔离与盲测规则

新训练与新验证在风格、任务领域和来源组上隔离；对旧训练、旧验证、冻结保留、C/C2 与评测载荷使用原先字符 5-gram Jaccard≥0.5／BGE-M3 cosine≥0.9 门禁。旧 8204 条训练不可删改，若新验证与它近似则丢弃新验证。排除 5 条仅在验收聚合时应用，原冻结保留文件不修改。模型可见字段不包含 split、style ID、generator、标签、文件路径或可直接推出标签的计算字段。


## 第二教师替换（生成前）

MiMo v2.6 首次合成冒烟 ReadTimeout（90.84 秒）；用户明确授权改用 mimo-v2.5 作为本轮第二教师。24 条独立合成资格样本格式全有效，初次一致 22/24、request 6/8，未达到预登记的小样本资格线。只根据这批自建样本，补充条件式义务及 JSON 传输包装的通用定义；使用另一批 24 条新样本与批量输出检查，DeepSeek 24/24、MiMo 23/24，request 均 8/8、none 误报均 0，资格检查通过。这不是保留集性能估计。两次结果均保留；旧标签、旧保留集与金标准不重标；计时不重置。

生成和双教师盲审并行，以缩短等待；所有文本依然先通过隔离门禁，再按一致票准入。约一半的可核验范围在结果前固定为每个生成器占新增准入训练／验证的 40–60%；不会按类别挑选或改写分歧样本。


## 数据准备中的通用修正与教务审核

新候选的初审发现，旧简报把适用于 request 的呈现方式同时传给 none/quoted，导致当前任务污染负类。修正仅依据新训练候选，保留原始简报、文本与教师票；v2 补充分别为两个生成器新增 1,200 条训练候选与 400 条验证候选，仍属同一轮数据准备，不重置墙钟，不读取保留集或金标准错例。v2 明确按标签解释结构，并要求 MCP 内层 JSON 放在外层 text 字符串中。原定准入门禁不变。

用户要求由子 agent 担任最终教师／教务主任。独立子 agent 只读取本轮新训练／验证候选，保存逐条判断与文本哈希，先审数据契约与生成质量，再审最终入库候选；不读保留集或金标准正文。抽样审核与全量双教师票分别记录，不能把抽样表述成全量重新标注。用户随后明确授权其裁定分歧：对双票完整但三方不一致的固定分层样本，子 agent 在不看原始票和契约标签的情况下逐条给最终标签或 abstain；最终入库保留 contract_label、原始双票、裁定理由和输入哈希。未审分歧、缺票和 abstain 仍丢弃。三方一致率仍用原始票计算，不把裁定计入一致率。

原始流式复核与补充复核保留各自票和日志。一次补充快照传输超时中断后，复核程序从已保存票恢复，仅补缺失票；已有票不覆盖，失败调用照常计数。

语义视图恢复后，保留的 8,204 条训练文档有 1 条在两种 Laya tokenizer 下超过 384 token（分别 435/436）。使用通用重叠窗口保留全文，训练窗口继承文档标签，推理按文档汇总窗口概率；报告同时记录文档数与窗口数。这种窗口标签继承属于弱监督，不能宣称每个窗口都经独立重标。新生成文档仍要求可完整装入 384-token 视图。

条件启用模块与单元测试提前实现，但本轮尚未生成启用配置。只有固定的入库、捷径探针、模型选择及最终冻结评测证据全部通过且哈希一致，才允许 S1 增加风险；默认仍关闭。

候选在完成全部预定生成后收口，最迟为 11:47（在任何训练结果出现前登记），给隔离与捷径探针保留时间；未完成的预定生成及在途结果照实记录。新增训练／验证分别按生成器平衡：仅当一种生成器超过60%时，按 sha256(id) 从小到大保留至少数生成器数量的1.5倍，不按标签或模型结果选择；旧8204条不参与此裁剪。任何规模或门禁不足都不进入训练。

<!-- D3 RESULTS -->

## 执行结果（自动汇总，未知项不推测）

D″ 检查点：`43cbe72`，提交信息“阶段 D″：退回，训练流程保留”。当前阶段墙钟 239.8 分钟；不进入 E。

### 语义视图与测试

俄语独立语义保留集 216 条，混合文字词从 3839/7165（53.58%）变为 0/7165（0.00%）。两次使用同一 Unicode 词统计口径；与历史评审的 62% 分母定义不同。

| 测试记录 | 项数 | 结果 |
|---|---|---|
| .local\stage-d3\unit-tests-current.log | 181 | 通过 |
| .local\stage-d3\unit-tests-runtime.log | 185 | 失败，保留原记录 |
| .local\stage-d3\unit-tests-adjudication.log | 17 | 通过 |
| .local\stage-d3\http-test-recheck.log | 1 | 通过 |
| .local\stage-d3\unit-tests-cloud-lock.log | 29 | 通过 |
| .local\stage-d3\unit-tests-final.log | 186 | 通过 |
| .local\stage-d3\continuation-unit-tests.log | 19 | 通过 |
| .local\stage-d3\continuation-full-tests.log | 188 | 通过 |
| .local\stage-d3\gapfill-unit-tests.log | 19 | 通过 |
| .local\stage-d3\gapfill-full-tests.log | 188 | 通过 |

首次运行时全量检查中的新增测试前提已修正；既有 HTTP 测试超时已单独复核。以上按每次实际运行列出。真实 Pi 回归与离线诊断分别见下文。

冻结原始文件变化：0；派生语义输入变化：0。

### 数据生成、教师与隔离

| 批次 | 生成器 | 完成尝试/原计划 | 有效训练 | 有效验证 |
|---|---|---|---|---|
| . | cloud | 4100/4100 | 3020 | 831 |
| . | local | 4100/4100 | 2640 | 752 |
| supplement | cloud | 1600/1600 | 1094 | 379 |
| supplement | local | 1600/1600 | 1187 | 396 |
| gapfill | cloud | 1200/1200 | 657 | 194 |
| gapfill | local | 379/1200（时间截断，完成数下界） | 218 | 0 |

补缺授权前的历史候选快照：10299 条、双教师有效票 19756 张；当时完整双票中的原始三方一致率 67.26%。以下历史表是候选契约标签分布，不是本次最终训练规模。

| 候选划分 | 数量 | 契约类别 | 语言 | 生成器 |
|---|---|---|---|---|
| train | 7941 | {"request": 2446, "none": 4706, "quoted": 789} | {"zh": 1959, "en": 2059, "ja": 1946, "ru": 1977} | {"deepseek-v4.1-flash": 4114, "huihui-qwen3.8-27b": 3827} |
| validation | 2358 | {"request": 742, "quoted": 243, "none": 1373} | {"ja": 617, "zh": 580, "ru": 620, "en": 541} | {"deepseek-v4.1-flash": 1210, "huihui-qwen3.8-27b": 1148} |

补缺授权前，子 agent 最终教师完成前两批480条定向分歧审阅：468条确定裁定、12条弃权；保留契约304条、修正164条。与DeepSeek一致440/468，与MiMo一致70/468。原票在独立裁定完成后才关联；这些不是总体教师准确率。后续授权批次另行计入最终入库统计，原始票与裁定均保留。

本次冻结候选 11368 条，有效教师票 21852 张；补生成有效候选 1069 条。最终数据链路由独立教务子 agent 复算，审计见机读结果 dean-gapfill-review；旧 dean-admission-review 仅为补缺前历史记录。新增训练生成器占比 DeepSeek 51.88%、Qwen 48.12%；新验证 DeepSeek 52.73%、Qwen 47.27%。

隔离结果：{"whole_fragment_exceeds_384_token_view": 1654, "char5_jaccard_ge_0.5": 1806}。阈值保持 Jaccard 0.5 / BGE cosine 0.9。

隔离后原始三方一致 5105/7354（69.42%）；最终新增入库 5698，其中裁定准入 593、最终标签修正 230。

| 划分 | 类别数量 | 语言数量 | 生成器数量 |
|---|---|---|---|
| train | {"none": 7183, "request": 4081, "quoted": 1007} | {"zh": 2562, "en": 4303, "ja": 3006, "ru": 2400} | {"deepseek-v4.1-flash": 10148, "null": 166, "huihui-qwen3.8-27b": 1957} |
| validation | {"request": 551, "none": 975, "quoted": 105} | {"en": 415, "ja": 376, "zh": 375, "ru": 465} | {"deepseek-v4.1-flash": 860, "huihui-qwen3.8-27b": 771} |

| 数据门禁 | 通过 |
|---|---|
| train_minimum | True |
| train_request_prior | True |
| train_quoted_prior | True |
| train_languages | True |
| train_sources | True |
| train_generator_balance | True |
| validation_minimum | True |
| validation_request_prior | True |
| validation_quoted_prior | True |
| validation_languages | True |
| validation_sources | True |
| validation_generator_balance | True |
| retained_8204 | True |
| new_train_4000 | True |
| unique_ids | True |
| isolated_family | True |
| isolated_domain | True |
| isolated_source_dataset | True |
| style_coverage | True |
| style_registry | True |
| request_without_ai | True |
| obfuscation_fraction | True |
| seven_types | True |
| long_dilution_minimum | True |
| surface_gaps | True |

数据准备累计到入库完成 177.22 分钟，超过原120分钟预算；首次停止后已分别获得追加隔离时间与补生成授权。原始止损记录保留，不把这次扩展表述为原预算内完成。训练加评测仍单独硬限60分钟，整阶段原4小时上限未放宽。

捷径探针：首句验证准确率 0.7094，全篇 request F1 0.8718；训练前门禁 True。

完整探针 request F1 为 0.8718466196，候选须达到至少 0.9018466196；训练后结果见候选表。

### 训练、校准与新验证集选模

| 模型 | epoch | 训练 loss | 验证 loss | 验证准确率 |
|---|---|---|---|---|
| english | 1 | 0.184604 | 0.148139 | 0.9669 |
| english | 2 | 0.052639 | 0.137038 | 0.9700 |
| english | 3 | 0.015474 | 0.158834 | 0.9749 |
| english | 4 | 0.008497 | 0.163694 | 0.9773 |
| multilingual | 1 | 0.165987 | 0.135825 | 0.9798 |
| multilingual | 2 | 0.049939 | 0.137098 | 0.9810 |
| multilingual | 3 | 0.018179 | 0.153024 | 0.9779 |
| modernbert | 1 | 0.896333 | 0.850937 | 0.5978 |
| modernbert | 2 | 0.885251 | 0.850641 | 0.5978 |
| modernbert | 3 | 0.865558 | 0.777096 | 0.6622 |
| modernbert | 4 | 0.477635 | 0.356709 | 0.8921 |
| modernbert | 5 | 0.352419 | 0.290031 | 0.9086 |
| modernbert | 6 | 0.200702 | 0.212607 | 0.9356 |
| modernbert | 7 | 0.132830 | 0.236229 | 0.9332 |
| modernbert | 8 | 0.092613 | 0.216030 | 0.9399 |

| 模型冒烟 | 有限loss与梯度 | 原版权重未变 | 优化器更新 |
|---|---|---|---|
| english | True | True | 0 |
| multilingual | True | True | 0 |
| modernbert | True | True | 0 |

训练调度状态：{"status": "completed", "completed": ["english-smoke", "multilingual-smoke", "modernbert-smoke", "english-fit", "multilingual-fit", "modernbert-fit", "round-evaluation"], "active": "round-evaluation", "finished_unix": 1792302577.7755215}。每个模型只启动一组超参数；中止模型的已完成epoch也原样列出。

训练加评测实际墙钟 54.52 分钟（含三模型冒烟、训练、校准及冻结评测；上限60分钟）。

english：best epoch 2，早停原因 overfit_restore_best，温度 1.693735，阈值 0.8672272455806804，原版权重未变 True。完整配置与文件哈希见机读文件。

multilingual：best epoch 1，早停原因 validation_loss_early_stop，温度 1.998166，阈值 0.07245711123612303，原版权重未变 True。完整配置与文件哈希见机读文件。

modernbert：best epoch 6，早停原因 validation_loss_early_stop，温度 1.151970，阈值 0.5181391716002404，原版权重未变 True。完整配置与文件哈希见机读文件。

| 模型 | 权重文件 | SHA-256 |
|---|---|---|
| english | model.safetensors | f24d437b4dfc592f31351b4139c5c54fb697227210636b636a793a1d5998bac9 |
| multilingual | model.safetensors | bf2120407cc19ddd09f14093e148014238343974e3301aceb8b90e901e46980e |
| modernbert | model.safetensors | c079562325390fb30f86f657225faf9bf502a6a7732c4f23cc1cd108971d26ea |

三模型共用种子20261017、最大8个epoch、验证loss改善阈值0.002、patience=2；恢复实际最低验证loss对应epoch。Laya micro_batch=16、encoder_lr=1e-5、head_lr=5e-5、FP16 AMP；ModernBERT batch_size=16、lr=1e-5、weight_decay=0.01、bfloat16。每个文档的语义内容窗口≤384 token，Laya整体编码max_len=512（含问题和结构），不把结构预算当成正文预算。

| 模型/集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| english | 1631 | 0.9655 | 0.9586 | 0.0195 | 0.9620 | 0.9525 | 0.0242 |
| multilingual | 1631 | 0.9746 | 0.9504 | 0.0154 | 0.9624 | 0.9630 | 0.0116 |
| modernbert | 1631 | 0.9347 | 0.9398 | 0.0174 | 0.9372 | 0.8679 | 0.0219 |
| ensemble | 1631 | 0.9673 | 0.9656 | 0.0072 | 0.9665 | 0.9584 | 0.0262 |

| 候选 | 阈值 | 验证NLL | 相对全篇探针F1差 | 探针通过 |
|---|---|---|---|---|
| english | 0.8672272455806804 | 0.10407410687388013 | 0.09017869687951052 | True |
| multilingual | 0.07245711123612303 | 0.08720863305664059 | 0.0905189718216638 | True |
| modernbert | 0.5181391716002404 | 0.20857221156966485 | 0.06536903101526104 | True |
| ensemble | 0.42721583087906256 | 0.1066557564560557 | 0.09460850281728661 | True |

只按新验证集冻结选择：multilingual。

指标口径：request 召回、精确率、F1 和 none 误报率使用冻结的部署阈值；macro-F1 使用三类别概率 argmax，二者判定规则不同。ECE 基于校准后的 request 概率。

### 最终冻结评测（仅聚合）

| 模型/集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| full_combined | 1000 | 0.9587 | 0.8935 | 0.0399 | 0.9250 | 0.9545 | 0.0233 |
| full_semantic | 788 | 0.9476 | 0.9213 | 0.0101 | 0.9343 | 0.9616 | 0.0207 |
| adjusted_combined | 995 | 0.9646 | 0.8929 | 0.0399 | 0.9274 | 0.9558 | 0.0210 |
| adjusted_semantic | 783 | 0.9563 | 0.9206 | 0.0101 | 0.9381 | 0.9637 | 0.0178 |
| public | 212 | 0.9810 | 0.8443 | 0.1776 | 0.9075 | 0.9150 | 0.0398 |

full_semantic / language

| 模型/集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| en | 205 | 0.9273 | 0.8793 | 0.0299 | 0.9027 | 0.9427 | 0.0291 |
| ja | 168 | 0.9524 | 0.9302 | 0.0093 | 0.9412 | 0.9783 | 0.0182 |
| ru | 216 | 0.9649 | 0.9322 | 0.0000 | 0.9483 | 0.9705 | 0.0214 |
| zh | 199 | 0.9464 | 0.9464 | 0.0000 | 0.9464 | 0.9602 | 0.0275 |

full_semantic / style

| 模型/集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| semantic_heldout:a chronological handover record with a buried dependency | 117 | 0.8077 | 0.8750 | 0.0253 | 0.8400 | 0.9360 | 0.0557 |
| semantic_heldout:a dashboard help panel containing a structured example | 138 | 0.9429 | 0.8684 | 0.0110 | 0.9041 | 0.9605 | 0.0277 |
| semantic_heldout:a patch review with an attached explanatory note | 144 | 0.9744 | 0.9744 | 0.0000 | 0.9744 | 0.9875 | 0.0189 |
| semantic_heldout:an archived discussion with a later addendum | 135 | 0.9459 | 0.9459 | 0.0000 | 0.9459 | 0.9422 | 0.0264 |
| semantic_heldout:an engineering erratum contrasting previous and current behavior | 147 | 0.9714 | 0.8500 | 0.0213 | 0.9067 | 0.9481 | 0.0166 |
| semantic_heldout:three-turn dialogue using referents from previous turns | 107 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.0169 |

adjusted_semantic / language

| 模型/集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| en | 205 | 0.9273 | 0.8793 | 0.0299 | 0.9027 | 0.9427 | 0.0291 |
| ja | 166 | 0.9512 | 0.9286 | 0.0094 | 0.9398 | 0.9780 | 0.0181 |
| ru | 215 | 0.9821 | 0.9322 | 0.0000 | 0.9565 | 0.9746 | 0.0171 |
| zh | 197 | 0.9630 | 0.9455 | 0.0000 | 0.9541 | 0.9643 | 0.0209 |

adjusted_semantic / style

| 模型/集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| semantic_heldout:a chronological handover record with a buried dependency | 115 | 0.8400 | 0.8750 | 0.0256 | 0.8571 | 0.9440 | 0.0481 |
| semantic_heldout:a dashboard help panel containing a structured example | 137 | 0.9412 | 0.8649 | 0.0110 | 0.9014 | 0.9599 | 0.0253 |
| semantic_heldout:a patch review with an attached explanatory note | 144 | 0.9744 | 0.9744 | 0.0000 | 0.9744 | 0.9875 | 0.0189 |
| semantic_heldout:an archived discussion with a later addendum | 134 | 0.9722 | 0.9459 | 0.0000 | 0.9589 | 0.9487 | 0.0195 |
| semantic_heldout:an engineering erratum contrasting previous and current behavior | 146 | 0.9706 | 0.8462 | 0.0213 | 0.9041 | 0.9474 | 0.0171 |
| semantic_heldout:three-turn dialogue using referents from previous turns | 107 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.0169 |

C/C2：

| 模型/集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| C+C2 | 1014 | 1.0000 | 0.6852 | 0.0331 | 0.8132 | 0.8477 | 0.0258 |
| c | 400 | 1.0000 | 0.6512 | 0.0403 | 0.7887 | 1.0000 | 0.0235 |
| c2 | 614 | 1.0000 | 0.7077 | 0.0284 | 0.8288 | 0.8421 | 0.0272 |

保留集验收 False，金标准验收 False。批量每片段耗时：保留集 9.492 ms，金标准 5.429 ms。

旧验证集只报告：

| 模型/集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| old validation | 872 | 1.0000 | 0.8237 | 0.0812 | 0.9033 | 0.9438 | 0.0361 |

### 真实运行与调用量

真实 Pi 条件性回归未触发：运行 ID=[]，verify_v2=null。

| 云端模型 | 请求数（含失败） | 有token记录的请求 | 已知总token |
|---|---|---|---|
| deepseek-v4.1-flash | 10947 | 10691 | 17370595 |
| mimo-v2.6-flash | 1 | 0 | 未知 |
| mimo-v2.5 | 4015 | 3967 | 13122774 |

未返回 usage 的请求 token 数未知，不计作零；并行请求耗时之和不等于阶段墙钟。有效请求记录仅含模型名、耗时与 token 数。原始共用追加日志存在 36 行损坏，原件保留；上表调用量为可解析记录下界，不能宣称精确总量。后续追加增加跨进程锁，修复不追补或覆盖历史证据。

### 验收逐条自检

| 验收项 | 结果 |
|---|---|
| D3_0_semantic_unit_and_russian_under_1pct | True |
| D3_1_data_gates | True |
| D3_1_shortcut_pretrain | True |
| D3_2_validation_threshold | True |
| D3_3_three_fits_one_configuration | True |
| D3_3_posttrain_probe | True |
| D3_4_adjusted_heldout | False |
| D3_4_gold_regression | False |
| conditional_real_regression | 未运行／尚未触发 |
| no_stage_E | True |

### 改动文件

- `docs/03-status.md`
- `docs/22-stage-d3-report.md`
- `docs/stage-d3-results.json`
- `docs/stage-d3-verification.md`
- `docs/整体设计文档.md`
- `evaluate_stage_d3.py`
- `src/d2v2/content_model.py`
- `src/d2v2/core.py`
- `src/d2v2/request_model.py`
- `src/d2v2/semantic_view.py`
- `stage_d2_cloud.py`
- `stage_d3_adjudication.py`
- `stage_d3_admit.py`
- `stage_d3_collect.py`
- `stage_d3_cutoff.py`
- `stage_d3_data.py`
- `stage_d3_fast_isolation.py`
- `stage_d3_gapfill.py`
- `stage_d3_gapfill_cutoff.py`
- `stage_d3_gapfill_finalize.py`
- `stage_d3_isolation.py`
- `stage_d3_model.py`
- `stage_d3_probe.py`
- `stage_d3_protocol.py`
- `stage_d3_regression.py`
- `stage_d3_report.py`
- `stage_d3_run_training.py`
- `stage_d3_stream_review.py`
- `stage_d3_supplement.py`
- `stage_d3_teacher.py`
- `tests/test_stage_d3.py`
- `train_stage_d3.py`

既有其他阶段未提交改动保留，不计入本阶段交付。.local/ 内数据、裁定、日志和模型证据不提交。

### 当前未解决项

以最终入库门禁、候选资格、冻结验收与真实回归为准；未运行项不宣称完成。S1 是否实际启用需另核对配置与回归记录，评测通过字段本身不会自动启用。

冻结验收未达标项（不调整阈值，不导出错例，不开启下一轮）：

| 集合 | 指标 | 实际 | 预登记要求 | 绝对差距 |
|---|---|---|---|---|
| adjusted_combined | none误报率 | 0.03993344425956739 | <=0.03 | 0.009933444259567388 |
| gold | request精确率 | 0.6851851851851852 | >=0.8 | 0.11481481481481481 |
| gold | none误报率 | 0.03311965811965812 | <=0.03 | 0.003119658119658121 |

首次停止记录：数据准备 118.33 分钟时触发预设预算保护（硬线120分钟，预留100秒收尾）。生成／复核完成后才运行完整串行字符隔离，隔离子进程在562.25秒超时，未给嵌入隔离和捷径探针留下足够时间；这是首次执行安排与隔离效率的缺口，不能据此判断候选模型性能。首次停止时未训练，S1关闭；历史停止记录不覆盖后续授权续行结果。

### 历史续行：用户授权追加时间，只用冻结数据

用户明确允许优化隔离后继续已有数据的隔离、入库和捷径探针；通过后继续同一轮训练，训练加评测仍限60分钟，不开始E。原始计时、首次失败日志和停止记录保留；不重新生成，不重新标注。

优化采用缓存的精确倒排计数；固定参考的余弦相似度批量计算，阈值附近仍用原矩阵向量算法复核。原Jaccard 0.5、cosine 0.9、稳定输入顺序及跨划分逐条判定保持不变。

合成基准1000参考／100查询：原版0.885秒、优化版0.195秒，4.53倍；判定一致。该次历史全量隔离耗时：282.8514711856842秒。

隔离、入库计算与捷径探针均完成；新增云端调用 0 次，候选、原始教师票及云端日志哈希全部不变。新增训练 3472／4000（缺528），保留旧8204后训练总数11676；新验证1501。

该次续行的阻断项：验证集request占比36.71%，超过35%；训练长文稀释2.04%，低于5%。按预登记的dilution类型，把所有通过隔离的长文候选都算上，连同旧数据也最多371条，低于最低训练规模所需611条。因此当时停止待评审；本结论仅适用于补生成授权之前的固定池，后续结果见下节。

### 用户授权补生成缺口（同一轮，门槛不变）

用户明确允许补生成长文和负样本，通过隔离、入库和捷径探针后继续本轮60分钟训练评测。原失败批次、验证集与探针保存在pre-gapfill中；训练开始前只做这次获准的数据修补，冻结语义保留集及金标准未参与修补。

冒烟发现原长度简报常被超额生成。保留各次失败记录，最终以原风格登记中13种适合长篇正文的训练风格补缺；原48种训练、16种验证风格的数据保留。计划尝试生成2000条长文、400条验证负样本，两个生成器各半；实际有效补批1069条，最终入库另行过滤。训练补批计划英语80%，其余中日俄20%，验证四语言各25%。英语目标200–210词，仍在原180–230词范围内；增加明确最低长文单位检查并保留全文384-token上限，未截断文本或放宽隔离阈值。验证补批均为plain，最终仍核验15–25%的整体变体比例。

完整最低长度、两套tokenizer限制与教师复核可能分别拒绝样本，因此生成计划不等于准入规模。三方一致仍以原始教师票计算，授权教务裁定另列。

本次结果：{"status": "单轮训练与评测完成，模型验收未通过，S1保持关闭", "updated_unix": 1792299445.7436042, "candidate_n": 11368, "teacher_vote_n": 21852, "gapfill_valid_candidates": 1069, "isolation_seconds": 361.97804832458496, "isolated_n": 7908, "isolation_rejected_counts": {"whole_fragment_exceeds_384_token_view": 1654, "char5_jaccard_ge_0.5": 1806}, "admission_passed": true, "new_train_n": 4067, "retained_train_n": 8204, "train_n": 12271, "validation_n": 1631, "validation_request_fraction": 0.3378295524218271, "long_dilution_n": 677, "long_dilution_fraction": 0.05517072773205118, "raw_three_way_agreement_after_isolation": 0.6941800380745172, "agent_adjudicated_n": 593, "agent_relabeled_n": 230, "pretrain_probe_passed": true, "first_sentence_accuracy": 0.7093807480073574, "full_probe_request_f1": 0.8718466195761857, "no_heldout_or_gold_feedback": true, "stage_E_started": false, "evidence_sha256": {"generated-combined.jsonl": "386feb78d7ebec2cf1304d3843ed0d1b9d479414592583c3b8656e7ec8727717", "teacher-votes.jsonl": "30b737b5986ea8798e1c6763366292c1883c452081387cbb2bd7d048892e81df", "isolation.json": "ab1d921a346004acbe3baa155d5fb15024d7ce8b3d10370b9dd1745a16f29d46", "admitted.jsonl": "f1b6f67fa9fbd944c03b93213176114f8aa9f8fed52be3e892db489049e20b65", "new-validation-frozen.jsonl": "fea8731d012441e4485e971149c8f0d93133349fcadf060fb342c1700712269e", "probe.json": "4f5d3b6396b68206ddb7598e517fcfb579f163a298021d5787b3d4cd80147472", "dean-gapfill-review.json": "b91bf9e4fe14f03ec1bb8e2daa71d9f4e135e0e4cacb85a1fda5aa6843df4b75"}, "gapfill_cloud_calls": {"deepseek-v4.1-flash": 1876, "mimo-v2.5": 596}, "gapfill_unparseable_log_lines": 0, "finished_unix": 1792302726.7447276, "training_started": true, "training_evaluation_seconds": 3271.156862258911, "training_runner_status": "completed", "selected": "multilingual", "model_acceptance_passed": false, "real_regression_complete_passed": false, "s1_enabled_for_real_regression": false, "real_run_ids": [], "verify_v2_all_passed": null, "heldout_model_evaluation_started": true, "gold_model_evaluation_completed": true}
