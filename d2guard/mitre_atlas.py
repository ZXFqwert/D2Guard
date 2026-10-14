"""
MITRE ATLAS (Adversarial Threat Landscape for AI Systems) 智能体威胁矩阵映射中枢
定位：
将智能体受到的提示注入与工具滥用行为实时对齐到国际权威的 MITRE ATLAS 矩阵，
赋能 D²Guard 从单一防御脚本升维为企业级智能体安全运营中心 (Agent-SOC / SIEM)。
支持的 MITRE ATLAS 核心技术项：
1. AML.T0051: LLM Prompt Injection (直接提示注入、间接提示注入、多语言/注释对抗绕过)
2. AML.T0054: LLM Jailbreak (特权模式伪装、绕过安全审查)
3. AML.T0057: LLM Data Exfiltration (机密凭证窃取、多轮分片隐蔽外发)
4. AML.T0043: Craft Adversarial Data (MCP 工具描述投毒、长期记忆库休眠投毒)
5. AML.T0047: ML-Enabled Tool Abuse (工作区配置篡改、终端管道逃逸、越权 Git 推送)
6. AML.T0048: Execution via API / Multi-Agent (多智能体凭证渗透、横向移动)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AtlasTechnique:
    technique_id: str
    tactic: str           # Initial Access, Execution, Persistence, Exfiltration, Defense Evasion
    name: str
    description: str
    severity: str         # LOW, MEDIUM, HIGH, CRITICAL


ATLAS_DATABASE: Dict[str, AtlasTechnique] = {
    "AML.T0051": AtlasTechnique(
        technique_id="AML.T0051",
        tactic="Initial Access / Evasion",
        name="LLM 提示注入 (Prompt Injection)",
        description="攻击者利用恶意自然语言提示词破坏模型指令边界，包括网页间接注入与代码注释注入。",
        severity="HIGH"
    ),
    "AML.T0054": AtlasTechnique(
        technique_id="AML.T0054",
        tactic="Defense Evasion",
        name="模型越狱与角色伪装 (LLM Jailbreak)",
        description="攻击者通过管理员身份伪装、模式切换提示词绕过智能体的前置系统安全设定。",
        severity="HIGH"
    ),
    "AML.T0057": AtlasTechnique(
        technique_id="AML.T0057",
        tactic="Exfiltration",
        name="大模型数据隐蔽外泄 (LLM Data Exfiltration)",
        description="智能体在外部诱导下通过网络工具将本地敏感凭据、数据库配置以明文、Base64 或滑动切片外发。",
        severity="CRITICAL"
    ),
    "AML.T0043": AtlasTechnique(
        technique_id="AML.T0043",
        tactic="Persistence / Ingestion",
        name="对抗性数据构造 (Craft Adversarial Data)",
        description="攻击者构造带有恶意提示载荷的文档、代码、PR 或知识库记录，诱导智能体解析并触发攻击。",
        severity="HIGH"
    ),
    "AML.T0110": AtlasTechnique(
        technique_id="AML.T0110",
        tactic="Initial Access / Persistence",
        name="智能体工具链与描述投毒 (AI Agent Tool Poisoning)",
        description="恶意第三方 MCP 服务在 tools/list 描述或参数模式中嵌入隐蔽指令，劫持智能体工具选择与参数生成。",
        severity="CRITICAL"
    ),
    "AML.T0047": AtlasTechnique(
        technique_id="AML.T0047",
        tactic="Execution",
        name="智能体工具滥用 (ML-Enabled Tool Abuse)",
        description="越权触发高危破坏性系统工具，如通过 curl | bash 执行反弹 Shell、覆写配置文件致 RCE (CVE-2025-53773)。",
        severity="CRITICAL"
    ),
    "AML.T0048": AtlasTechnique(
        technique_id="AML.T0048",
        tactic="Lateral Movement",
        name="多智能体 API 凭据渗透 (Multi-Agent Credential Leak)",
        description="主 Agent 将敏感认证信息、访问密钥跨进程传递给不可信后台子 Agent，导致横向权限扩散。",
        severity="MEDIUM"
    )
}


class AtlasThreatMapper:
    """ATLAS 威胁技术映射器"""

    @classmethod
    def map_policy_or_event(cls, policy_id: Optional[str], tool_name: Optional[str], reason: str) -> AtlasTechnique:
        """根据策略命中断言与工具动作，映射至 MITRE ATLAS 矩阵单元"""
        pid = (policy_id or "").upper()
        t_name = (tool_name or "").lower()
        r_text = reason.lower()

        # 1. 数据外发相关 -> AML.T0057
        if "NET" in pid or "EXFIL" in pid or "SECRET" in pid or "外发" in r_text or "分片" in r_text:
            return ATLAS_DATABASE["AML.T0057"]

        # 2. 工具滥用与关键配置篡改 / 命令逃逸 -> AML.T0047
        if "CONFIG-IMMUTABLE" in pid or "EXEC" in pid or "CVE-2025-53773" in r_text or "管道" in r_text or "authorized_keys" in r_text:
            return ATLAS_DATABASE["AML.T0047"]

        # 3. 智能体工具链投毒 (MCP) -> AML.T0110
        if "MCP" in pid or "mcp" in r_text or "mcp" in t_name:
            return ATLAS_DATABASE["AML.T0110"]

        # 3.1 长期记忆库休眠投毒 -> AML.T0043
        if "MEMORY" in pid or "休眠" in r_text or "投毒" in r_text:
            return ATLAS_DATABASE["AML.T0043"]

        # 4. 子 Agent 渗透扩散 -> AML.T0048
        if "SUBAGENT" in pid or "子 agent" in r_text or t_name == "spawn_subagent":
            return ATLAS_DATABASE["AML.T0048"]

        # 5. 代码推送越权 -> AML.T0047
        if "GIT" in pid or t_name in ["git.push", "git_push"]:
            return ATLAS_DATABASE["AML.T0047"]

        # 6. 默认提示注入 -> AML.T0051
        return ATLAS_DATABASE["AML.T0051"]

    @classmethod
    def get_matrix_status(cls, active_technique_ids: List[str]) -> List[Dict[str, Any]]:
        """输出给前端 SOC 态势大屏渲染的完整矩阵状态"""
        matrix = []
        for tech_id, item in ATLAS_DATABASE.items():
            is_active = tech_id in active_technique_ids
            matrix.append({
                "id": item.technique_id,
                "tactic": item.tactic,
                "name": item.name,
                "description": item.description,
                "severity": item.severity,
                "active": is_active
            })
        return matrix
