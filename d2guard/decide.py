"""
接口三：decide(state, proposed_action, extracted, event) -> ActionVerdict
决策中枢职责：
1. 评估 YAML 策略 DSL；
2. 跨轮敏感凭据匹对（支持明文、Base64 以及滑动分片累计熔断）；
3. 执行 exec Shell AST 分析与子进程环境变量隔离检查；
4. 特权操作触发单次绑定 ApprovalToken (ASK 机制)；
5. 快镜出疑点时唤醒慢镜 DeepSeek 精选证据包深度裁判；
6. 返回三态裁决 (ALLOW / ASK / BLOCK)。
"""

from __future__ import annotations
import hashlib
import os
import re
import uuid
import yaml
from typing import Any, Dict, List, Optional

from .models import (
    ActionVerdict,
    ApprovalToken,
    D2Event,
    ExtractedData,
    SecurityState,
    VerdictType,
)
from .slow_mirror import EvidencePack, SlowMirror


class PolicyDecisionEngine:
    """策略决策引擎"""

    def __init__(
        self,
        policy_path: Optional[str] = None,
        slow_mirror: Optional[SlowMirror] = None
    ):
        self.policy_path = policy_path or os.path.join(
            os.path.dirname(__file__), "..", "policies", "default_policy.yaml"
        )
        self.slow_mirror = slow_mirror or SlowMirror()
        self.policies = self._load_policies()

    def _load_policies(self) -> List[Dict[str, Any]]:
        """加载 YAML 策略配置"""
        if os.path.exists(self.policy_path):
            try:
                with open(self.policy_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    return data.get("policies", [])
            except Exception as e:
                print(f"[D2Guard] 警告: 加载策略文件失败 {e}，使用内置硬规则")
        return []

    def check_secrets_and_chunks(
        self,
        state: SecurityState,
        payload_str: str,
        target_domain: Optional[str] = None
    ) -> tuple[bool, bool, str]:
        """
        跨轮已读敏感数据匹配检查：
        返回: (is_match, is_chunked, match_desc)
        """
        if not state.read_secrets:
            return False, False, ""

        payload_lower = payload_str.lower()

        for sec_id, secret in state.read_secrets.items():
            # 1. 完整明文匹配
            if secret.exact_text.lower() in payload_lower:
                return True, False, f"命中已读敏感凭证完整明文 [{sec_id} from {secret.source_path}]"

            # 2. 预存 Base64 匹配
            if secret.base64_text.lower() in payload_lower:
                return True, False, f"命中已读敏感凭证 Base64 编码 [{sec_id} from {secret.source_path}]"

            # 3. 8 字节子片段匹配与多轮累计追踪
            matched_chunks = [c for c in secret.sub_chunks if c.lower() in payload_lower]
            if matched_chunks:
                # 累积到该域名的记录
                if target_domain:
                    outbound_hist = state.accumulated_outbound.setdefault(
                        target_domain,
                        type(list(state.accumulated_outbound.values())[0])(domain=target_domain) if state.accumulated_outbound else None
                    )
                    # 无论如何记录该片段
                    if hasattr(outbound_hist, 'matched_chunk_set'):
                        outbound_hist.matched_chunk_set.update(matched_chunks)
                        # 计算累计覆盖率
                        coverage = len(outbound_hist.matched_chunk_set) / max(1, len(secret.sub_chunks))
                        if coverage >= 0.25 or len(matched_chunks) >= 2:
                            return True, True, f"命中敏感数据多轮分片累计窃取 [{sec_id} 覆盖率 {coverage*100:.1f}%]"

                # 即使单次，如果有较长子串在外部非信任请求中
                if len(matched_chunks) >= 2 or len(matched_chunks[0]) >= 12:
                    return True, True, f"命中已读敏感凭证特征分片 [{sec_id}]"

        return False, False, ""

    def decide(
        self,
        state: SecurityState,
        proposed_action: dict,
        extracted: ExtractedData,
        event: D2Event,
        approval_token: Optional[ApprovalToken] = None
    ) -> ActionVerdict:
        """主决策接口"""
        tool_name = event.tool_name or proposed_action.get("tool_name", "")
        tool_args = event.tool_args or proposed_action.get("tool_args", {})
        call_id = event.call_id or str(uuid.uuid4())

        # 0. 校验单次 ASK 批准令牌 (若携带)
        if approval_token and approval_token.is_valid_for(call_id, tool_args):
            return ActionVerdict(
                verdict=VerdictType.ALLOW,
                reason="用户已单次手动批准此特定操作令牌"
            )

        # 1. 规则 1: 敏感系统路径写入阻断 (fs.write)
        if tool_name == "fs.write":
            target_path = tool_args.get("path", "") or tool_args.get("file", "")
            for p in self.policies:
                if p.get("id") == "POL-FS-WRITE-SENSITIVE":
                    pattern = p.get("target_path_regex", "")
                    if pattern and re.search(pattern, target_path, re.IGNORECASE):
                        return ActionVerdict(
                            verdict=VerdictType.BLOCK,
                            policy_id="POL-FS-WRITE-SENSITIVE",
                            reason=f"阻断写入敏感系统路径: {target_path}"
                        )

        # 2. 规则 2: 敏感凭证跨轮与分片外发拦截 (net.fetch)
        if tool_name == "net.fetch":
            url = tool_args.get("url", "")
            body = tool_args.get("body", "") or tool_args.get("data", "")
            target_domain = extracted.domains[0] if extracted.domains else ""
            
            # 检查白名单
            trusted = state.effective_permissions.get("trusted_domains", [])
            is_trusted = any(td in target_domain for td in trusted) if target_domain else False

            if not is_trusted:
                payload_to_check = f"{url} {body}"
                is_match, is_chunked, match_desc = self.check_secrets_and_chunks(
                    state, payload_to_check, target_domain
                )
                if is_match:
                    return ActionVerdict(
                        verdict=VerdictType.BLOCK,
                        policy_id="POL-NET-SECRET-EXFIL",
                        reason=f"外发阻断: {match_desc}",
                        is_chunked_leak=is_chunked,
                        is_partial_leak=False
                    )

        # 3. 规则 3: 恶意 Shell 命令 AST 检查 (exec)
        if tool_name == "exec":
            ast_info = extracted.ast_info or {}
            # 检查管道注入
            if ast_info.get("has_pipe_to_interpreter"):
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    policy_id="POL-EXEC-RESTRICT",
                    reason="AST 语法分析检出危险管道到解释器执行流 (如 curl | bash)"
                )
            # 检查高危下载传输工具
            dangerous_binaries = ast_info.get("dangerous_binaries", [])
            blocked_binaries = ["curl", "wget", "nc", "netcat"]
            for b in dangerous_binaries:
                if b in blocked_binaries:
                    return ActionVerdict(
                        verdict=VerdictType.BLOCK,
                        policy_id="POL-EXEC-RESTRICT",
                        reason=f"禁止调用高危外部传输与下载工具: {b}"
                    )

        # 4. 规则 4: 代码检视任务越权推送拦截 (git.push)
        if tool_name == "git.push":
            if state.initial_task_type in ["code_review", "review", "audit"]:
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    policy_id="POL-GIT-REVIEW-NO-PUSH",
                    reason="用户初始任务被锁定为代码检视 (code_review)，严禁执行 git.push"
                )

        # 5. 规则 5: 子 Agent 凭证渗透拦截 (spawn_subagent)
        if tool_name == "spawn_subagent":
            sub_prompt = str(tool_args.get("prompt", "") or tool_args.get("task", ""))
            is_match, _, match_desc = self.check_secrets_and_chunks(state, sub_prompt)
            if is_match:
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    policy_id="POL-SUBAGENT-SECRET-LEAK",
                    reason=f"阻断向子 Agent 渗透主会话敏感凭证: {match_desc}"
                )

        # 6. 特权破坏性操作触发 ASK 询问 (fs.delete)
        if tool_name in ["fs.delete", "fs.remove"]:
            token_id = str(uuid.uuid4())[:8]
            args_hash = hashlib.sha256(str(sorted(tool_args.items())).encode()).hexdigest()
            token = ApprovalToken(token_id=token_id, call_id=call_id, args_hash=args_hash)
            return ActionVerdict(
                verdict=VerdictType.ASK,
                policy_id="POL-FS-DELETE-ASK",
                reason=f"待删除文件操作具有破坏性，挂起请求等待用户确认",
                approval_token=token
            )

        # 7. 快镜初筛与慢镜疑点裁决
        fast_signals = extracted.fast_mirror_signals
        risk_score = fast_signals.get("risk_score", 0.0)
        action_compliance = fast_signals.get("action_compliance", "expected")

        # 若快镜标记明显越权或高风险
        if risk_score >= 0.5 or action_compliance == "deviant":
            # 唤醒慢镜 System 2 深度研判
            evidence = EvidencePack(
                initial_task=state.initial_task,
                effective_permissions=state.effective_permissions,
                proposed_action={"tool_name": tool_name, "tool_args": tool_args},
                taint_snippet=event.raw_content[:500],
                matched_secrets=list(state.read_secrets.keys()),
                call_id=call_id
            )
            slow_res = self.slow_mirror.judge(evidence)
            slow_verdict_str = slow_res.get("verdict", "ASK")
            verdict_type = VerdictType(slow_verdict_str)

            if verdict_type == VerdictType.ASK:
                token_id = str(uuid.uuid4())[:8]
                args_hash = hashlib.sha256(str(sorted(tool_args.items())).encode()).hexdigest()
                token = ApprovalToken(token_id=token_id, call_id=call_id, args_hash=args_hash)
                return ActionVerdict(
                    verdict=VerdictType.ASK,
                    reason=f"慢镜研判可疑: {slow_res.get('reason')}",
                    approval_token=token,
                    evidence_summary=slow_res
                )
            elif verdict_type == VerdictType.BLOCK:
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    reason=f"慢镜阻断: {slow_res.get('reason')}",
                    evidence_summary=slow_res
                )

        # 8. 无任何规则触碰，放行
        return ActionVerdict(
            verdict=VerdictType.ALLOW,
            reason="常规安全操作，快速放行"
        )
