"""
接口三：decide(state, proposed_action, extracted, event) -> ActionVerdict
决策中枢职责：
1. 评估 YAML 策略 DSL；
2. 跨轮敏感凭据匹对（支持明文、Base64 以及滑动分片累计熔断）；
3. 执行 exec Shell AST 分析与子进程环境变量隔离检查；
4. 特权操作触发单次绑定 ApprovalToken (ASK 机制)；
5. 快镜出疑点时唤醒慢镜 DeepSeek / GPU1 精选证据包深度因果裁判；
6. 支持消融实验控制开关 (enable_state_aggregation)；
7. 返回三态裁决 (ALLOW / ASK / BLOCK)。
"""

from __future__ import annotations
import secrets
from urllib.parse import urlsplit
import os
import re
import uuid
import yaml
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    canonical_args_hash,
    ActionVerdict,
    ApprovalToken,
    D2Event,
    DomainOutboundHistory,
    ExtractedData,
    SecurityState,
    VerdictType,
)
from .contract import ContractCompiler, InvariantVerifier
from .redaction import OutboundRedactor
from .normalizer import AdversarialNormalizer
from .slow_mirror import EvidencePack, SlowMirror
from .taint_engine import DynamicTaintEngine


class PolicyDecisionEngine:
    """策略决策引擎"""

    def __init__(
        self,
        policy_path: Optional[str] = None,
        slow_mirror: Optional[SlowMirror] = None,
        enable_state_aggregation: bool = True
    ):
        self.policy_path = policy_path or os.path.join(
            os.path.dirname(__file__), "..", "policies", "default_policy.yaml"
        )
        self.slow_mirror = slow_mirror or SlowMirror()
        self.enable_state_aggregation = enable_state_aggregation
        self.policies, self.settings = self._load_policies()
        self.outbound_redactor_provider = None

    def _load_policies(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """加载 YAML 策略配置"""
        if os.path.exists(self.policy_path):
            try:
                with open(self.policy_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    return data.get("policies", []), data.get("settings", {})
            except Exception as e:
                print(f"[D2Guard] 警告: 加载策略文件失败 {e}，使用内置硬规则")
        return [], {}

    def check_secrets_and_chunks(
        self,
        state: SecurityState,
        payload_str: str,
        target_domain: Optional[str] = None
    ) -> Tuple[bool, bool, str]:
        """
        跨轮已读敏感数据与多轮分片滑动窗口匹配检查
        返回: (is_match, is_chunked, match_desc)
        """
        # 消融检查：若关闭状态聚合机 (Delta-Only 消融组)，无法感知此前读取的敏感数据
        if not self.enable_state_aggregation or not state.read_secrets:
            return False, False, ""

        if not payload_str:
            return False, False, ""

        # 对抗样本规范化：展开 URL 解码、Base64 解码、Hex 解码等候选文本
        _, candidates = AdversarialNormalizer.normalize_for_inspection(payload_str)
        if payload_str not in candidates:
            candidates.append(payload_str)

        chunk_settings = self.settings.get("sharded_chunks", {})
        cov_threshold = chunk_settings.get("coverage_threshold", 0.35)
        min_chunks = chunk_settings.get("min_matched_chunks", 2)

        for sec_id, secret in state.read_secrets.items():
            exact_lower = secret.exact_text.lower()
            b64_lower = secret.base64_text.lower()

            for cand in candidates:
                cand_lower = cand.lower()

                # 1. 完整明文匹配
                if exact_lower in cand_lower:
                    return True, False, f"命中已读敏感凭证完整明文 [{sec_id} from {secret.source_path}]"

                # 2. 预存 Base64 匹配
                if b64_lower in cand_lower:
                    return True, False, f"命中已读敏感凭证 Base64 编码 [{sec_id} from {secret.source_path}]"

            # 3. 滑动分片匹配与多轮累计追踪
            all_matched_in_payload = set()
            for cand in candidates:
                cand_lower = cand.lower()
                for c in secret.sub_chunks:
                    if len(c) >= 6 and c.lower() in cand_lower:
                        all_matched_in_payload.add(c)

            if all_matched_in_payload:
                matched_list = list(all_matched_in_payload)
                if target_domain:
                    outbound_hist = state.accumulated_outbound.setdefault(
                        target_domain,
                        DomainOutboundHistory(domain=target_domain)
                    )
                    outbound_hist.matched_chunk_set.update(matched_list)
                    coverage = len(outbound_hist.matched_chunk_set) / max(1, len(secret.sub_chunks))

                    # 触发分片累计熔断
                    if coverage >= cov_threshold or len(outbound_hist.matched_chunk_set) >= min_chunks:
                        return True, True, (
                            f"命中敏感数据多轮分片累计窃取 [{sec_id} "
                            f"累积覆盖率 {coverage*100:.1f}%, 命中分片数 {len(outbound_hist.matched_chunk_set)}]"
                        )
                else:
                    # 单次 payload 包含多个分片特征
                    if len(matched_list) >= min_chunks:
                        return True, True, f"命中已读敏感凭证多重特征分片 [{sec_id}]"

        # 4. 动态变异污点 (Hex/URL/反转) 与香农熵异常检测
        is_tainted, taint_reason, _ = DynamicTaintEngine.scan_for_tainted_flow(
            payload_str, state.read_secrets
        )
        if is_tainted:
            return True, False, taint_reason

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

        # 0. 校验单次 ASK 批准令牌 (若携带且有效)
        if approval_token and approval_token.is_valid_for(call_id, tool_args):
            return ActionVerdict(
                verdict=VerdictType.ALLOW,
                reason="用户已单次手动批准此特定操作令牌"
            )

        # 0.5 语义不变量断言契约验证 (Semantic Invariant Contract)
        contract = getattr(state, "invariant_contract", None)
        if not contract and state.initial_task:
            contract = ContractCompiler.compile_intent(state.initial_task)
            state.invariant_contract = contract

        if contract:
            is_valid, violation_id, violation_reason = InvariantVerifier.verify(
                contract, tool_name, tool_args, state
            )
            if not is_valid:
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    policy_id=violation_id or "CONTRACT-VIOLATION",
                    reason=violation_reason or "违背会话语义安全不变量契约"
                )

        # 1. 规则 1: 敏感系统路径写入阻断 (fs.write) 与工作区关键配置不可篡改 (CVE-2025-53773)
        if tool_name in ["fs.write", "fs_write"]:
            target_path = str(tool_args.get("path", "") or tool_args.get("file", ""))
            for p in self.policies:
                pid = p.get("id")
                if pid in ["POL-FS-WRITE-SENSITIVE", "POL-FS-CONFIG-IMMUTABLE"]:
                    pattern = p.get("target_path_regex", "")
                    if pattern and re.search(pattern, target_path, re.IGNORECASE):
                        return ActionVerdict(
                            verdict=VerdictType.BLOCK,
                            policy_id=pid,
                            reason=f"阻断写入关键受限路径: {target_path} ({p.get('reason', '')})"
                        )

        # 2. 规则 2: 敏感凭证跨轮与分片外发拦截 (net.fetch)
        if tool_name in ["net.fetch", "net_fetch"]:
            url = str(tool_args.get("url", ""))
            body = str(tool_args.get("body", "") or tool_args.get("data", ""))
            target_domain = (urlsplit(url).hostname or "").lower()

            # 白名单检查
            trusted = state.effective_permissions.get("trusted_domains", [])
            for p in self.policies:
                if p.get("id") == "POL-NET-SECRET-EXFIL":
                    trusted = trusted + p.get("trusted_domains", [])
            is_trusted = any(target_domain == td.lower() or target_domain.endswith("." + td.lower()) for td in trusted) if target_domain else False

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
        if tool_name in ["exec", "exec_cmd"]:
            ast_info = extracted.ast_info or {}
            if ast_info.get("has_pipe_to_interpreter"):
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    policy_id="POL-EXEC-RESTRICT",
                    reason="AST 语法分析检出危险管道到解释器执行流 (如 curl | bash)"
                )
            dangerous_binaries = ast_info.get("dangerous_binaries", [])
            blocked_binaries = ["curl", "wget", "nc", "netcat", "bash", "sh"]
            for b in dangerous_binaries:
                if b in blocked_binaries:
                    return ActionVerdict(
                        verdict=VerdictType.BLOCK,
                        policy_id="POL-EXEC-RESTRICT",
                        reason=f"禁止调用高危外部传输与下载工具: {b}"
                    )

        # 4. 规则 4: 代码检视任务越权推送拦截 (git.push)
        if tool_name in ["git.push", "git_push"]:
            if state.initial_task_type in ["code_review", "review", "audit"]:
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    policy_id="POL-GIT-REVIEW-NO-PUSH",
                    reason="用户初始任务被锁定为代码检视 (code_review)，严禁执行 git.push"
                )

        # 5. 规则 5: 子 Agent 凭证渗透拦截 (spawn_subagent)
        if tool_name in ["spawn_subagent"]:
            sub_prompt = str(tool_args.get("prompt", "") or tool_args.get("task", ""))
            is_match, _, match_desc = self.check_secrets_and_chunks(state, sub_prompt)
            if is_match:
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    policy_id="POL-SUBAGENT-SECRET-LEAK",
                    reason=f"阻断向子 Agent 渗透主会话敏感凭证: {match_desc}"
                )

        # 6. 特权破坏性操作触发 ASK 询问 (fs.delete)
        if tool_name in ["fs.delete", "fs_delete", "fs.remove"]:
            token_id = secrets.token_urlsafe(32)
            args_hash = canonical_args_hash(tool_args)
            token = ApprovalToken(token_id=token_id, call_id=call_id, args_hash=args_hash)
            return ActionVerdict(
                verdict=VerdictType.ASK,
                policy_id="POL-FS-DELETE-ASK",
                reason="待删除文件操作具有破坏性，挂起请求等待操作员确认",
                approval_token=token
            )

        # 7. 规则 7: 记忆库休眠投毒拦截 (memory.write)
        if tool_name in ["memory.write", "memory.store"]:
            content = str(tool_args.get("content", "") or tool_args.get("value", ""))
            dormant_patterns = [
                r"当用户下次", r"下次提到", r"下次部署时", r"whenever the user",
                r"in future sessions", r"trigger on", r"secretly send"
            ]
            if any(re.search(p, content, re.IGNORECASE) for p in dormant_patterns):
                return ActionVerdict(
                    verdict=VerdictType.BLOCK,
                    policy_id="POL-MEMORY-DORMANT-DEFENSE",
                    reason="检测到向记忆库写入包含条件唤醒特征的休眠投毒载荷"
                )

        # 8. 快镜初筛与慢镜深度裁判升级
        fast_signals = extracted.fast_mirror_signals
        risk_score = fast_signals.get("risk_score", 0.0)
        action_compliance = fast_signals.get("action_compliance", "expected")
        text_nature = fast_signals.get("text_nature", "informational")

        # 当快镜标出越权、强指令诱导或高风险分
        if getattr(self, "enable_slow_mirror", True) and (risk_score >= 0.5 or action_compliance == "deviant" or text_nature == "directive"):
            evidence = EvidencePack(
                initial_task=state.initial_task,
                effective_permissions=state.effective_permissions,
                proposed_action={"tool_name": tool_name, "tool_args": tool_args},
                taint_snippet=event.raw_content[:600],
                matched_secrets=list(state.read_secrets.keys()) if self.enable_state_aggregation else [],
                call_id=call_id
            )
            slow_res = self.slow_mirror.judge(evidence, redactor=self.outbound_redactor_provider() if self.outbound_redactor_provider else OutboundRedactor.from_state(state))
            slow_verdict_str = slow_res.get("verdict", "ASK")
            verdict_type = VerdictType(slow_verdict_str)

            if verdict_type == VerdictType.ASK:
                token_id = secrets.token_urlsafe(32)
                args_hash = canonical_args_hash(tool_args)
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

            return ActionVerdict(verdict=VerdictType.ALLOW, reason=slow_res.get("reason", "慢镜放行"), evidence_summary=slow_res)

        # 9. 常规安全操作放行
        return ActionVerdict(
            verdict=VerdictType.ALLOW,
            reason="常规安全操作，快速放行"
        )
