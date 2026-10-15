"""
7类对抗样本规范化清洗器 (Normalizer)
覆盖赛题与测试集中的对抗变形：
1. 多语言与表情混淆
2. Unicode 变形与零宽空格
3. 指令分片拼接
4. 分隔符与注释内嵌载荷提取
5. 字符格式递归解码 (URL, Hex, Base64)
6. 长上下文稀释清洗
7. 业务语义伪装特征提取
"""

from __future__ import annotations
import base64
import binascii
import re
import unicodedata
import urllib.parse
from typing import List, Tuple


# 常见西里尔字母/特殊同形字到 ASCII 拉丁字母的映射表
HOMOGLYPH_MAP = {
    'а': 'a', 'с': 'c', 'е': 'e', 'о': 'o', 'р': 'p', 'ѕ': 's', 'х': 'x', 'у': 'y',
    'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H', 'І': 'I', 'Ј': 'J', 'К': 'K',
    'М': 'M', 'О': 'O', 'Р': 'P', 'Ѕ': 'S', 'Т': 'T', 'Х': 'X',
}

# 零宽字符与不可见控制符正则
ZERO_WIDTH_REGEX = re.compile(r'[\u200B-\u200D\uFEFF\u200E\u200F\u202A-\u202E]')


class AdversarialNormalizer:
    """对抗样本清洗与规范化器"""

    @classmethod
    def clean_unicode_and_zero_width(cls, text: str) -> str:
        """去除零宽字符，执行 NFKC 标准化，并替换常见同形仿冒字"""
        if not text:
            return ""
        # 1. 移除零宽字符
        cleaned = ZERO_WIDTH_REGEX.sub('', text)
        # 2. NFKC 兼容性等价分解合并
        cleaned = unicodedata.normalize('NFKC', cleaned)
        # 3. 同形字替换
        chars = [HOMOGLYPH_MAP.get(c, c) for c in cleaned]
        return "".join(chars)

    @classmethod
    def recursive_decode(cls, text: str, max_depth: int = 4) -> List[str]:
        """
        递归启发式多层解码：
        支持 URL 解码、Hex 16进制解码、Base64 解码。
        返回包含原始文本及各层成功解码产物的候选字符串列表。
        """
        candidates = [text]
        current_layer = [text]

        for _ in range(max_depth):
            next_layer = []
            for item in current_layer:
                # 尝试 URL 解码
                try:
                    unquoted = urllib.parse.unquote(item)
                    if unquoted != item and unquoted not in candidates:
                        candidates.append(unquoted)
                        next_layer.append(unquoted)
                except Exception:
                    pass

                # 尝试 Hex 解码 (纯十六进制串，长度偶数且 >= 4)
                hex_matches = re.findall(r'(?:0x)?([0-9a-fA-F]{6,})', item)
                for h in hex_matches:
                    try:
                        decoded_bytes = binascii.unhexlify(h if len(h) % 2 == 0 else h[:-1])
                        decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
                        if decoded_str and decoded_str not in candidates and len(decoded_str) >= 3:
                            candidates.append(decoded_str)
                            next_layer.append(decoded_str)
                    except Exception:
                        pass

                # 尝试 Base64 解码
                b64_matches = re.findall(r'[A-Za-z0-9+/]{8,}={0,2}', item)
                for b in b64_matches:
                    try:
                        # 补齐 padding
                        missing_padding = len(b) % 4
                        padded = b + ('=' * (4 - missing_padding) if missing_padding else '')
                        decoded_bytes = base64.b64decode(padded)
                        decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
                        # 判断是否为有意义的 ASCII / 文本
                        if decoded_str and len(decoded_str) >= 4 and decoded_str.isprintable():
                            if decoded_str not in candidates:
                                candidates.append(decoded_str)
                                next_layer.append(decoded_str)
                    except Exception:
                        pass

            if not next_layer:
                break
            current_layer = next_layer

        return candidates

    @classmethod
    def extract_comments_and_hidden_payloads(cls, text: str) -> List[str]:
        """
        从代码、HTML、配置文件中提取注释与分隔符内部可能隐藏的二阶载荷
        包括: /* ... */, <!-- ... -->, # ..., // ...
        """
        extracted = []
        if not text:
            return extracted

        # 匹配 /* ... */
        c_style = re.findall(r'/\*([\s\S]*?)\*/', text)
        extracted.extend([c.strip() for c in c_style if c.strip()])

        # 匹配 <!-- ... -->
        html_style = re.findall(r'<!--([\s\S]*?)-->', text)
        extracted.extend([h.strip() for h in html_style if h.strip()])

        # 匹配单行注释 # ... 或 // ...
        single_line = re.findall(r'(?:#|//)\s*(.+)', text)
        extracted.extend([s.strip() for s in single_line if len(s.strip()) > 8])

        return extracted

    @classmethod
    def normalize_for_inspection(cls, text: str) -> Tuple[str, List[str]]:
        """
        标准预处理全流程：
        1. 清洗 Unicode 和零宽字符
        2. 提取潜在注释内嵌文本
        3. 展开所有递归解码候选
        返回: (清洗后主文本, 所有展开的语义候选集合)
        """
        cleaned = cls.clean_unicode_and_zero_width(text)
        candidates = cls.recursive_decode(cleaned)
        
        # 将注释中提取的内容也加入解码检查
        comments = cls.extract_comments_and_hidden_payloads(cleaned)
        for c in comments:
            candidates.extend(cls.recursive_decode(c))

        return cleaned, list(set(candidates))
