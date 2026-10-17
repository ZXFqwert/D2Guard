"""Detection-only transforms. Executable input and raw evidence stay unchanged.

Reuse the reviewed grapheme/NFKC/homoglyph/comment mapping from d2core. Its
lexical token fields are deliberately not exposed as model Token intervals.
"""
import base64
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote

from d2core.extractor import normalize as legacy_normalize, _sub, B64, HOMOGLYPHS

GREEK = str.maketrans({'Α':'A','Β':'B','Ε':'E','Ζ':'Z','Η':'H','Ι':'I','Κ':'K',
                     'Μ':'M','Ν':'N','Ο':'O','Ρ':'P','Τ':'T','Υ':'Y','Χ':'X',
                     'ο':'o','ρ':'p','ν':'v','ι':'i'})


@dataclass
class RawMapping:
    char_to_raw: list


def normalize(raw, *, casefold=False):
    text, old = legacy_normalize(raw, decode_base64=False)
    chars, spans = [], []
    for char, span in zip(text, old.char_to_raw):
        if unicodedata.category(char) == 'Cf':
            continue
        value = char.translate(GREEK)
        chars.extend(value)
        spans.extend([span] * len(value))
    text = ''.join(chars)
    text, spans = _sub(text, spans, r'[ \t]+', lambda _: ' ')
    # Bounded expansions retain the encoded source as well as its detection view.
    for _ in range(2):
        additions = []
        for pattern, decoder in (
            (r'(?:%[0-9a-fA-F]{2}){2,}', unquote),
            (r'(?:\\x[0-9a-fA-F]{2}){2,}', lambda s: bytes.fromhex(s.replace('\\x','')).decode('utf-8')),
            (r'0x(?:[0-9a-fA-F]{2}){4,}', lambda s: bytes.fromhex(s[2:]).decode('utf-8')),
            (B64.pattern, lambda s: base64.b64decode(s+'='*(-len(s)%4),altchars=b'-_',validate=True).decode('utf-8')),
        ):
            for match in list(re.finditer(pattern,text))[:8]:
                value = match.group()
                if len(value)>16384:continue
                try:
                    decoded = decoder(value)
                except (ValueError,UnicodeError):
                    continue
                if not decoded or decoded in text or any(decoded == x[0] for x in additions):continue
                if sum(c.isprintable() or c in '\n\t\r' for c in decoded)/len(decoded)<.95:continue
                decoded, _ = legacy_normalize(decoded,decode_base64=False)
                decoded = decoded.translate(GREEK)
                selected = spans[match.start():match.end()]
                additions.append((decoded,(min(x[0] for x in selected),max(x[1] for x in selected))))
        if not additions:break
        for decoded,span in additions:
            value='\n'+decoded
            text+=value;spans.extend([span]*len(value))
    if casefold:
        folded=[];folded_spans=[]
        for char,span in zip(text,spans):
            value=char.casefold();folded.extend(value);folded_spans.extend([span]*len(value))
        text=''.join(folded);spans=folded_spans
    return text, RawMapping(spans)


def evidence_span(ref, raw, char_span, fast):
    """Only the actual model tokenizer may label a span as model Tokens."""
    result={**ref,'char_span':list(char_span),'token_span':None,'tokenizer':None}
    if hasattr(fast,'token_span'):
        result['token_span']=fast.token_span(raw,char_span)
        result['tokenizer']='original-laya:'+getattr(fast,'metadata',{}).get('revision','unknown')
    return result


def target_view(raw):
    """One detection key; never feed the result to the executor."""
    text=unicodedata.normalize('NFKC',raw).translate(HOMOGLYPHS).translate(GREEK)
    return ''.join(c for c in text if unicodedata.category(c)!='Cf').casefold()
