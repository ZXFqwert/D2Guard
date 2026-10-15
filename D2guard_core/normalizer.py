"""
Dual-View Anti-Bypass Normalizer & Token Span Mapper
"""
import re
import unicodedata
import base64
from typing import Tuple, List, Dict, Any

# Cyrillic to Latin homoglyphs mapping
HOMOGLYPH_MAP = {
    'а': 'a', 'с': 'c', 'е': 'e', 'о': 'o', 'р': 'p', 'х': 'x', 'у': 'y',
    'і': 'i', 'ј': 'j', 'ѕ': 's', 'ԁ': 'd', 'ԛ': 'q', 'ԝ': 'w',
    'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H', 'І': 'I', 'Ј': 'J',
    'К': 'K', 'М': 'M', 'О': 'O', 'Р': 'P', 'Т': 'T', 'Х': 'X', 'Ү': 'Y'
}

def normalize_text(raw_text: str) -> str:
    """
    Apply canonical transformations:
    1. Unicode NFKC normalization
    2. Cyrillic homoglyph conversion
    3. Zero-width character stripping
    4. Comment stripping (/* ... */)
    5. Quote concatenation (s""h -> sh)
    6. $IFS to whitespace
    """
    if not raw_text:
        return ""
    
    # 1. NFKC
    text = unicodedata.normalize('NFKC', raw_text)
    
    # 2. Cyrillic Homoglyphs
    chars = []
    for ch in text:
        chars.append(HOMOGLYPH_MAP.get(ch, ch))
    text = "".join(chars)
    
    # 3. Strip zero-width chars
    text = re.sub(r'[\u200b-\u200f\ufeff]', '', text)
    
    # 4. Strip C-style comments: /* ... */
    text = re.sub(r'/\*.*?\*/', '', text)
    
    # 5. Concatenate quotes inside commands: e.g. b''a""s''h -> bash
    # Match patterns where quotes are juxtaposed inside words
    text = re.sub(r'(?<=[a-zA-Z0-9_\-\.])[\'"]{2,}(?=[a-zA-Z0-9_\-\.])', '', text)
    text = re.sub(r'(?<=[a-zA-Z0-9_\-\.])[\'"]([a-zA-Z0-9_\-\.]+)[\'"]', r'\1', text)
    
    # 6. $IFS replacement
    text = re.sub(r'\$IFS', ' ', text)
    
    return text

def detect_heuristic_base64(text: str) -> List[str]:
    """Detect potential base64 strings and return decoded ascii segments."""
    tokens = re.findall(r'[A-Za-z0-9+/]{8,}={0,2}', text)
    decoded_list = []
    for token in tokens:
        try:
            decoded = base64.b64decode(token).decode('utf-8', errors='ignore')
            if len(decoded.strip()) >= 4 and any(c.isalnum() for c in decoded):
                decoded_list.append(decoded)
        except Exception:
            pass
    return decoded_list

def estimate_token_span(raw_content: str, snippet: str) -> Tuple[List[int], List[int]]:
    """Calculate character span and approximate token span [start, end]."""
    if not snippet or not raw_content:
        return [0, 0], [0, 0]
    
    idx = raw_content.find(snippet)
    if idx == -1:
        # Search relaxed
        clean_snippet = snippet.strip()
        idx = raw_content.find(clean_snippet)
        if idx == -1:
            return [0, len(raw_content)], [0, max(1, len(raw_content) // 4)]
        length = len(clean_snippet)
    else:
        length = len(snippet)
        
    char_span = [idx, idx + length]
    # Rough estimate of token: roughly 4 chars per token, or count spaces
    token_start = len(raw_content[:idx].split())
    token_count = max(1, len(raw_content[idx:idx+length].split()))
    token_span = [token_start, token_start + token_count]
    return char_span, token_span
