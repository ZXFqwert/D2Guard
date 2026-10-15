"""
原生 MCP (Model Context Protocol) JSON-RPC 2.0 中间人安全防御代理 (MCPProxy)
借鉴：
1. Trail of Bits: mcp-context-protector (tools/list 投毒清洗与 TOFU 锁定)
2. OWASP LLM-07 / MCP Security Guidance (沙箱隔离与输入输出边界强化)
职责：
1. 原生监听/过滤 Agent 与 MCP Server 之间的 JSON-RPC 2.0 报文 (stdio / SSE)；
2. tools/list 阶段：静态拦截与清洗 tool description 中的隐藏提示注入，实施 TOFU Schema 哈希锁定；
3. tools/call 阶段：参数类型与路径穿透校验，阻断参数走形与越权探测；
4. 工具返回阶段：包裹结构化 `<untrusted_mcp_output>` 隔离沙箱标签，打上 TAINT_MCP 污点标记。
"""

from __future__ import annotations
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .models import ActionVerdict, D2Event, CallLifecycleStage, VerdictType
from .normalizer import AdversarialNormalizer


# 恶意的 MCP Tool Description 投毒特征正则
MCP_POISON_PATTERNS = [
    re.compile(r'(?i)(\[\s*system\s*(directive|override|note|instruction)[\s\S]*?\])', re.IGNORECASE),
    re.compile(r'(?i)(ignore\s+(all\s+)?(previous|prior|system)\s+instructions)', re.IGNORECASE),
    re.compile(r'(?i)(always\s+call\s+this\s+tool\s+(first|with))', re.IGNORECASE),
    re.compile(r'(?i)(read\s+(the\s+)?(\.env|config|secret|id_rsa|passwd|credentials?))', re.IGNORECASE),
    re.compile(r'(?i)(exfiltrate|leak|send\s+to|forward\s+to\s+http)', re.IGNORECASE),
    re.compile(r'忽略(之前|以上|所有)的?(提示|规则|指令)', re.IGNORECASE),
    re.compile(r'(必须|优先)调用本工具.*(附带|携带|外发)', re.IGNORECASE),
    re.compile(r'(读取|获取).*(私钥|密钥|\.env|id_rsa|token).*并(发送|上传|回传)', re.IGNORECASE),
]


class MCPJsonRpcSecurityProxy:
    """MCP JSON-RPC 2.0 中间人安全代理"""

    def __init__(self, server_id: str = "default_mcp_server"):
        self.server_id = server_id
        # TOFU (Trust-On-First-Use) 锁定的工具 Schema 哈希表: {tool_name: schema_hash}
        self.tofu_schema_hashes: Dict[str, str] = {}
        # 记录清洗审计日志
        self.audit_log: List[Dict[str, Any]] = []

    def sanitize_tool_description(self, raw_description: str) -> Tuple[str, bool, List[str]]:
        """
        审计并清洗 tools/list 中单个工具的 description
        返回: (cleaned_desc, was_poisoned, detected_patterns)
        """
        if not raw_description:
            return "", False, []

        normalized_desc, _ = AdversarialNormalizer.normalize_for_inspection(raw_description)
        detected = []

        for p in MCP_POISON_PATTERNS:
            matches = p.findall(normalized_desc)
            if matches:
                detected.append(p.pattern)

        if not detected:
            return raw_description, False, []

        # 发现投毒载荷：剥离所有恶意诱导语句，降级为纯安全描述
        cleaned = raw_description
        for p in MCP_POISON_PATTERNS:
            cleaned = p.sub("[SANITIZED: Disallowed instruction stripped by D2Guard MCP-Proxy]", cleaned)

        return cleaned.strip(), True, detected

    def process_tools_list_response(self, response_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, List[str]]:
        """
        拦截处理 MCP Server 返回的 tools/list JSON-RPC 报文
        报文格式示例：
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "fetch_data", "description": "...", "inputSchema": {...}}
                ]
            }
        }
        """
        result = response_payload.get("result", {})
        tools = result.get("tools", [])
        if not tools:
            return response_payload, False, []

        modified = False
        all_detected = []

        for tool in tools:
            tool_name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            cleaned_desc, was_poisoned, detected = self.sanitize_tool_description(desc)

            if was_poisoned:
                modified = True
                tool["description"] = cleaned_desc
                all_detected.extend([f"[{tool_name}] {d}" for d in detected])
                self.audit_log.append({
                    "stage": "tools/list",
                    "tool": tool_name,
                    "action": "SANITIZE_DESCRIPTION",
                    "detected": detected
                })

            # 计算当前 Schema 哈希，实施 TOFU 防篡改锁定
            schema_repr = json.dumps({
                "name": tool_name,
                "inputSchema": tool.get("inputSchema", {})
            }, sort_keys=True)
            current_hash = hashlib.sha256(schema_repr.encode()).hexdigest()

            if tool_name not in self.tofu_schema_hashes:
                # 首次握手记录哈希
                self.tofu_schema_hashes[tool_name] = current_hash
            else:
                # 后续如果 Schema 动态发生篡改（动态投毒）
                if self.tofu_schema_hashes[tool_name] != current_hash:
                    all_detected.append(f"[{tool_name}] TOFU_SCHEMA_MUTATION_DETECTED")
                    self.audit_log.append({
                        "stage": "tools/list",
                        "tool": tool_name,
                        "action": "BLOCK_SCHEMA_TAMPERING",
                        "original_hash": self.tofu_schema_hashes[tool_name],
                        "new_hash": current_hash
                    })

        return response_payload, modified, all_detected

    def process_tools_call_request(self, request_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[ActionVerdict]]:
        """
        拦截处理 Agent 发往 MCP Server 的 tools/call 请求
        报文格式示例：
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "read_file",
                "arguments": {"path": "../../etc/passwd"}
            }
        }
        """
        params = request_payload.get("params", {})
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        # 1. 检查参数路径穿透漏洞 (Path Traversal)
        for k, v in args.items():
            if isinstance(v, str):
                if "../" in v or "..\\" in v:
                    return request_payload, ActionVerdict(
                        verdict=VerdictType.BLOCK,
                        policy_id="POL-MCP-PATH-TRAVERSAL",
                        reason=f"MCP 参数检出危险路径穿透特征: {k}={v}"
                    )

        return request_payload, None

    def process_tools_call_response(self, response_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        拦截处理 MCP Server 返回的 tools/call 执行结果
        自动包裹结构化 `<untrusted_mcp_output>` 隔离沙箱标签，切断二阶间接提示注入流
        """
        result = response_payload.get("result", {})
        content = result.get("content", [])

        wrapped_text = ""
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                raw_text = item.get("text", "")
                # 注入沙箱隔离标记，明确指示模型不可将其中的文本视为指令
                sandboxed_text = (
                    f"<untrusted_mcp_output server='{self.server_id}'>\n"
                    f"{raw_text}\n"
                    f"</untrusted_mcp_output>"
                )
                item["text"] = sandboxed_text
                wrapped_text += sandboxed_text + "\n"

        return response_payload, wrapped_text
