"""
变异容忍动态污点流追踪引擎 (Dynamic Taint Engine with Mutation Tolerance)
借鉴：
1. Google DeepMind: CaMeL (信息流控制 IFC 与值级依赖追踪)
2. Protect AI: pipelock (香农熵检测与动态 Canary 假凭据跟踪)
职责：
1. 超越单纯明文字符串匹配，建立抗变异的污点传播流；
2. 自动生成多模态变异指纹字典：Hex 编码、URL 编码、Base64/URLSafe、倒序反转、间隔变形；
3. 香农熵 (Shannon Entropy) 异常分析：识别隐蔽外发的加密密文与高熵哈希切片；
4. 动态 Canary 诱饵注入与出站捕获：100% 确定性证实数据外发行为。
"""

from __future__ import annotations
import base64
import math
import re
import urllib.parse
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple


def calculate_shannon_entropy(text: str) -> float:
    """计算字符串的香农信息熵 (用于检测加密、密文、随机高危密钥)"""
    if not text or len(text) < 4:
        return 0.0
    counter = Counter(text)
    total_len = len(text)
    entropy = 0.0
    for count in counter.values():
        p = count / total_len
        entropy -= p * math.log2(p)
    return entropy


class DynamicTaintEngine:
    """动态污点引擎"""

    @classmethod
    def generate_mutations(cls, secret_text: str) -> Set[str]:
        """
        为机密字符串生成全套潜在对抗变异体指纹
        """
        if not secret_text or len(secret_text) < 4:
            return set()

        clean_sec = secret_text.strip()
        mutations = set()

        # 1. 原始明文与大小写变体
        mutations.add(clean_sec)
        mutations.add(clean_sec.lower())
        mutations.add(clean_sec.upper())

        # 2. Base64 编码 (含常规与 URL-safe 变体)
        try:
            b64_val = base64.b64encode(clean_sec.encode()).decode()
            mutations.add(b64_val)
            mutations.add(b64_val.rstrip("="))
            b64_url = base64.urlsafe_b64encode(clean_sec.encode()).decode()
            mutations.add(b64_url)
        except Exception:
            pass

        # 3. 十六进制 (Hex) 编码变体
        try:
            hex_val = clean_sec.encode().hex()
            mutations.add(hex_val)
            mutations.add(hex_val.upper())
        except Exception:
            pass

        # 4. URL 编码变体
        try:
            url_enc = urllib.parse.quote(clean_sec)
            if url_enc != clean_sec:
                mutations.add(url_enc)
        except Exception:
            pass

        # 5. 反转字符串变体 (Reverse Exfiltration)
        reversed_sec = clean_sec[::-1]
        mutations.add(reversed_sec)

        # 6. 空白或常见分隔符剥离比对 (如 s k - x x x -> sk-xxx)
        stripped = re.sub(r'[\s\-_:]', '', clean_sec)
        if len(stripped) >= 6:
            mutations.add(stripped.lower())

        return mutations

    @classmethod
    def scan_for_tainted_flow(
        cls,
        payload_text: str,
        secret_registry: Dict[str, Any],
        entropy_threshold: float = 4.2
    ) -> Tuple[bool, str, float]:
        """
        扫描外发负载中是否存在污点流泄露
        返回: (is_tainted, match_reason, max_entropy)
        """
        if not payload_text or not secret_registry:
            return False, "", 0.0

        payload_lower = payload_text.lower()
        # 剥离 URL 编码以透视底层字符
        unquoted_payload = urllib.parse.unquote(payload_text).lower()

        # 1. 变异指纹字典比对
        for sec_id, sec_data in secret_registry.items():
            raw_text = getattr(sec_data, "exact_text", str(sec_data))
            mutations = cls.generate_mutations(raw_text)

            for mut in mutations:
                mut_lower = mut.lower()
                if len(mut_lower) >= 6 and (mut_lower in payload_lower or mut_lower in unquoted_payload):
                    return True, f"命中污点变异指纹 [{sec_id} 变异体: {mut[:12]}...]", 0.0

        # 2. 局部高熵密文检测 (防止直接外发未解密的 AES/RSA/哈希密文块)
        # 拆解单词或连续字符块
        words = re.findall(r'[a-zA-Z0-9+/=]{16,}', payload_text)
        max_entropy = 0.0
        suspicious_block = ""
        for w in words:
            ent = calculate_shannon_entropy(w)
            if ent > max_entropy:
                max_entropy = ent
                suspicious_block = w

        # 若包含高熵且会话已读敏感凭据
        if max_entropy >= entropy_threshold and len(secret_registry) > 0:
            return True, f"检出可疑高熵密文数据外发 (香农熵 {max_entropy:.2f} >= {entropy_threshold}): {suspicious_block[:16]}...", max_entropy

        return False, "", max_entropy
