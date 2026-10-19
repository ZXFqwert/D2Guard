# 阶段 G 评审：能力补全

评审日期：2026-10-19。评审对象：[阶段 G 报告](../28-stage-g-report.md)、`stage-g-results.json`、未提交改动。评审人：Claude。

## 结论：退回，转阶段 G′（简化重做）

停机原因（容器 PID 1 不回收子进程，僵尸进程耗尽线程额度）是部署复杂度本身造成的，与防护逻辑无关。更重要的是防护开启的干净轮次里出现大量误拦，根因是三处过度保守的事实建模，不是决策表或 S1 的问题。

**责任说明：** “Docker Compose 双容器”是评审方在执行方案 G1 中写的，对比赛并不必要。赛题要求的是防护系统，主流编码 Agent 也多在宿主机上运行；我们的防护在 Hook/内核层，不依赖容器。容器只是为了让“下载执行、推送”这类危险测试动作能安全真跑，这用本地夹具即可做到。

## 误拦根因（clean/on 轮次）

| 现象 | 次数 | 根因（代码位置） |
|---|---|---|
| `ls -la`、`git log` 等只读命令被 DT-4c 挂起 | 16 | `policy.py` `is_egress_sink`：`exec` 一律视为外发；且新来源（命令输出、HTTP MCP 返回）疑似缺 S1 分析，按“未覆盖”记为请求污染 |
| `pwd && ls && git log … \| head` 被 POL-EXEC-RESTRICT 拦截 | 7 | `cmd.ast.unverifiable` 实为“不在命令白名单”，把普通管道/重定向当成不可审计 |
| 派发子 Agent 被 DT-4c-EGRESS 挂起 | 2 | `is_egress_sink` 把 `spawn_subagent` 当外发 |
| 只读 MCP 调用被挂起 | 4 | `is_egress_sink` 除 `project_facts` 外的 MCP 调用全算外发 |

另：git push 由 POL-EXEC-RESTRICT 拦下而不是 POL-GIT-REVIEW-NO-PUSH，下载执行由 DT-4c 拦下而不是 POL-EXEC-RESTRICT，说明命令没有被解析成具体效果；多层场景主 Agent 先读到注入，第一层就挂起，孙层路径没有被测到。

## 做得对的

- G0 慢镜超时 90 秒可配置；G5 已查官方公告，口径准确（只复现配置篡改机制）。
- 已运行的防护开启攻击轮攻击成功 0；IDE 自动批准写入、敏感 exec 写入被正确拦截；E′ 回归 16/16 核验、有效拦截 9/9。
- 失败轮全部保留，没有择优替换。

## 转入 G′

见执行方案“阶段 G′”。
