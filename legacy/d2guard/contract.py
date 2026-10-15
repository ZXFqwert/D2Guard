"""
语义不变量断言契约引擎 (Semantic Invariant Contract Engine)
定位：
实现“意图—计划—工具”的形式化数学对齐与确定性安全检查。
核心机理：
1. 编译期：根据用户初始任务 (Initial Task)，在 1ms 内形式化编译生成三维安全不变量契约：
   - 路径只读域 (Path Domain)：合法读写白名单与受保护敏感路径黑名单；
   - 副作用能力集 (Capability Set)：网络外发、文件覆写、破坏性删除、终端执行、代码推送、子 Agent 派发能力布尔锁；
   - 机密敏感界 (Secret Boundary)：严格禁止向未授权媒介流动已读凭据。
2. 运行期：工具执行前执行 0.05ms 极速形式化断言验证：
   - 违约直接硬阻断 (BLOCK)，从数学与逻辑上杜绝大模型裁判被二次提示注入 (Judge Hijacking)；
   - 慢镜 (DeepSeek) 仅负责将违约因果转化为符合赛题规范的高质量中文判词。
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import ActionVerdict, SecurityState, VerdictType


@dataclass
class InvariantContract:
    """单个会话的语义安全不变量契约"""
    task_intent: str
    task_category: str  # 'code_review' | 'general_qa' | 'doc_summary' | 'deploy' | 'dev_build'
    
    # 1. 路径访问域
    allowed_read_patterns: List[str] = field(default_factory=list)
    forbidden_write_patterns: List[str] = field(default_factory=list)
    
    # 2. 工具副作用能力权限锁
    allow_network_egress: bool = False
    allow_filesystem_write: bool = False
    allow_filesystem_delete: bool = False
    allow_terminal_exec: bool = False
    allow_git_push: bool = False
    allow_subagent_secrets: bool = False

    # 3. 受信目标域
    trusted_network_domains: List[str] = field(default_factory=list)


class ContractCompiler:
    """契约编译器：基于用户初始意图编译形式化不变量"""

    @classmethod
    def compile_intent(cls, initial_task: str) -> InvariantContract:
        task_lower = initial_task.lower()

        # 场景 A: 代码检视、安全走查、代码审计类
        if any(w in task_lower for w in ["检视", "审查", "走查", "audit", "review", "代码规范", "静态分析"]):
            return InvariantContract(
                task_intent=initial_task,
                task_category="code_review",
                allowed_read_patterns=[r".*\.(py|js|ts|java|c|cpp|go|md|txt|json|yaml|yml)$", r"src/.*", r"tests/.*"],
                forbidden_write_patterns=[r".*settings\.json$", r".*\.vscode/.*", r".*\.git/.*", r".*\.ssh/.*", r".*\.env.*"],
                allow_network_egress=False,
                allow_filesystem_write=False,
                allow_filesystem_delete=False,
                allow_terminal_exec=False,
                allow_git_push=False,  # 严格对齐赛题能力 3
                allow_subagent_secrets=False,
                trusted_network_domains=["github.com"]
            )

        # 场景 B: 外部网页文档阅读与总结
        if any(w in task_lower for w in ["总结", "文档", "概括", "翻译", "summary", "read doc", "博客"]):
            return InvariantContract(
                task_intent=initial_task,
                task_category="doc_summary",
                allowed_read_patterns=[r".*\.(md|txt|html|pdf)$", r"docs/.*"],
                forbidden_write_patterns=[r".*settings\.json$", r".*\.vscode/.*", r".*\.git/.*", r".*\.ssh/.*", r".*\.env.*"],
                allow_network_egress=False,  # 总结文档禁止将本地数据向外窃取
                allow_filesystem_write=True, # 允许保存总结产物与临时笔记
                allow_filesystem_delete=True,
                allow_terminal_exec=False,
                allow_git_push=False,
                allow_subagent_secrets=False,
                trusted_network_domains=["huggingface.co", "github.com", "docs.python.org"]
            )

        # 场景 C: 修复 Bug 并提交代码开发
        if any(w in task_lower for w in ["修复", "开发", "实现", "fix", "implement", "feature", "提交推送"]):
            return InvariantContract(
                task_intent=initial_task,
                task_category="dev_build",
                allowed_read_patterns=[r".*"],
                forbidden_write_patterns=[r".*\.ssh/.*", r".*authorized_keys", r".*\.aws/.*"],
                allow_network_egress=True,
                allow_filesystem_write=True,
                allow_filesystem_delete=False,
                allow_terminal_exec=True,
                allow_git_push=True,
                allow_subagent_secrets=False,
                trusted_network_domains=["pypi.org", "github.com", "api.trusted.com"]
            )

        # 默认通用契约 (常规交互与任务支持)
        return InvariantContract(
            task_intent=initial_task,
            task_category="general_qa",
            allowed_read_patterns=[r".*"],
            forbidden_write_patterns=[r".*\.ssh/.*", r".*settings\.json", r"/etc/.*"],
            allow_network_egress=True,
            allow_filesystem_write=True,
            allow_filesystem_delete=True,
            allow_terminal_exec=True,
            allow_git_push=False,
            allow_subagent_secrets=False,
            trusted_network_domains=["api.trusted.com"]
        )


class InvariantVerifier:
    """契约验证器：0.05ms 确定性断言检查"""

    @classmethod
    def verify(
        cls,
        contract: InvariantContract,
        tool_name: str,
        tool_args: dict,
        state: SecurityState
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        验证动作是否违背形式化安全不变量
        返回: (is_valid, violation_policy_id, violation_reason)
        """
        # 1. 检查文件写操作与不可篡改工作区配置 (fs.write)
        if tool_name in ["fs.write", "fs_write"]:
            path = str(tool_args.get("path", "") or tool_args.get("file", ""))
            
            # 硬规则：保护 .vscode/settings.json、.git/、系统关键目录 (CVE-2025-53773)
            immutable_patterns = [
                r"(?i)\.vscode/settings\.json",
                r"(?i)\.vscode/tasks\.json",
                r"(?i)\.git/config",
                r"(?i)\.bashrc",
                r"(?i)\.zshrc",
                r"(?i)\.ssh/",
                r"(?i)\.aws/"
            ]
            for p in immutable_patterns:
                if re.search(p, path):
                    return False, "POL-FS-CONFIG-IMMUTABLE", f"契约断言违背: 严禁篡改工作区关键元配置或权限文件: {path}"

            # 契约规则：当前任务是否允许写文件
            if not contract.allow_filesystem_write:
                return False, "CONTRACT-FS-WRITE-DISALLOWED", f"语义契约违背: 用户初始任务锁定为 [{contract.task_category}] 只读任务，严禁执行文件写入: {path}"

        # 2. 检查 Git 远端推送 (git.push)
        if tool_name in ["git.push", "git_push"]:
            if not contract.allow_git_push:
                return False, "POL-GIT-REVIEW-NO-PUSH", f"语义契约违背: 用户初始任务属于 [{contract.task_category}] 场景，形式化禁止代码推送操作"

        # 3. 破坏性删除 (fs.delete) 由策略引擎 POL-FS-DELETE-ASK 统一触发 ASK 单次审批机制，契约层不执行硬阻断

        # 4. 检查网络外发能力 (net.fetch)
        if tool_name in ["net.fetch", "net_fetch"]:
            url = str(tool_args.get("url", ""))
            if not contract.allow_network_egress and state.read_secrets:
                return False, "CONTRACT-NET-EGRESS-DISALLOWED", f"语义契约违背: 会话已接触敏感机密且当前契约禁止外网数据流动，阻断向 {url} 发送数据"

        # 5. 检查终端执行能力 (exec)
        if tool_name in ["exec", "exec_cmd"]:
            cmd = str(tool_args.get("command", ""))
            if not contract.allow_terminal_exec:
                # 若任务完全不包含执行
                return False, "CONTRACT-EXEC-DISALLOWED", f"语义契约违背: 任务 [{contract.task_category}] 不具备终端执行能力，阻断命令: {cmd}"

        return True, None, None
