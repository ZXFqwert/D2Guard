"""Extract complete source sentences, never truncate or generate a paraphrase."""
import re
from .compression import grant


def build_task_brief(raw, trusted, count_tokens):
    if trusted==raw and count_tokens(raw)<=150:
        return {'task_brief':raw,'task_brief_tokens':count_tokens(raw),
                'task_brief_kept_spans':[[0,len(raw)]] if raw else [],
                'task_brief_omitted_spans':[],'task_brief_overflow':False}
    spans=[]
    # A sentence boundary must not split filenames or decimal/URL components.
    for match in re.finditer(r'[^\n。！？!?]+(?:[。！？!?]|\n|$)',trusted):
        a,b=match.span()
        for part in re.finditer(r'.+?(?:\.(?=\s|$)|$)',trusted[a:b]):
            x,y=a+part.start(),a+part.end()
            while x<y and trusted[x].isspace():x+=1
            while y>x and trusted[y-1].isspace():y-=1
            if x<y:spans.append([x,y])
    if count_tokens(trusted)<=150:
        kept=spans
    else:
        kept=[]
        for i,(a,b) in enumerate(spans):
            permissions=grant(trusted[a:b],{},1)
            if i==0 or any(permissions[k] for k in ('read','write','net','spawn')):
                kept.append([a,b])
    # Use original complete sentence spans; quoted segments were masked upstream.
    brief='\n'.join(raw[a:b] for a,b in kept)
    if not any(raw[a:b].strip() for a,b in kept):brief=''
    omitted=[];cursor=0
    for a,b in kept:
        if cursor<a:omitted.append([cursor,a])
        cursor=b
    if cursor<len(raw):omitted.append([cursor,len(raw)])
    tokens=count_tokens(brief)
    return {'task_brief':brief,'task_brief_tokens':tokens,
            'task_brief_kept_spans':kept,'task_brief_omitted_spans':omitted,
            'task_brief_overflow':tokens>150}
