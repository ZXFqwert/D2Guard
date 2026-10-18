# 阶段 D⁗：S1 阈值与真实环境验收

状态：**阶段D⁗未通过真实良性集门槛；S1关闭，真实回归未启动，停止等待评审**。只做D⁗，不重训、不新增训练数据、不开始E。

## 预登记计划与差异

顺序：D‴检查点→冻结模型与温度→只在D‴新验证集定阈值→真实来源及沙箱命令冒烟→双教师一致入库和盲标包→一次聚合评测→离线轨迹重算→真实Pi冒烟和68轮配对回归。阶段墙钟上限2小时。

检查点 `935c2cd`，提交信息“阶段 D‴：模型通过，阈值退回”；不含.local。已有其他阶段未提交文件保留。

本阶段明确授权公开真实文本复核，覆盖旧设计“只发送合成文本”的限制。用户后续取消许可证阻塞门禁，仍保留来源、固定提交与已识别许可证信息。MCP按独立服务器身份计数，SDK示例不计入；未启动上游服务器，描述来自实际工具注册的字面量/docstring，仅投影name/description，不捏造inputSchema。长描述按语义窗口切片。

命令采集原计划含Git日志；算力机GitHub读取缓慢，保留失败记录，改为本机固定提交后上传公开文件，在bubblewrap无网络、只读挂载沙箱运行文档/JSON单测、只读语法索引、sha256sum、du。没有执行项目安装脚本或导入下载的代码。

初始148次命令，加数量补集37次，共185次实际命令，4次非零退出原样保留；去重后按不同command_id核验至少100次。采集端关闭tokenizer JSON持久化截断和padding，再按384-token语义视图切片；发现截断时尚未正式标注/评测，最终冻结数据重新完整采集。

正式调用前双教师三个类别冒烟通过。正式标注只要求DeepSeek与MiMo一致，不使用前阶段的子agent裁定。截断和非法JSON视为无效票，不补猜、不重试；中断队列的保守前缀缺票排除，剩余未尝试候选继续。单次5xx或读取超时仅排除该批；同一教师连续3次此类失败视为服务阻塞并停止，401/403/模型身份不符直接停止。没有重试已尝试批次。

## 阈值与验证指标

模型权重SHA-256：`bf2120407cc19ddd09f14093e148014238343974e3301aceb8b90e901e46980e`。温度保留完整精度 `1.9981657266616821`，显示值1.998166；不重新拟合。阈值 **0.5**。

| 集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| D‴新验证集 | 1631 | 0.9619 | 0.9888 | 0.0031 | 0.9752 | 0.9630 | 0.0116 |

与评审参考0.5 / 召回0.9619 / 精确率0.9888 / none误报率0.31%一致，差异仅为显示四舍五入。request指标使用冻结阈值，macro-F1使用三类argmax，ECE基于校准后request概率。

## 真实良性集来源与规模

候选冻结：{"n": 1911, "categories": {"documentation": 1400, "mcp": 330, "command": 181}, "distinct_servers": 108, "distinct_commands": 117, "actual_commands_executed": 148, "nonzero_command_exits": 4, "sha256": "44d126e35c4356d5069a17e827918b18605dc50f0b6565886a1f176556761324", "selection": "deterministic file order and first slices, before teacher votes or model predictions"}

数量补集：{"n": 891, "category": {"documentation": 563, "mcp": 290, "command": 38}, "original_candidate_n": 1911, "union_candidate_n": 2802, "sha256": "24922cc8f2ca030f094309819433dcbfa4c4b90ff5c2e4d0f86129ad7ed209b4", "basis": "Only missing admission counts: initial docs486<600, distinct servers94<100. No classifier predictions or evaluation results available. All initial valid agreements retained; no previous fragment rejudged. Additional actual wc output commands37."}

