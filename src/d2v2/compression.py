"""Explicit, bounded rule-based security extraction; not general semantic understanding."""
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit
from d2core.extractor import normalize

URL = re.compile(r'https?://[^\s<>"\x27`]+',re.I)
PATH = re.compile(r'(?<![\w])(?:\.[A-Za-z][\w.-]*|(?:[\w@-]+/)*[\w@-]+\.(?:md|txt|json|csv|env|pem|key|py|sh|exe|yaml|yml))(?![\w])',re.I)
DIRECTIVE = re.compile(r'\b(read|write|send|upload|post|fetch|execute|run|must|before|register|ignore|use|call)\b|读取|写入|发送|外发|上传|执行|必须|忽略|调用|之前',re.I)
NEGATION = re.compile(r'\b(no|not|never|without|avoid|explain|quote|example)\b|禁止|不要|不得|示例|解释|引用|不允许',re.I)
READ = re.compile(r'\b(read|review|inspect|summari[sz]e)\b|读|查阅|审查',re.I)
WRITE = re.compile(r'\b(write|generate|create|save)\b|写|生成|保存|创建',re.I)


def canonical(target):
    target = target.strip('`\'" ,;。)')
    if target.lower().startswith(('https://','http://')):
        u=urlsplit(target)
        if not u.hostname or u.username or u.password:
            raise ValueError('Invalid network target')
        return urlunsplit((u.scheme.lower(),u.netloc.lower(),u.path or '/',u.query,''))
    target=target.replace('\\','/')
    if target.startswith('/') or ':' in target or '..' in target.split('/'):
        raise ValueError('Non-workspace path')
    return str(PurePosixPath(target))


def targets(text):
    urls=[m.group().rstrip('.,;。)') for m in URL.finditer(text)]
    without=URL.sub(lambda m:' '*len(m.group()),text)
    return list(dict.fromkeys(urls+[m.group().rstrip('.') for m in PATH.finditer(without)]))


def sensitive(path):
    low=path.lower().replace('\\','/')
    return any(x in low for x in ('.env','id_rsa','id_ed25519','.ssh/','.aws/','credential','secret','token','password')) or low.endswith(('.pem','.key'))


def grant(text, ref, version):
    """Explicit nearby action verbs only. Ambiguous clauses do not grant permissions."""
    result={'version':version,'intent_mode':'READONLY_REVIEW' if re.search(r'read.?only|只读',text,re.I) else 'TASK',
        'read':[],'write':[],'net':[],'evidence_ref':ref,'coverage_incomplete':False}
    for match in re.finditer(r'[^\n;。]+',text):
        clause=match.group()
        for target in targets(clause):
            before=clause[:clause.find(target)]
            # Scope to the latest coordinated verb phrase; never infer grants from a filename alone.
            before=re.split(r'\.\s+|,|\band\b|然后|并且',before,flags=re.I)[-1]
            if NEGATION.search(before):
                continue
            try: value=canonical(target)
            except ValueError:
                result['coverage_incomplete']=True;continue
            if value.startswith('http'):
                if READ.search(before) or re.search(r'\bGET\b',before):result['net'].append('GET '+value)
                elif re.search(r'\bPOST\b',before):result['net'].append('POST '+value)
            elif WRITE.search(before):result['write'].append(value)
            elif READ.search(before):result['read'].append(value)
    if result['intent_mode']=='READONLY_REVIEW':result['write']=[]
    for key in ('read','write','net'):
        result[key]=list(dict.fromkeys(result[key]))
        if len(result[key])>16:result['coverage_incomplete']=True;result[key]=result[key][:16]
    return result


def clauses(raw, ref):
    text,mapping=normalize(raw)
    found=[]
    for match in re.finditer(r'[^\n;。]+',text):
        clause=match.group(); mentioned=targets(clause)
        if not mentioned or not DIRECTIVE.search(clause):continue
        mapped=mapping.char_to_raw[match.start():match.end()]
        a,b=min(x[0] for x in mapped),max(x[1] for x in mapped)
        ops=[]
        if READ.search(clause) or re.search(r'fs_read|fs\.read',clause,re.I):ops.append('fs.read')
        if WRITE.search(clause):ops.append('fs.write')
        if re.search(r'\b(post|upload|send)\b|上传|外发|发送',clause,re.I):ops.append('net.fetch:POST')
        if re.search(r'\b(get|fetch)\b|net_fetch',clause,re.I):ops.append('net.fetch:GET')
        found.append({'induced_ops':ops,'induced_targets':mentioned[:12],
            'clause_kind':'quoted_or_negated' if NEGATION.search(clause) else 'candidate_instruction',
            'evidence_ref':{**ref,'char_span':[a,b]},
            'span_unit':'unicode_codepoints','attribution':'candidate',
            'coverage_incomplete':len(mentioned)>12})
    # A capped target list is a coverage gap even when the source is short.
    return found, len(raw)>65536 or any(item['coverage_incomplete'] for item in found)


def action(tool,args):
    mapping={'fs_read':'fs.read','fs_write':'fs.write','net_fetch':'net.fetch','spawn_subagent':'spawn_subagent','mcp_call':'mcp.call'}
    name=mapping.get(tool,tool)
    raw_target=args.get('url') if name=='net.fetch' else args.get('path','')
    valid=True
    try: target=canonical(raw_target) if raw_target else ''
    except ValueError:target='invalid';valid=False
    op=(str(args.get('method','GET')).upper() if name=='net.fetch' else name)
    return {'event_kind':'ACTION_CANDIDATE','tool':name,'op':op,'target':target,
        'sensitive_target':sensitive(target),'valid_target':valid,
        'coverage_incomplete':name not in {'fs.read','fs.write','net.fetch','spawn_subagent','mcp.call'}}


def fast_view(value):
    """Drop storage mechanics, never security facts. Full references remain in SQLite."""
    if isinstance(value,list):return [fast_view(item) for item in value]
    if isinstance(value,dict):
        return {key:fast_view(item) for key,item in value.items()
            if key not in {'evidence_ref','span_unit','call_id','ref','actual_leakage_semantics'}}
    return value
