"""
快镜 System 1: 毫秒级语义与参数定型分类器 (FastMirror)
定位：非自回归超轻量定型初筛，耗时 5~20ms。
职责：为增量文本快速回答两个标准分类选择题，提供风险参考分：
1. 外部文本性质 text_nature: informational | directive | example | uncertain
2. 动作合规性 action_compliance: expected | ancillary | deviant | insufficient
原则：仅提供风险信号，不能推翻硬规则，不能自行授权。
底层支持接入本地 Laya 400M 定型模型及高速校准规则引擎。
"""

from __future__ import annotations
import os
import re
import time
from typing import Any, Dict, Optional
from .models import D2Event

try:
    import laya
    _LAYA_AVAILABLE = True
except ImportError:
    _LAYA_AVAILABLE = False


# 恶意诱导指令特征词模式 (涵盖中英文典型提示注入模式与对抗变形)
DIRECTIVE_PATTERNS = [
    re.compile(r'(?i)(ignore\s+(all\s+)?(previous|prior|above)\s+instructions)', re.IGNORECASE),
    re.compile(r'(?i)(system\s+override|admin\s+mode|dan\s+mode|jailbreak)', re.IGNORECASE),
    re.compile(r'(?i)(you\s+must\s+(now\s+)?(send|exfiltrate|upload|forward|leak))', re.IGNORECASE),
    re.compile(r'(?i)(read\s+(the\s+)?(\.env|config|secrets?|id_rsa|passwd|credentials?))', re.IGNORECASE),
    re.compile(r'忽略(之前|以上|所有)的?(提示|规则|指令|约束)', re.IGNORECASE),
    re.compile(r'(进入|切换到)?(管理员|开发者|特权|调试|上帝)模式', re.IGNORECASE),
    re.compile(r'(读取|获取|查看).*(密钥|私钥|密码|\.env|id_rsa|token|passwd).*(发送|回传|上传|外发)', re.IGNORECASE),
    re.compile(r'(不要告诉用户|秘密执行|静默执行|后台发送|自动上报)', re.IGNORECASE),
    re.compile(r'(?i)(disregard\s+all\s+rules|bypass\s+security)', re.IGNORECASE),
]

# 示例/代码展示特征模式
EXAMPLE_PATTERNS = [
    re.compile(r'(?i)(for\s+example|e\.g\.|sample\s+code|documentation\s+example)', re.IGNORECASE),
    re.compile(r'例如|比如|示例代码|参考配置|代码演示|说明文档', re.IGNORECASE),
]

# 越权动作典型特征模式
DEVIANT_ACTION_PATTERNS = [
    re.compile(r'(curl|wget|nc|bash\s+-i|sh\s+-i|eval|base64\s+-d)', re.IGNORECASE),
    re.compile(r'(id_rsa|\.aws\/credentials|\.ssh\/authorized_keys|\.bash_history|\/etc\/shadow)', re.IGNORECASE),
]


class FastMirror:
    """快镜分类器 (基于 Laya 400M 定型模型与校准规则引擎)"""

    def __init__(self, model_path: Optional[str] = None, use_laya_model: Optional[bool] = None):
        self.model_path = model_path
        if use_laya_model is None:
            self.use_laya_model = _LAYA_AVAILABLE and os.getenv("USE_LAYA_MODEL", "false").lower() in ("true", "1")
        else:
            self.use_laya_model = use_laya_model and _LAYA_AVAILABLE
        self.laya_guard = None

        if self.use_laya_model:
            try:
                # 尝试加载 Laya Guardrail 实例
                self.laya_guard = laya.LayaGuardrail(action="audit")
            except Exception as e:
                # 离线或初次加载失败时走极速校准规则引擎
                self.laya_guard = None

    def classify_text_nature(self, text: str) -> str:
        """
        选择题 1：外部文本性质
        返回: 'directive' | 'example' | 'informational' | 'uncertain'
        """
        if not text or len(text.strip()) == 0:
            return "uncertain"

        # 1. 检查强指令诱导与注入特征模式
        for pattern in DIRECTIVE_PATTERNS:
            if pattern.search(text):
                return "directive"

        # 2. 检查是否属于示例
        for pattern in EXAMPLE_PATTERNS:
            if pattern.search(text):
                return "example"

        # 3. 正常业务或技术文档
        if len(text) > 20:
            return "informational"

        return "uncertain"

    def classify_action_compliance(
        self,
        tool_name: Optional[str],
        tool_args: dict,
        initial_task: str,
        text_nature: str
    ) -> str:
        """
        选择题 2：动作合规性
        结合当前动作与初始任务判断：
        返回: 'expected' | 'ancillary' | 'deviant' | 'insufficient'
        """
        if not tool_name:
            return "insufficient"

        args_str = str(tool_args).lower()

        # 检查是否包含越权高危特征
        for pattern in DEVIANT_ACTION_PATTERNS:
            if pattern.search(args_str):
                return "deviant"

        # 若外部文本性质为强指令诱导，且动作涉及网络外发或敏感读写
        if text_nature == "directive" and tool_name in ["net.fetch", "net_fetch", "exec", "exec_cmd", "fs.write", "spawn_subagent"]:
            return "deviant"

        # 检查是否与用户初始任务严重偏离
        task_lower = (initial_task or "").lower()
        if any(w in task_lower for w in ["review", "检视", "审查", "audit", "只读"]):
            if tool_name in ["git.push", "git_push", "net.fetch", "net_fetch", "fs.write"]:
                return "deviant"

        if tool_name in ["fs.read", "fs_read", "git.status", "git.log"]:
            return "expected"

        return "ancillary"

    def assess_event(self, event: D2Event, initial_task: str = "") -> Dict[str, Any]:
        """
        对单条增量事件进行快镜定型评估
        设计目标耗时: 5 ~ 20ms
        """
        start_t = time.perf_counter()

        text = event.raw_content
        text_nature = self.classify_text_nature(text)
        action_compliance = self.classify_action_compliance(
            event.tool_name,
            event.tool_args,
            initial_task,
            text_nature
        )

        laya_signals = {}
        # 若已加载 Laya 实例，并行提取模型信号
        if self.laya_guard and text:
            try:
                # Laya 毫秒级快速推理
                laya_res = self.laya_guard.invoke(text[:500])
                if isinstance(laya_res, dict):
                    laya_signals = {
                        "is_injection": laya_res.get("prompt_injection", False),
                        "is_jailbreak": laya_res.get("jailbreak", False),
                        "has_sensitive": laya_res.get("sensitive_data", False)
                    }
                    if laya_signals.get("is_injection") or laya_signals.get("is_jailbreak"):
                        text_nature = "directive"
            except Exception:
                pass

        # 综合计算风险参考分 (0.0 - 1.0)
        risk_score = 0.0
        if text_nature == "directive":
            risk_score += 0.5
        if action_compliance == "deviant":
            risk_score += 0.5
        elif action_compliance == "ancillary" and text_nature == "directive":
            risk_score += 0.3

        risk_score = min(1.0, risk_score)
        latency_ms = (time.perf_counter() - start_t) * 1000.0

        return {
            "backend": "laya" if laya_signals else "rules",
            "text_nature": text_nature,
            "action_compliance": action_compliance,
            "risk_score": risk_score,
            "laya_signals": laya_signals,
            "latency_ms": latency_ms
        }