最终一致入库：{"passed": true, "candidate_n": 2802, "fully_reviewed_n": 2004, "missing_votes_n": 798, "admitted_n": 1293, "agreement_rate": 0.6452095808383234, "disagreement_n": 711, "category": {"documentation": 707, "mcp": 387, "command": 199}, "label": {"none": 1160, "request": 133}, "repository_n": 36, "distinct_mcp_servers": 112, "distinct_command_outputs": 139, "benign_sha256": "876214466918df991c8878772c008961dc6d51a4150c27fc0a63431a8bfde521", "blind_sha256": "95d98659bd376839bd875102c7d544c26e2c32629a4c5fde8d43eff273882a06", "language_annotation": "Not annotated for real-source data; und replaces a collection placeholder. Language is not a model input.", "distribution": {"repository": {"Textualize/rich": 28, "Textualize/textual": 17, "encode/starlette": 27, "fastapi/fastapi": 24, "fastapi/typer": 27, "networkx/networkx": 41, "numpy/numpy": 45, "pallets-eco/blinker": 7, "pallets/itsdangerous": 9, "pallets/jinja": 9, "pallets/markupsafe": 8, "psf/requests": 11, "pydantic/pydantic": 43, "pygments/pygments": 16, "pypa/build": 23, "pypa/flit": 12, "pypa/hatch": 24, "pypa/installer": 23, "pypa/packaging": 34, "pypa/virtualenv": 30, "pypa/wheel": 23, "pytest-dev/pluggy": 14, "pytest-dev/pytest": 39, "python-attrs/attrs": 27, "python-attrs/cattrs": 20, "python-jsonschema/jsonschema": 19, "python-trio/trio": 17, "scikit-learn/scikit-learn": 30, "scipy/scipy": 41, "sphinx-doc/sphinx": 48, "sqlalchemy/sqlalchemy": 50, "sympy/sympy": 42, "urllib3/urllib3": 37, "ChromeDevTools/chrome-devtools-mcp": 6, "Flux159/mcp-server-kubernetes": 6, "GongRzhe/Gmail-MCP-Server": 6, "GongRzhe/Office-Word-MCP-Server": 6, "alexander-zuev/supabase-mcp-server": 4, "antvis/mcp-server-chart": 4, "awslabs/mcp": 176, "cloudflare/mcp-server-cloudflare": 39, "containers/kubernetes-mcp-server": 6, "crystaldba/postgres-mcp": 6, "executeautomation/mcp-playwright": 4, "github/github-mcp-server": 4, "isaacphi/mcp-gdrive": 3, "modelcontextprotocol/servers-archived": 41, "modelcontextprotocol/servers": 8, "neo4j-contrib/mcp-neo4j": 16, "nickclyde/duckduckgo-mcp-server": 3, "octagonai/octagon-mcp-server": 4, "redis/mcp-redis": 2, "sooperset/mcp-atlassian": 2, "stripe/agent-toolkit": 5, "supabase-community/supabase-mcp": 1, "tavily-ai/tavily-mcp": 3, "upstash/context7": 2, "zcaceres/fetch-mcp": 6, "encode/httpx": 12, "pandas-dev/pandas": 4, "agronholm/anyio": 11, "pallets/werkzeug": 14, "benborla/mcp-server-mysql": 3, "blazickjp/arxiv-mcp-server": 2, "browserbase/mcp-server-browserbase": 2, "designcomputer/mysql_mcp_server": 1, "domdomegg/airtable-mcp-server": 1, "exa-labs/exa-mcp-server": 1, "getsentry/sentry-mcp": 2, "grafana/mcp-grafana": 3, "jina-ai/MCP": 3, "microsoft/markitdown": 1, "pydantic/logfire-mcp": 3, "rusiaaman/wcgw": 2}, "document_kind": {"api_docs": 527, "issue_template": 4, "readme": 76, "changelog": 77, "contributing": 18, "pull_request_template": 5, "not_documentation": 586}, "category_labels": {"documentation": {"none": 612, "request": 95}, "mcp": {"none": 349, "request": 38}, "command": {"none": 199}}, "server": {"ChromeDevTools/chrome-devtools-mcp": 6, "Flux159/mcp-server-kubernetes": 6, "GongRzhe/Gmail-MCP-Server": 6, "GongRzhe/Office-Word-MCP-Server": 6, "alexander-zuev/supabase-mcp-server": 4, "antvis/mcp-server-chart": 4, "awslabs/mcp/amazon-kendra-index-mcp-server": 1, "awslabs/mcp/amazon-keyspaces-mcp-server": 3, "awslabs/mcp/amazon-mq-mcp-server": 6, "awslabs/mcp/amazon-neptune-mcp-server": 3, "awslabs/mcp/amazon-qbusiness-anonymous-mcp-server": 1, "awslabs/mcp/amazon-qindex-mcp-server": 5, "awslabs/mcp/amazon-translate-mcp-server": 6, "awslabs/mcp/aurora-dsql-mcp-server": 7, "awslabs/mcp/aws-appsync-mcp-server": 3, "awslabs/mcp/aws-dataprocessing-mcp-server": 3, "awslabs/mcp/aws-documentation-mcp-server": 2, "awslabs/mcp/aws-for-sap-management-mcp-server": 5, "awslabs/mcp/aws-healthomics-mcp-server": 1, "awslabs/mcp/aws-iac-mcp-server": 6, "awslabs/mcp/aws-location-mcp-server": 5, "awslabs/mcp/aws-pricing-mcp-server": 2, "awslabs/mcp/aws-serverless-mcp-server": 1, "awslabs/mcp/aws-support-mcp-server": 4, "awslabs/mcp/billing-cost-management-mcp-server": 2, "awslabs/mcp/ccapi-mcp-server": 4, "awslabs/mcp/document-loader-mcp-server": 2, "awslabs/mcp/dynamodb-mcp-server": 4, "awslabs/mcp/ecs-mcp-server": 6, "awslabs/mcp/eks-mcp-server": 3, "awslabs/mcp/elasticache-mcp-server": 3, "awslabs/mcp/finch-mcp-server": 4, "awslabs/mcp/healthimaging-mcp-server": 6, "awslabs/mcp/healthlake-mcp-server": 6, "awslabs/mcp/iam-mcp-server": 3, "awslabs/mcp/lambda-tool-mcp-server": 1, "awslabs/mcp/memcached-mcp-server": 3, "awslabs/mcp/mssql-mcp-server": 4, "awslabs/mcp/mysql-mcp-server": 4, "awslabs/mcp/oracle-mcp-server": 3, "awslabs/mcp/postgres-mcp-server": 2, "awslabs/mcp/prometheus-mcp-server": 3, "awslabs/mcp/roda-mcp-server": 5, "awslabs/mcp/s3-tables-mcp-server": 2, "awslabs/mcp/sagemaker-ai-mcp-server": 10, "awslabs/mcp/security-agent-mcp-server": 5, "awslabs/mcp/stepfunctions-tool-mcp-server": 1, "awslabs/mcp/timestream-for-influxdb-mcp-server": 6, "awslabs/mcp/valkey-mcp-server": 5, "awslabs/mcp/well-architected-security-mcp-server": 4, "cloudflare/mcp-server-cloudflare/ai-gateway": 3, "cloudflare/mcp-server-cloudflare/auditlogs": 1, "cloudflare/mcp-server-cloudflare/autorag": 3, "cloudflare/mcp-server-cloudflare/browser-rendering": 6, "cloudflare/mcp-server-cloudflare/cloudflare-one-casb": 6, "cloudflare/mcp-server-cloudflare/dex-analysis": 4, "cloudflare/mcp-server-cloudflare/dns-analytics": 3, "cloudflare/mcp-server-cloudflare/graphql": 3, "cloudflare/mcp-server-cloudflare/workers-bindings": 4, "cloudflare/mcp-server-cloudflare/workers-builds": 1, "cloudflare/mcp-server-cloudflare/workers-observability": 1, "containers/kubernetes-mcp-server": 6, "crystaldba/postgres-mcp": 6, "executeautomation/mcp-playwright": 4, "github/github-mcp-server": 4, "isaacphi/mcp-gdrive": 3, "modelcontextprotocol/servers-archived/aws-kb-retrieval-server": 1, "modelcontextprotocol/servers-archived/brave-search": 2, "modelcontextprotocol/servers-archived/everart": 1, "modelcontextprotocol/servers-archived/gdrive": 1, "modelcontextprotocol/servers-archived/github": 6, "modelcontextprotocol/servers-archived/gitlab": 3, "modelcontextprotocol/servers-archived/google-maps": 3, "modelcontextprotocol/servers-archived/postgres": 1, "modelcontextprotocol/servers-archived/puppeteer": 6, "modelcontextprotocol/servers-archived/redis": 4, "modelcontextprotocol/servers-archived/sentry": 1, "modelcontextprotocol/servers-archived/slack": 6, "modelcontextprotocol/servers-archived/sqlite": 6, "modelcontextprotocol/servers/fetch": 1, "modelcontextprotocol/servers/filesystem": 4, "neo4j-contrib/mcp-neo4j/mcp-neo4j-cloud-aura-api": 6, "neo4j-contrib/mcp-neo4j/mcp-neo4j-cypher": 2, "neo4j-contrib/mcp-neo4j/mcp-neo4j-data-modeling": 5, "neo4j-contrib/mcp-neo4j/mcp-neo4j-memory": 3, "nickclyde/duckduckgo-mcp-server": 3, "octagonai/octagon-mcp-server": 4, "redis/mcp-redis": 2, "sooperset/mcp-atlassian": 2, "stripe/agent-toolkit": 5, "supabase-community/supabase-mcp": 1, "tavily-ai/tavily-mcp": 3, "upstash/context7": 2, "zcaceres/fetch-mcp": 6, "awslabs/mcp/cloudtrail-mcp-server": 6, "awslabs/mcp/cloudwatch-applicationsignals-mcp-server": 2, "awslabs/mcp/redshift-mcp-server": 3, "benborla/mcp-server-mysql": 3, "blazickjp/arxiv-mcp-server": 2, "browserbase/mcp-server-browserbase": 2, "cloudflare/mcp-server-cloudflare/cloudflare-blog": 1, "cloudflare/mcp-server-cloudflare/radar": 3, "designcomputer/mysql_mcp_server": 1, "domdomegg/airtable-mcp-server": 1, "exa-labs/exa-mcp-server": 1, "getsentry/sentry-mcp": 2, "grafana/mcp-grafana": 3, "jina-ai/MCP": 3, "microsoft/markitdown": 1, "modelcontextprotocol/servers/memory": 3, "pydantic/logfire-mcp": 3, "rusiaaman/wcgw": 2}}}

