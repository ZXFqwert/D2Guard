"""Explicit quotation boundaries, never heuristic authority inferred from prose."""
import re


def split_user_message(raw):
    quoted=[];offset=0;fence=None;forwarded=False;block_start=None
    lines=raw.splitlines(keepends=True)
    for line in lines:
        stripped=line.strip()
        marker=re.match(r'^(```+|~~~+)',stripped)
        start_forward=bool(re.match(r'^(?:[- ]*(?:begin forwarded message|forwarded message|原始邮件|转发消息|转发内容)[- :：]*|<forwarded>)$',stripped,re.I))
        end_forward=bool(re.match(r'^(?:[- ]*(?:end forwarded message|转发结束)[- ]*|</forwarded>)$',stripped,re.I))
        is_quote=bool(fence or forwarded or marker or start_forward or re.match(r'^\s*>',line))
        if is_quote:
            if block_start is None:block_start=offset
        elif block_start is not None:
            quoted.append([block_start,offset]);block_start=None
        if marker:
            if fence and marker.group()[0]==fence[0] and len(marker.group())>=len(fence):fence=None
            elif not fence:fence=marker.group()
        if start_forward:forwarded=True
        if end_forward:forwarded=False
        offset+=len(line)
    if block_start is not None:quoted.append([block_start,len(raw)])
    chars=list(raw)
    for a,b in quoted:
        chars[a:b]=['\n' if c=='\n' else ' ' for c in chars[a:b]]
    return ''.join(chars),quoted
