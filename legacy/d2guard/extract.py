"""
接口一：extract(event) -> ExtractedData
职责划分：
1. 代码确定性提取：文件路径、URL域名、bashlex AST 语法分析、敏感凭证与私钥正则扫描；
2. 字符区间与 Token 序号映射；
3. 快镜 Laya 初筛：回答文本性质与动作合规性两大定型选择题；
4. 严格将实际观察事实与模型主观推测分开存储。
"""

from __future__ import annotations
import re
import urllib.parse
from typing import Any, Dict, List, Optional
import bashlex

from .models import D2Event, ExtractedData
from .normalizer import AdversarialNormalizer
from .fast_mirror import FastMirror


# 常见私钥与敏感 Token 正则模式
SECRET_REGEXES = [
    re.compile(r'sk-[a-zA-Z0-9_\-]{20,}', re.IGNORECASE),                         # OpenAI / LLM API key
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----'), # RSA/EC 私钥
    re.compile(r'AKIA[0-9A-Z]{16}'),                                             # AWS Access Key
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),                                          # GitHub Personal Token
    re.compile(r'(?i)api[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{16,})'),   # 通用 API Key
    re.compile(r'(?i)password["\']?\s*[:=]\s*["\']?([^\s"\'&]+)'),               # 密码字段
]

# URL 与域名提取正则
URL_REGEX = re.compile(r'https?://([a-zA-Z0-9.\-]+(?::[0-9]+)?)')

# 路径提取常见字段名
PATH_KEYS = {"path", "file", "filepath", "filename", "target_path", "source_path", "dest_path"}


def parse_bash_ast(command_str: str) -> Dict[str, Any]:
    """
    使用 bashlex 对 shell 命令行进行抽象语法树 (AST) 解析
    检测：
    1. 危险二元管道 (例如 curl | bash)
    2. 命令替换 (例如 `cmd` 或 $(cmd))
    3. 调用高危二进制 (curl, wget, nc, bash, sh)
    4. 环境变量引用
    """
    ast_info = {
        "is_valid_bash": True,
        "dangerous_binaries": [],
        "has_pipe_to_interpreter": False,
        "has_command_substitution": False,
        "env_var_expansions": []
    }
    
    if not command_str or not command_str.strip():
        return ast_info

    try:
        parts = bashlex.parse(command_str)
    except Exception:
        # 非标 bash 命令，标记为无法完全解析但继续字符串检查
        ast_info["is_valid_bash"] = False
        # 降级模式检测
        lower = command_str.lower()
        if "|" in lower and any(x in lower for x in ["bash", "sh", "python"]):
            ast_info["has_pipe_to_interpreter"] = True
        for b in ["curl", "wget", "nc", "bash", "sh"]:
            if re.search(rf'\b{b}\b', lower):
                ast_info["dangerous_binaries"].append(b)
        return ast_info

    interpreters = {"bash", "sh", "python", "python3", "perl", "ruby"}
    downloaders = {"curl", "wget", "nc", "netcat"}

    def walk_node(node):
        kind = getattr(node, 'kind', None)
        
        # 检查 pipeline
        if kind == 'pipeline':
            # 检查是否有下载工具管道传递到解释器
            cmds = getattr(node, 'parts', [])
            has_dl = False
            for c in cmds:
                c_words = [getattr(w, 'word', '') for w in getattr(c, 'parts', []) if getattr(w, 'kind', '') == 'word']
                if c_words and c_words[0] in downloaders:
                    has_dl = True
                if c_words and c_words[0] in interpreters and has_dl:
                    ast_info["has_pipe_to_interpreter"] = True

        # 检查命令调用
        if kind == 'command':
            words = [getattr(w, 'word', '') for w in getattr(node, 'parts', []) if getattr(w, 'kind', '') == 'word']
            if words:
                cmd_name = words[0].split('/')[-1]
                if cmd_name in (downloaders | interpreters):
                    if cmd_name not in ast_info["dangerous_binaries"]:
                        ast_info["dangerous_binaries"].append(cmd_name)

        # 检查命令替换 $(...) 或 `...`
        if kind in ('commandsubstitution', 'backquotes'):
            ast_info["has_command_substitution"] = True

        # 检查变量展开 $VAR
        if kind == 'parameter':
            var_value = getattr(node, 'value', '')
            if var_value:
                ast_info["env_var_expansions"].append(var_value)

        # 递归遍历子节点
        for child in getattr(node, 'parts', []):
            walk_node(child)

    for p in parts:
        walk_node(p)

    return ast_info


def char_to_token_span(text: str, char_start: int, char_end: int) -> tuple[int, int]:
    """
    轻量 Token 序号对齐映射器：
    将字符区间 (start, end) 映射为估计的 Token 编号区间。
    在无本地分词器权重时，基于空格与标点词元边界计算。
    """
    if not text:
        return (0, 0)
    tokens = list(re.finditer(r'\w+|[^\w\s]', text))
    token_start = 0
    token_end = 0
    found_start = False
    for i, t in enumerate(tokens):
        if not found_start and t.start() >= char_start:
            token_start = i
            found_start = True
        if t.end() <= char_end:
            token_end = i + 1
    return (token_start, max(token_start + 1, token_end))


class EventExtractor:
    """事实与语义抽取器"""

    def __init__(self, fast_mirror: Optional[FastMirror] = None):
        self.fast_mirror = fast_mirror or FastMirror()

    def extract(self, event: D2Event, initial_task: str = "") -> ExtractedData:
        """从增量事件中提取结构化事实与定型信号"""
        extracted = ExtractedData(event_id=event.event_id)

        # 1. 对抗样本标准化与展开候选
        cleaned_text, candidates = AdversarialNormalizer.normalize_for_inspection(event.raw_content)

        # 2. 提取路径
        paths = set()
        for k, v in event.tool_args.items():
            if k in PATH_KEYS and isinstance(v, str):
                paths.add(v)
            elif isinstance(v, str) and ("/" in v or "\\" in v or "." in v):
                # 检查是否为有效路径格式
                if len(v) < 260 and not v.startswith("http"):
                    paths.add(v)
        extracted.file_paths = list(paths)

        # 3. 提取域名与 URL
        domains = set()
        # 从工具参数提取
        for v in event.tool_args.values():
            if isinstance(v, str):
                for match in URL_REGEX.findall(v):
                    domains.add(match)
        # 从原始文本及展开候选提取
        for cand in candidates:
            for match in URL_REGEX.findall(cand):
                domains.add(match)
        extracted.domains = list(domains)

        # 4. AST 语法分析 (若为 exec 工具)
        if event.tool_name == "exec":
            cmd = event.tool_args.get("command", "") or event.tool_args.get("cmd", "")
            extracted.ast_info = parse_bash_ast(cmd)

        # 5. 正则扫描私钥与敏感凭证 (检查原始文本与解码后候选)
        found_secrets = set()
        for cand in candidates:
            for reg in SECRET_REGEXES:
                for match in reg.findall(cand):
                    secret_val = match if isinstance(match, str) else match[0]
                    if len(secret_val) >= 10:
                        found_secrets.add(secret_val)
        extracted.found_secrets = list(found_secrets)

        # 6. 计算 Token 偏移 (若提供字符跨度)
        if event.char_span != (0, 0):
            event.token_span = char_to_token_span(event.raw_content, event.char_span[0], event.char_span[1])

        # 7. 快镜初筛定型信号
        fast_signals = self.fast_mirror.assess_event(event, initial_task=initial_task)
        extracted.fast_mirror_signals = fast_signals

        return extracted
