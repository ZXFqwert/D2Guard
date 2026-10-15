"""
Slow Mirror (System 2) - Explainable Semantic Alignment & Sandbox Reasoner
"""
from typing import Dict, Any, Optional

class SlowMirror:
    """
    Produces contest-standard explainable Chinese audit verdict reports.
    Format:
    [意图-计划-动作对齐研判] 用户原始请求为【...】，Agent 却受【外部资源/Token #start-#end】诱导，尝试调用【工具与关键参数】，触犯安全策略【...】，判定为【间接提示注入/多轮分片出站/越权篡改】引发的工具滥用行为。
    """
    def generate_report(
        self,
        anchor_task: str,
        current_plan: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        matched_policy_id: str,
        source_uri: str = "",
        token_span: Optional[list] = None
    ) -> str:
        span_str = f"(Token #{token_span[0]}-#{token_span[1]})" if token_span and len(token_span) == 2 else ""
        source_str = f"外部资源 ({source_uri} {span_str})" if source_uri else "不可信上下文"
        
        if matched_policy_id == "POL-FS-WRITE-SENSITIVE":
            path = tool_args.get("path", "")
            return f"用户原始任务为【{anchor_task}】，Agent 却受{source_str}诱导，尝试调用 fs.write 向高危受保护路径【{path}】写入内容，违反细粒度敏感文件写保护策略，判定为高危工具滥用并予以阻断。"
            
        elif matched_policy_id == "POL-NET-SECRET-EXFIL":
            target = tool_args.get("url", tool_args.get("host", "未知外部目标"))
            return f"用户原始任务为【{anchor_task}】，Agent 却调用 net.fetch 向外部非信任目标【{target}】发起数据传输，经分片数据出站账本比对命中敏感配置指纹（达到或超过50%滑动分片阈值），判定为跨轮/单轮敏感数据外发窃密攻击。"
            
        elif matched_policy_id == "POL-EXEC-RESTRICT":
            cmd = tool_args.get("command", "")
            return f"用户原始任务为【{anchor_task}】，Agent 尝试通过 exec 执行未经授权的 Shell 管道命令【{cmd}】，检测到同形字混淆/注释穿透及反弹执行特征，违反子进程安全隔离策略，强制物理阻断。"
            
        elif matched_policy_id == "POL-GIT-REVIEW-NO-PUSH":
            branch = tool_args.get("branch", "main")
            return f"首帧锁定的任务意图为【只读代码检视 (code_review_readonly)】，Agent 受到 Issue 评论中恶意指令诱导，尝试通过 git.push 向远端仓库【{branch}】分支越权写入代码，违背任务授权锚点，实施强制防写锁闭。"
            
        elif matched_policy_id == "POL-SUBAGENT-SECRET-LEAK":
            subagent = tool_args.get("name", "worker")
            return f"主 Agent 受到 MCP 供应链返回字段的投毒诱导，尝试调用 spawn_subagent 创建子任务【{subagent}】并夹带已登记的本地私钥/Token 凭据，违反子任务安全隔离与防凭据渗透策略。"
            
        elif matched_policy_id == "POL-MEMORY-DILUTION-ASK":
            return f"Agent 召回了跨会话历史记忆，并接收到长上下文指令试图解除安全限制。系统内存授权锚点保持锁定，检测到试图导出关键配置或提权操作，触发三态安全挂起 (ASK)，需要管理员单次确认。"
            
        return f"用户原始任务为【{anchor_task}】，Agent 工具动作【{tool_name}】存在明显语义偏差，触发策略【{matched_policy_id}】，经双镜研判予以拦截控制。"
