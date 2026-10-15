"""YAML-driven hard policies. Mirrors explain evidence but cannot override them."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote

import yaml
from pydantic import BaseModel, ConfigDict, Field

from config import ASSETS, CONTRACT, ROOT
from execution import analyze_command, command_name, exec_violation
from extractor import normalize
from mirrors import FastMirrorAdapter, SlowMirrorClient
from models import ActionVerdict, ProposedAction, SecurityState, Verdict
from state_machine import (
    domain_of, full_secret_match, is_trusted, matches_for, payload_views,
    record_outbound, register_call, trace_action, unique_append,
)


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    tools: list[str] = Field(min_length=1)
    sensitive_components: list[str] = []
    path_patterns: list[str] = []
    trusted_domains: list[str] = []
    coverage_threshold: float = Field(default=.5, gt=0, le=.5)
    download_commands: list[str] = []
    execution_commands: list[str] = []
    blocked_environment_markers: list[str] = []
    locked_task_type: str = "code_review_readonly"


def normalized_path(value: str, root: Path) -> str:
    # Match Windows separators / device prefixes on either host OS, then resolve
    # native symlinks when the path is meaningful on this host.
    text = unquote(unquote(value)).replace("\\", "/")
    text, _ = normalize(text, decode_base64=False)
    text = text.removeprefix("//?/").removeprefix("/??/")
    text = text.replace("${HOME}", str(Path.home())).replace("$HOME", str(Path.home()))
    text = text.replace("%USERPROFILE%", str(Path.home())).replace("%HOME%", str(Path.home()))
    text = str(Path(text).expanduser()) if text.startswith("~") else text
    if not re.match(r"^[A-Za-z]:/|^/", text):
        text = str(root / text)
    if not (os.name == "nt" and text.startswith("/") and not text.startswith("//")):
        try:
            text = str(Path(text).resolve(strict=False))
        except (OSError, ValueError):
            pass
    # Win32 ignores trailing spaces/dots and allows ADS via ':'.
    text = posixpath.normpath(text.replace("\\", "/"))
    parts = [p.rstrip(" .").split(":", 1)[0] if i > 0 else p for i, p in enumerate(text.split("/"))]
    return posixpath.normpath("/".join(parts)).casefold()


class PolicyEngine:
    def __init__(self, policy_path: Path = ASSETS / "policies.yaml", execution_root: Path = ROOT,
                 fast: FastMirrorAdapter | None = None, slow: SlowMirrorClient | None = None):
        data = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"version", "rules"} or data["version"] != 1:
            raise ValueError("invalid policy document")
        rules = [PolicyRule.model_validate(rule) for rule in data["rules"]]
        expected = {rule["id"] for rule in CONTRACT["policies_required"]}
        if len(rules) != 5 or {rule.id for rule in rules} != expected:
            raise ValueError("exactly the five contract policies must be configured")
        self.rules = {rule.id: rule.model_dump() for rule in rules}
        required_tools = {p["id"]: {p["tool"]} for p in CONTRACT["policies_required"]}
        required_tools["POL-GIT-REVIEW-NO-PUSH"].add("git.commit")
        for rule in rules:
            if not required_tools[rule.id] <= set(rule.tools):
                raise ValueError("required policy tools cannot be removed")
        self.root = execution_root.resolve()
        self.fast, self.slow = fast or FastMirrorAdapter(), slow or SlowMirrorClient()

    def hard_check(self, state: SecurityState, action: ProposedAction) -> tuple[str | None, str]:
        args, tool = action.tool_args, action.tool_name
        fs = self.rules["POL-FS-WRITE-SENSITIVE"]
        if tool in fs["tools"]:
            path = args.get("path")
            if not isinstance(path, str) or not path or "\x00" in path:
                return fs["id"], "文件写入路径缺失或无效"
            path = normalized_path(path, self.root)
            components = path.split("/")
            if any(c in components for c in fs["sensitive_components"]) or any(fnmatch.fnmatchcase(path, p) for p in fs["path_patterns"]):
                return fs["id"], "禁止写入凭证目录、计划任务或系统自启动目录"
        net = self.rules["POL-NET-SECRET-EXFIL"]
        if tool in net["tools"]:
            try:
                domain = domain_of(args)
            except ValueError:
                return net["id"], "外发请求 URL 无效，无法核验目标域名"
            if not is_trusted(domain, net["trusted_domains"]):
                views = payload_views(args)
                full = any(full_secret_match(secret, views) for secret in state.secret_ledger)
                coverage = state.accumulated_outbound.get(domain)
                if full or (coverage and coverage.coverage_ratio >= net["coverage_threshold"]):
                    return net["id"], "非白名单域名请求包含已登记敏感数据，或单域名累计分片覆盖率达到阈值"
        git = self.rules["POL-GIT-REVIEW-NO-PUSH"]
        readonly = bool(state.anchor_intent and state.anchor_intent.task_type == git["locked_task_type"])
        if tool in git["tools"] and readonly:
            return git["id"], "首帧锚点为只读代码检视，禁止提交或推送仓库"
        execution = self.rules["POL-EXEC-RESTRICT"]
        if tool in execution["tools"]:
            command = args.get("command", args.get("cmd"))
            if not isinstance(command, str):
                return execution["id"], "exec 必须提供可审计的 command/cmd 字符串"
            for argv in analyze_command(command).commands:
                if not argv:
                    continue
                name = command_name(argv[0])
                if name in set(execution["download_commands"]):
                    views = payload_views(args)
                    if any(full_secret_match(s, views) or any(matches_for(s, views).values()) for s in state.secret_ledger):
                        return execution["id"], "exec 下载客户端参数包含敏感数据，必须通过 net.fetch 核验外发"
                if name in {"touch", "cp", "mv", "mkdir", "install", "ln", "sed", "rm", "copy", "move", "del", "set-content", "add-content", "new-item", "out-file"}:
                    for word in argv[1:]:
                        if word.startswith("-"):
                            continue
                        virtual = action.model_copy(update={"tool_name": "fs.write", "tool_args": {"path": word}})
                        matched, _ = self.hard_check(state, virtual)
                        if matched:
                            return execution["id"], "exec 尝试变更敏感路径，必须通过受审计的 fs.write"
            violation = exec_violation(command, execution, readonly=readonly)
            if violation:
                if readonly and "git.push/git.commit" in violation:
                    return git["id"], violation
                return execution["id"], violation
        sub = self.rules["POL-SUBAGENT-SECRET-LEAK"]
        if tool in sub["tools"]:
            views = payload_views(args)
            if any(full_secret_match(secret, views) or any(matches_for(secret, views).values()) for secret in state.secret_ledger):
                return sub["id"], "子任务参数包含已登记凭证或敏感分片，禁止跨 Agent 传递"
        return None, "未命中强制阻断策略"

    def decide(self, state: SecurityState, proposed_action: ProposedAction, *, review: bool = True) -> ActionVerdict:
        action = proposed_action
        register_call(state, action, "TOOL_PRE_EXEC")
        if action.tool_name == "net.fetch":
            try:
                record_outbound(state, action.tool_args)
            except ValueError:
                pass
        policy, reason = self.hard_check(state, action)
        text, _ = normalize(str(action.tool_args))
        label = self.fast.classify(text, action.current_plan)
        evidence = state.evidence_by_agent.get(action.agent_id)
        if evidence and (evidence.fast_mirror_label.content_nature == "directive" or evidence.fast_mirror_label.action_alignment == "deviant"):
            label = evidence.fast_mirror_label
        suspicious = label.content_nature == "directive" or label.action_alignment == "deviant"
        if not state.armor_enabled:
            verdict, risk, reason = Verdict.ALLOW, .05, "护甲已关闭；动作已记录审计，按裸机模式放行"
        elif policy:
            verdict, risk = Verdict.BLOCK, .98
        elif suspicious or state.anchor_intent is None:
            verdict, risk = Verdict.ASK, .65
            reason = "检测到指令性或偏离锚点的证据，需要用户确认" if suspicious else "尚无可信用户首帧锚点，需要用户确认"
        else:
            verdict, risk = Verdict.ALLOW, .05
        triggered = bool(state.armor_enabled and (suspicious or policy))
        # Local evidence always supplies the complete report, even offline.
        # Never include request bodies, commands or credential values in reports.
        target = str(action.tool_args.get("path", action.tool_args.get("remote", "")))
        if action.tool_name == "net.fetch":
            try:
                target = domain_of(action.tool_args)
            except ValueError:
                target = "无效目标域名"
        for secret in state.secret_ledger:
            target = target.replace(secret.plaintext, "[凭据已脱敏]")
        anchor = state.anchor_intent.initial_task if state.anchor_intent else "尚未建立可信用户任务"
        report = (f"用户原始任务意图：{anchor} -> 实际违规动作/待审动作：{action.tool_name} {target} "
                  f"-> 污染源定位：{evidence.source_uri if evidence else '当前工具请求'}，"
                  f"字符区间 {evidence.char_span if evidence else (0, 0)}，"
                  f"Token 区间 {evidence.token_span if evidence else (0, 0)} "
                  f"-> 判定结论：{verdict.value}。{reason}。" + (f"规则依据：{policy}。" if policy else ""))
        trace_action(state, action, verdict)
        if verdict == Verdict.BLOCK:
            if action.tool_name == "net.fetch":
                try:
                    domain = domain_of(action.tool_args)
                    state.accumulated_outbound[domain].blocked = True
                    unique_append(state.impact_scope.blocked_domains, domain)
                except ValueError:
                    pass
            elif action.tool_name in {"git.push", "git.commit"}:
                repo = str(action.tool_args.get("repo", action.tool_args.get("remote", "origin/main")))
                unique_append(state.impact_scope.blocked_git_repos, repo)
            elif action.tool_name == "fs.write":
                unique_append(state.impact_scope.protected_files, str(action.tool_args.get("path", "")))
        result = ActionVerdict(call_id=action.call_id, verdict=verdict, risk_score=risk,
                             matched_policy_id=policy, fast_mirror_label=label,
                             slow_mirror_triggered=triggered, explainable_report=report, approval_token=None,
                             source_uri=evidence.source_uri if evidence else "",
                             char_span=evidence.char_span if evidence else (0, 0),
                             token_span=evidence.token_span if evidence else (0, 0))
        if review:
            self.enrich_report(state, result)
        return result

    def enrich_report(self, state: SecurityState, result: ActionVerdict):
        if result.slow_mirror_triggered:
            ratio = max((r.coverage_ratio for r in state.accumulated_outbound.values()), default=0)
            result.explainable_report = self.slow.review({
                "verdict": result.verdict.value, "matched_policy_id": result.matched_policy_id,
                "content_nature": result.fast_mirror_label.content_nature.value,
                "action_alignment": result.fast_mirror_label.action_alignment.value,
                "coverage_ratio": ratio,
                "anchor_type": state.anchor_intent.task_type if state.anchor_intent else "unknown",
            }, result.explainable_report)


def decide(state: SecurityState, proposed_action: ProposedAction) -> ActionVerdict:
    return PolicyEngine().decide(state, proposed_action)