| 文档仓库 | 提交 | 许可证记录 | 候选片段 |
|---|---|---|---|
| [Textualize/rich](https://github.com/Textualize/rich/tree/9d8f9a372cc5916fd4781fec207ced7ddac2f08f) | 9d8f9a372cc5916fd4781fec207ced7ddac2f08f | MIT | 74 |
| [Textualize/textual](https://github.com/Textualize/textual/tree/5e5b7ef58b8c5572c13a3ff9027d756623661495) | 5e5b7ef58b8c5572c13a3ff9027d756623661495 | MIT | 71 |
| [agronholm/anyio](https://github.com/agronholm/anyio/tree/633965bad02a857574b3dbad03d1ef9f35e9caa4) | 633965bad02a857574b3dbad03d1ef9f35e9caa4 | MIT | 73 |
| [encode/httpx](https://github.com/encode/httpx/tree/b5addb64f0161ff6bfe94c124ef76f6a1fba5254) | b5addb64f0161ff6bfe94c124ef76f6a1fba5254 | BSD-3-Clause | 69 |
| [encode/starlette](https://github.com/encode/starlette/tree/b7901fb908f0c6c3b8b6e495517cea6b2e77e66b) | b7901fb908f0c6c3b8b6e495517cea6b2e77e66b | BSD-3-Clause | 66 |
| [fastapi/fastapi](https://github.com/fastapi/fastapi/tree/b23d78f2ce4e7b3ea48a59f51ca249690d9fd02c) | b23d78f2ce4e7b3ea48a59f51ca249690d9fd02c | MIT | 62 |
| [fastapi/typer](https://github.com/fastapi/typer/tree/a5882dedf0bc7a46cd861fdfca020f88519e0f21) | a5882dedf0bc7a46cd861fdfca020f88519e0f21 | MIT | 60 |
| [networkx/networkx](https://github.com/networkx/networkx/tree/abf2feda2252ee4e0d5a66964addf179225dfe76) | abf2feda2252ee4e0d5a66964addf179225dfe76 | BSD-3-Clause | 72 |
| [numpy/numpy](https://github.com/numpy/numpy/tree/7ed6cf76b27d66e6354f8d6cedafd1e06cda741e) | 7ed6cf76b27d66e6354f8d6cedafd1e06cda741e | BSD-3-Clause | 75 |
| [pallets-eco/blinker](https://github.com/pallets-eco/blinker/tree/c3364059663df1ddce32799d6b1922af89a345f6) | c3364059663df1ddce32799d6b1922af89a345f6 | MIT | 7 |
| [pallets/itsdangerous](https://github.com/pallets/itsdangerous/tree/672971d66a2ef9f85151e53283113f33d642dabd) | 672971d66a2ef9f85151e53283113f33d642dabd | BSD-3-Clause | 20 |
| [pallets/jinja](https://github.com/pallets/jinja/tree/5ef70112a1ff19c05324ff889dd30405b1002044) | 5ef70112a1ff19c05324ff889dd30405b1002044 | BSD-3-Clause | 33 |
| [pallets/markupsafe](https://github.com/pallets/markupsafe/tree/4e111271b1494995708a9e878a10829b5e10c7ba) | 4e111271b1494995708a9e878a10829b5e10c7ba | BSD-3-Clause | 13 |
| [pallets/werkzeug](https://github.com/pallets/werkzeug/tree/665e760ca6325a348ce03e5cf780b17e4be01848) | 665e760ca6325a348ce03e5cf780b17e4be01848 | BSD-3-Clause | 65 |
| [pandas-dev/pandas](https://github.com/pandas-dev/pandas/tree/910ef5492e6be9052ff6dfbcc15cd1f2c80caeb3) | 910ef5492e6be9052ff6dfbcc15cd1f2c80caeb3 | BSD-3-Clause | 3 |
| [psf/requests](https://github.com/psf/requests/tree/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60) | 611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60 | Apache-2.0 | 44 |
| [pydantic/pydantic](https://github.com/pydantic/pydantic/tree/5adfeaaaea947f81f0f01868604f219084ec151a) | 5adfeaaaea947f81f0f01868604f219084ec151a | MIT | 73 |
| [pygments/pygments](https://github.com/pygments/pygments/tree/156d85fdd18d34427fe893527e71da91dcfb0eb5) | 156d85fdd18d34427fe893527e71da91dcfb0eb5 | BSD-2-Clause | 61 |
| [pypa/build](https://github.com/pypa/build/tree/a1887073399bc1d92a0e94bf1650524f983b5574) | a1887073399bc1d92a0e94bf1650524f983b5574 | MIT | 72 |
| [pypa/flit](https://github.com/pypa/flit/tree/75b1c909d587c1ff5e0fd5f3df1046f74ee249d4) | 75b1c909d587c1ff5e0fd5f3df1046f74ee249d4 | BSD-3-Clause | 27 |
| [pypa/hatch](https://github.com/pypa/hatch/tree/ac9c0c9544795b380c2a5f63f80c1f46db3c5d4c) | ac9c0c9544795b380c2a5f63f80c1f46db3c5d4c | MIT | 63 |
| [pypa/installer](https://github.com/pypa/installer/tree/9b7fd286b85c5091390d4368709c46b35693b28c) | 9b7fd286b85c5091390d4368709c46b35693b28c | MIT | 24 |
| [pypa/packaging](https://github.com/pypa/packaging/tree/ef837aad3127167671eb37b9f6bd8a94ec7ce26e) | ef837aad3127167671eb37b9f6bd8a94ec7ce26e | Apache-2.0, BSD-2-Clause | 48 |
| [pypa/virtualenv](https://github.com/pypa/virtualenv/tree/8a7de0a40461d3d6dc01aa260137d394432e7da0) | 8a7de0a40461d3d6dc01aa260137d394432e7da0 | MIT | 58 |
| [pypa/wheel](https://github.com/pypa/wheel/tree/4ae6d07d38611cb0619864621c06fc032622eaef) | 4ae6d07d38611cb0619864621c06fc032622eaef | MIT | 25 |
| [pytest-dev/pluggy](https://github.com/pytest-dev/pluggy/tree/09fabb162b8f84af0292b827c94e0149b82d448a) | 09fabb162b8f84af0292b827c94e0149b82d448a | MIT | 18 |
| [pytest-dev/pytest](https://github.com/pytest-dev/pytest/tree/420cf37a3fc8c03c9a4769c2635a03773d27be10) | 420cf37a3fc8c03c9a4769c2635a03773d27be10 | MIT | 72 |
| [python-attrs/attrs](https://github.com/python-attrs/attrs/tree/ee66e7274852438cc23d4240a1a9cd632fda8b52) | ee66e7274852438cc23d4240a1a9cd632fda8b52 | MIT | 61 |
| [python-attrs/cattrs](https://github.com/python-attrs/cattrs/tree/73fa273b1239fc5c110c4f9b6674972284a2f456) | 73fa273b1239fc5c110c4f9b6674972284a2f456 | MIT | 51 |
| [python-jsonschema/jsonschema](https://github.com/python-jsonschema/jsonschema/tree/c497561ea0a95f5aac09cd63d15eb1420eb7bbec) | c497561ea0a95f5aac09cd63d15eb1420eb7bbec | MIT | 40 |
| [python-trio/trio](https://github.com/python-trio/trio/tree/4630d02872c0aa5778ce0afd702c5d532a2ccf60) | 4630d02872c0aa5778ce0afd702c5d532a2ccf60 | Apache-2.0, MIT | 46 |
| [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn/tree/85593ca7a07a9956ac891f6bfc3fedca53b74f72) | 85593ca7a07a9956ac891f6bfc3fedca53b74f72 | BSD-3-Clause | 72 |
| [scipy/scipy](https://github.com/scipy/scipy/tree/e1a7f5e4239c32a0415c3368f7969b93feddfee2) | e1a7f5e4239c32a0415c3368f7969b93feddfee2 | BSD-3-Clause, BSD-3-Clause | 72 |
| [sphinx-doc/sphinx](https://github.com/sphinx-doc/sphinx/tree/b04a2101295ac3fb725b16111eda0284b6da4cca) | b04a2101295ac3fb725b16111eda0284b6da4cca | BSD-2-Clause | 64 |
| [sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy/tree/7b95e267c867f9e35ee0aba7e637f373522b0e1d) | 7b95e267c867f9e35ee0aba7e637f373522b0e1d | MIT | 73 |
| [sympy/sympy](https://github.com/sympy/sympy/tree/50e68debd256f0ff52b1856bba54868e5499448e) | 50e68debd256f0ff52b1856bba54868e5499448e | MIT | 74 |
| [urllib3/urllib3](https://github.com/urllib3/urllib3/tree/a37bc93b65d6bcf00d3dc43d966bab6bd130ecd8) | a37bc93b65d6bcf00d3dc43d966bab6bd130ecd8 | MIT | 62 |

| 独立MCP服务器 | 提交 | 许可证记录 | 候选片段 |
|---|---|---|---|
| [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp/tree/2777fa05b296cdb51507e6fd33ae05c06fe0b9e7) | 2777fa05b296cdb51507e6fd33ae05c06fe0b9e7 | Apache-2.0 | 6 |
| [Flux159/mcp-server-kubernetes](https://github.com/Flux159/mcp-server-kubernetes/tree/b2e82de34b00a8de2103a6561843b9a8c73f3599) | b2e82de34b00a8de2103a6561843b9a8c73f3599 | MIT | 6 |
| [GongRzhe/Gmail-MCP-Server](https://github.com/GongRzhe/Gmail-MCP-Server/tree/a890d19189bbc1325b8728fab830fc278cfd8804) | a890d19189bbc1325b8728fab830fc278cfd8804 | MIT | 6 |
| [GongRzhe/Office-Word-MCP-Server](https://github.com/GongRzhe/Office-Word-MCP-Server/tree/a3bbbb6d6167e68cf855d73ef7dc6cd8cfbfedba) | a3bbbb6d6167e68cf855d73ef7dc6cd8cfbfedba | MIT | 6 |
| [alexander-zuev/supabase-mcp-server](https://github.com/alexander-zuev/supabase-mcp-server/tree/bca07008fe46cae791221c2ee30df034c963ec56) | bca07008fe46cae791221c2ee30df034c963ec56 | Apache-2.0 | 6 |
| [antvis/mcp-server-chart](https://github.com/antvis/mcp-server-chart/tree/e2a8fb7c185e17c75c067817ff1a2acfddf49aa1) | e2a8fb7c185e17c75c067817ff1a2acfddf49aa1 | MIT | 6 |
| [awslabs/mcp/amazon-bedrock-agentcore-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/amazon-kendra-index-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 2 |
| [awslabs/mcp/amazon-keyspaces-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/amazon-mq-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/amazon-neptune-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 4 |
| [awslabs/mcp/amazon-qbusiness-anonymous-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 1 |
| [awslabs/mcp/amazon-qindex-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 8 |
| [awslabs/mcp/amazon-translate-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/aurora-dsql-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 8 |
| [awslabs/mcp/aws-api-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 3 |
| [awslabs/mcp/aws-appsync-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/aws-dataprocessing-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 8 |
| [awslabs/mcp/aws-documentation-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 7 |
| [awslabs/mcp/aws-for-sap-management-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/aws-healthomics-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 1 |
| [awslabs/mcp/aws-iac-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 8 |
| [awslabs/mcp/aws-location-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/aws-pricing-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 19 |
| [awslabs/mcp/aws-serverless-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/aws-support-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 7 |
| [awslabs/mcp/bedrock-kb-retrieval-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 5 |
| [awslabs/mcp/billing-cost-management-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 7 |
| [awslabs/mcp/ccapi-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 8 |
| [awslabs/mcp/cloudtrail-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 11 |
| [awslabs/mcp/cloudwatch-applicationsignals-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 10 |
| [awslabs/mcp/cloudwatch-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 8 |
| [awslabs/mcp/document-loader-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 3 |
| [awslabs/mcp/dynamodb-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 9 |
| [awslabs/mcp/ecs-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 7 |
| [awslabs/mcp/eks-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 9 |
| [awslabs/mcp/elasticache-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/finch-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 4 |
| [awslabs/mcp/healthimaging-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/healthlake-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/iam-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/lambda-tool-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 1 |
| [awslabs/mcp/memcached-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/mssql-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 4 |
| [awslabs/mcp/mysql-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 5 |
| [awslabs/mcp/oracle-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 4 |
| [awslabs/mcp/postgres-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 3 |
| [awslabs/mcp/prometheus-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 7 |
| [awslabs/mcp/redshift-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 8 |
| [awslabs/mcp/roda-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/s3-tables-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 15 |
| [awslabs/mcp/sagemaker-ai-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 18 |
| [awslabs/mcp/security-agent-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 7 |
| [awslabs/mcp/stepfunctions-tool-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 1 |
| [awslabs/mcp/timestream-for-influxdb-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [awslabs/mcp/valkey-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 7 |
| [awslabs/mcp/well-architected-security-mcp-server](https://github.com/awslabs/mcp/tree/d534d0fa3c06838336ac1ed64e7114db0ba85e6f) | d534d0fa3c06838336ac1ed64e7114db0ba85e6f | Apache-2.0 | 6 |
| [browserbase/mcp-server-browserbase](https://github.com/browserbase/mcp-server-browserbase/tree/3e6f53461949037d5e65dd425da3ceb1263f11d6) | 3e6f53461949037d5e65dd425da3ceb1263f11d6 | Apache-2.0 | 5 |
| [cloudflare/mcp-server-cloudflare/ai-gateway](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 3 |
| [cloudflare/mcp-server-cloudflare/auditlogs](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 1 |
| [cloudflare/mcp-server-cloudflare/autorag](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 3 |
| [cloudflare/mcp-server-cloudflare/browser-rendering](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 6 |
| [cloudflare/mcp-server-cloudflare/cloudflare-blog](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 4 |
| [cloudflare/mcp-server-cloudflare/cloudflare-one-casb](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 6 |
| [cloudflare/mcp-server-cloudflare/dex-analysis](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 6 |
| [cloudflare/mcp-server-cloudflare/dns-analytics](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 3 |
| [cloudflare/mcp-server-cloudflare/graphql](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 7 |
| [cloudflare/mcp-server-cloudflare/logpush](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 1 |
| [cloudflare/mcp-server-cloudflare/radar](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 6 |
| [cloudflare/mcp-server-cloudflare/workers-bindings](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 6 |
| [cloudflare/mcp-server-cloudflare/workers-builds](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 1 |
| [cloudflare/mcp-server-cloudflare/workers-observability](https://github.com/cloudflare/mcp-server-cloudflare/tree/e4cf085520ea7286af77abf938d645c610ef1580) | e4cf085520ea7286af77abf938d645c610ef1580 | Apache-2.0 | 4 |
| [containers/kubernetes-mcp-server](https://github.com/containers/kubernetes-mcp-server/tree/970df6a7169c943fc0c82641fde6eed38f1e153c) | 970df6a7169c943fc0c82641fde6eed38f1e153c | Apache-2.0 | 6 |
| [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp/tree/15c8e33353546148acc2d8bd784551cf3905d1e2) | 15c8e33353546148acc2d8bd784551cf3905d1e2 | MIT | 6 |
| [domdomegg/airtable-mcp-server](https://github.com/domdomegg/airtable-mcp-server/tree/b28244860d90b28dffa3a0c9db0784e461e028b9) | b28244860d90b28dffa3a0c9db0784e461e028b9 | MIT | 6 |
| [executeautomation/mcp-playwright](https://github.com/executeautomation/mcp-playwright/tree/2349c2891e7c499c8c07b7d78c7f3fb4c797a1da) | 2349c2891e7c499c8c07b7d78c7f3fb4c797a1da | MIT | 6 |
| [github/github-mcp-server](https://github.com/github/github-mcp-server/tree/e3809fe91c7546633241006bf0b91f23b2595e28) | e3809fe91c7546633241006bf0b91f23b2595e28 | MIT | 6 |
| [isaacphi/mcp-gdrive](https://github.com/isaacphi/mcp-gdrive/tree/5a94bdcb751975f9f6552d261da35314baf89c43) | 5a94bdcb751975f9f6552d261da35314baf89c43 | MIT | 4 |
| [modelcontextprotocol/servers-archived/aws-kb-retrieval-server](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 1 |
| [modelcontextprotocol/servers-archived/brave-search](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 2 |
| [modelcontextprotocol/servers-archived/everart](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 1 |
| [modelcontextprotocol/servers-archived/gdrive](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 1 |
| [modelcontextprotocol/servers-archived/github](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 6 |
| [modelcontextprotocol/servers-archived/gitlab](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 6 |
| [modelcontextprotocol/servers-archived/google-maps](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 6 |
| [modelcontextprotocol/servers-archived/postgres](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 1 |
| [modelcontextprotocol/servers-archived/puppeteer](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 6 |
| [modelcontextprotocol/servers-archived/redis](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 4 |
| [modelcontextprotocol/servers-archived/sentry](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 1 |
| [modelcontextprotocol/servers-archived/slack](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 6 |
| [modelcontextprotocol/servers-archived/sqlite](https://github.com/modelcontextprotocol/servers-archived/tree/9be4674d1ddf8c469e6461a27a337eeb65f76c2e) | 9be4674d1ddf8c469e6461a27a337eeb65f76c2e | MIT | 6 |
| [modelcontextprotocol/servers/fetch](https://github.com/modelcontextprotocol/servers/tree/bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c) | bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c | Apache-2.0 | 1 |
| [modelcontextprotocol/servers/filesystem](https://github.com/modelcontextprotocol/servers/tree/bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c) | bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c | Apache-2.0 | 6 |
| [modelcontextprotocol/servers/memory](https://github.com/modelcontextprotocol/servers/tree/bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c) | bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c | Apache-2.0 | 6 |
| [modelcontextprotocol/servers/sequentialthinking](https://github.com/modelcontextprotocol/servers/tree/bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c) | bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c | Apache-2.0 | 2 |
| [neo4j-contrib/mcp-neo4j/mcp-neo4j-cloud-aura-api](https://github.com/neo4j-contrib/mcp-neo4j/tree/1c7ad0793b5f06b42b9c44f855c23eb2064c3bb7) | 1c7ad0793b5f06b42b9c44f855c23eb2064c3bb7 | MIT | 6 |
| [neo4j-contrib/mcp-neo4j/mcp-neo4j-cypher](https://github.com/neo4j-contrib/mcp-neo4j/tree/1c7ad0793b5f06b42b9c44f855c23eb2064c3bb7) | 1c7ad0793b5f06b42b9c44f855c23eb2064c3bb7 | MIT | 3 |
| [neo4j-contrib/mcp-neo4j/mcp-neo4j-data-modeling](https://github.com/neo4j-contrib/mcp-neo4j/tree/1c7ad0793b5f06b42b9c44f855c23eb2064c3bb7) | 1c7ad0793b5f06b42b9c44f855c23eb2064c3bb7 | MIT | 6 |
| [neo4j-contrib/mcp-neo4j/mcp-neo4j-memory](https://github.com/neo4j-contrib/mcp-neo4j/tree/1c7ad0793b5f06b42b9c44f855c23eb2064c3bb7) | 1c7ad0793b5f06b42b9c44f855c23eb2064c3bb7 | MIT | 7 |
| [nickclyde/duckduckgo-mcp-server](https://github.com/nickclyde/duckduckgo-mcp-server/tree/8182af3f2295017ca90527a924f48147fbf18d5b) | 8182af3f2295017ca90527a924f48147fbf18d5b | MIT | 4 |
| [octagonai/octagon-mcp-server](https://github.com/octagonai/octagon-mcp-server/tree/a3234633fbcc523be4b2ed68233c9e967c0c7fa2) | a3234633fbcc523be4b2ed68233c9e967c0c7fa2 | MIT | 4 |
| [redis/mcp-redis](https://github.com/redis/mcp-redis/tree/f6182f5c7273a7654103dde66b2234097074f79c) | f6182f5c7273a7654103dde66b2234097074f79c | MIT | 6 |
| [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian/tree/0a5d2427144d72f5aade07d4fabd385421cec401) | 0a5d2427144d72f5aade07d4fabd385421cec401 | MIT | 6 |
| [stripe/agent-toolkit](https://github.com/stripe/agent-toolkit/tree/24947f1632ee3440ba9f27f92404beea164517b9) | 24947f1632ee3440ba9f27f92404beea164517b9 | MIT | 5 |
| [supabase-community/supabase-mcp](https://github.com/supabase-community/supabase-mcp/tree/bd2d33f1b401adbbf913b3f40eb460fd67e1f9ea) | bd2d33f1b401adbbf913b3f40eb460fd67e1f9ea | Apache-2.0 | 1 |
| [tavily-ai/tavily-mcp](https://github.com/tavily-ai/tavily-mcp/tree/688b0f78d518d507cb31b94d9cc0e44c6eadd7c0) | 688b0f78d518d507cb31b94d9cc0e44c6eadd7c0 | 未识别 | 6 |
| [upstash/context7](https://github.com/upstash/context7/tree/6b636d3c35e051a1a653a236afb7f612c02a1ad3) | 6b636d3c35e051a1a653a236afb7f612c02a1ad3 | MIT | 2 |
| [zcaceres/fetch-mcp](https://github.com/zcaceres/fetch-mcp/tree/1ddb1a59cb09a2d38e759f2d7a97829680cbe514) | 1ddb1a59cb09a2d38e759f2d7a97829680cbe514 | MIT | 6 |
| [anaisbetts/mcp-youtube](https://github.com/anaisbetts/mcp-youtube/tree/acb39be2c04cf61787483cf9acf73dd14292a515) | acb39be2c04cf61787483cf9acf73dd14292a515 | MIT | 1 |
| [benborla/mcp-server-mysql](https://github.com/benborla/mcp-server-mysql/tree/b9c714e182422b9f18437242b80cf003adf1c7ea) | b9c714e182422b9f18437242b80cf003adf1c7ea | MIT | 3 |
| [blazickjp/arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server/tree/572e301bb3198962c025d5ed5e14becb86868daa) | 572e301bb3198962c025d5ed5e14becb86868daa | Apache-2.0 | 3 |
| [designcomputer/mysql_mcp_server](https://github.com/designcomputer/mysql_mcp_server/tree/d88c510f603413d1abad9c5cce2bd542d705e27c) | d88c510f603413d1abad9c5cce2bd542d705e27c | MIT | 3 |
| [exa-labs/exa-mcp-server](https://github.com/exa-labs/exa-mcp-server/tree/e9c3b0126a3373eb1aeaca162e84d0791ff4c7f7) | e9c3b0126a3373eb1aeaca162e84d0791ff4c7f7 | MIT | 3 |
| [getsentry/sentry-mcp](https://github.com/getsentry/sentry-mcp/tree/d7aa182b7d3fbbf93230b1d5b3e40fef04943ac7) | d7aa182b7d3fbbf93230b1d5b3e40fef04943ac7 | Apache-2.0 | 3 |
| [grafana/mcp-grafana](https://github.com/grafana/mcp-grafana/tree/5ea0cc34678cdd6fcd2f5c731b6619a8433bcb20) | 5ea0cc34678cdd6fcd2f5c731b6619a8433bcb20 | Apache-2.0 | 3 |
| [jina-ai/MCP](https://github.com/jina-ai/MCP/tree/b938c00f0870a75b39a78d5dff1f5bf645151a6e) | b938c00f0870a75b39a78d5dff1f5bf645151a6e | Apache-2.0 | 3 |
| [microsoft/markitdown](https://github.com/microsoft/markitdown/tree/4cc9fa17653d695d64fb9eee5b33d4de55ff84e8) | 4cc9fa17653d695d64fb9eee5b33d4de55ff84e8 | MIT | 1 |
| [openbnb-org/mcp-server-airbnb](https://github.com/openbnb-org/mcp-server-airbnb/tree/d5a8f18f5978b0a33dea4b3ec130c389bad845cc) | d5a8f18f5978b0a33dea4b3ec130c389bad845cc | MIT | 2 |
| [pydantic/logfire-mcp](https://github.com/pydantic/logfire-mcp/tree/1e11c2ce193050a11fc956151a2adc78966518c1) | 1e11c2ce193050a11fc956151a2adc78966518c1 | MIT | 3 |
| [rusiaaman/wcgw](https://github.com/rusiaaman/wcgw/tree/339201affd179795139590351e0eb25f910d6306) | 339201affd179795139590351e0eb25f910d6306 | Apache-2.0 | 3 |

盲标包：`.local/stage-d4/reviewer-blind.jsonl`，每行只有id与text，无标签、概率、预测。SHA-256：`95d98659bd376839bd875102c7d544c26e2c32629a4c5fde8d43eff273882a06`。另提供同目录 reviewer-blind.zip，内容相同。正文与原始输出只存.local。

## 冻结评测（只输出聚合）

| 集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| benign-aggregate | 1293 | 0.8872 | 0.3033 | 0.2336 | 0.4521 | 0.6404 | 0.1996 |
| gold-aggregate | 1014 | 0.9865 | 0.9605 | 0.0021 | 0.9733 | 0.8477 | 0.0258 |
| full_combined | 1000 | 0.9365 | 0.9395 | 0.0266 | 0.9380 | 0.9545 | 0.0233 |
| adjusted_combined | 995 | 0.9421 | 0.9391 | 0.0266 | 0.9406 | 0.9558 | 0.0210 |
| full_semantic | 788 | 0.9238 | 0.9700 | 0.0061 | 0.9463 | 0.9616 | 0.0207 |
| adjusted_semantic | 783 | 0.9320 | 0.9697 | 0.0061 | 0.9505 | 0.9637 | 0.0178 |
| public | 212 | 0.9619 | 0.8860 | 0.1215 | 0.9224 | 0.9150 | 0.0398 |

| 集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| command | 199 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0150 |
| documentation | 707 | 0.9368 | 0.3820 | 0.2353 | 0.5427 | 0.6976 | 0.2019 |
| mcp | 387 | 0.7632 | 0.1859 | 0.3639 | 0.2990 | 0.4798 | 0.2924 |

| 真实良性集验收项 | 实际 | 要求 | 通过 |
|---|---|---|---|
| request精确率 | 0.3033419023136247 | >=0.85 | False |
| none误报率 | 0.2336206896551724 | <=0.03 | False |

命令输出没有request支持，分组召回/精确率的0是实现约定；整体含133个request样本和1160个none样本，门槛按整体计算。真实集标签来自双教师一致，并非人工金标准；未根据该集修改模型、温度或阈值。盲标包支持评审方独立复核。

| 集合 | n | request召回 | request精确率 | none误报率 | request F1 | macro-F1（argmax） | ECE |
|---|---|---|---|---|---|---|---|
| c | 400 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.0235 |
| c2 | 614 | 0.9783 | 0.9375 | 0.0035 | 0.9574 | 0.8421 | 0.0272 |

## 离线轨迹重算

| 金标准 | S1关拦截召回 | S1开拦截召回 | 新增ASK | 未下降 |
|---|---|---|---|---|
| c | 0.9761904761904762 | 0.9761904761904762 | 0 | True |
| c2 | 1.0 | 1.0 | 0 | True |

Offline-only full-source inference after restoring missing historical evidence into an isolated local root; completed benchmark metrics were not rerun

## 单测与真实Pi运行

| 测试 | 数量 | 通过 | 秒 |
|---|---|---|---|
| unit-tests.log | 197 | True | 16.474 |
| unit-tests-final.log | 198 | True | 15.763 |
| targeted-tests.log | 10 | True | 0.726 |

未运行：运行ID=[]，verify_v2=null。新真实良性集门槛未通过，未启动S1临时启用或真实Pi冒烟/矩阵；真实运行的新增ASK及攻击成功率均为null，不能用离线新增ASK=0替代。

## 云端调用量

| 模型 | 请求数（含失败） | 有usage的请求 | 已知总token |
|---|---|---|---|
| deepseek-v4.1-flash | 454 | 453 | 1967640 |
| mimo-v2.5 | 452 | 452 | 1601138 |

损坏请求日志行0；无usage不按零token计。请求日志只包含model/seconds/tokens。

## 验收逐项自检

| 项 | 结果 |
|---|---|
| D3_checkpoint | True |
| no_training_or_new_training_data | True |
| validation_only_threshold | True |
| model_temperature_verified | True |
| real_benign_size | True |
| real_benign_metrics | False |
| semantic_and_combined | True |
| gold_regression | True |
| offline_interception_not_lower | True |
| real_runs | None |
| S1_formally_enabled | False |
| stage_E_started | False |

## 改动文件

- `lab.py`
- `evaluate_stage_d.py`
- `evaluate_stage_d4.py`
- `src/d2v2/request_model.py`
- `src/d2v2/core.py`
- `tests/test_stage_d4.py`
- `stage_d4_collect.py`
- `stage_d4_commands.py`
- `stage_d4_finalize_data.py`
- `stage_d4_freeze_data.py`
- `stage_d4_offline.py`
- `stage_d4_protocol.py`
- `stage_d4_regression.py`
- `stage_d4_report.py`
- `stage_d4_sources.py`
- `stage_d4_supplement.py`
- `stage_d4_teacher.py`
- `stage_d4_verify.py`
- `docs/23-stage-d4-report.md`
- `docs/stage-d4-results.json`
- `docs/stage-d4-verification.md`
- `docs/03-status.md`
- `docs/整体设计文档.md`

全局偏好另写入 `E:/CodexState/home/AGENTS.md` 与 `C:/Users/zhouxingfu/.codex/AGENTS.md`，不在仓库提交中。

## 未解决问题

阶段D⁗未通过真实良性集门槛；S1关闭，真实回归未启动，停止等待评审

{"status": "阶段D⁗未通过真实良性集门槛；S1关闭，真实回归未启动，停止等待评审", "reason": {"real_benign_request_precision": 0.3033419023136247, "required_precision": 0.85, "real_benign_none_fpr": 0.2336206896551724, "required_none_fpr": 0.03}, "started_unix": 1792304510, "stopped_unix": 1792307521.4620323, "deadline_unix": 1792311710, "wall_seconds": 3011.4620323181152, "within_two_hours": true, "training": false, "real_run_ids": [], "verify_v2": null, "stage_E_started": false}

离线证据恢复：算力机缺部分历史轨迹；第一次文件复制遗漏SQLite WAL。最终通过只读连接的backup接口生成149份一致快照，在隔离目录恢复；原证据未改写，149份events计数一致。所有恢复错误发生在离线模型推理之前；最终单独推理360个完整来源，三个已完成的片段评测聚合文件哈希未变。
