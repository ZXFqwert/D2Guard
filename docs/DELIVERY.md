# 交付文档入口

**核心防护模型为自行训练的 D²Guard-Laya S1 多语言模型。** 程序包中的冻结权重位于 `weights/D2Guard-multilingual/`，英文原版是独立基线与 tokenizer 组件。安装与配置见根 `README.md` 和 `WINDOWS-使用说明.md`。

- [当前模型、Python/Node/Pi 与 GPU 访问交接](39-runtime-and-compute-handoff.md)
- [CVE 与跨来源拆分评测](37-cve-and-split-injection-20261020.md)
- [多 MCP、直接指标及证据导出](38-multi-mcp-and-direct-metrics-20261021.md)
- [同一原生会话跨用户轮次评测](40-multiturn-final-20261021.md)

冻结的83场景矩阵评测共 996 次，未重跑。**攻击成功 110/164（67.1%）→0/165；正常完成 249/249→230/249；自身裁决误挂起 0/929，另有 2 次会话连带暂停。** 矩阵机读结果为 `stage-h-results.json`。专项评测记录按 `supplemental-runs.json` 保存，共 245 条；演示证据另见 `demo-runs.json`。历史研究文档保留于开发仓库，不作为此交付包的当前部署指令。

三份正式 DOCX 作为程序 ZIP 的同级交付件提供。密钥、`.local`、虚拟环境与缓存不入包。导出时只对包内上游主机名称脱敏，并更新引用的 manifest 哈希；开发工作区的原始运行记录保持不变。

- [最终功能交付验收与限制](41-final-acceptance-20261021.md)
