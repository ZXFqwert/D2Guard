"""Explicit, bounded rule-based security extraction; not general semantic understanding."""
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit
from .normalization import normalize, target_view
from .relations import relation_segments, contextual_cues

URL = re.compile(r'https?://[^\s<>"\x27`，；。！？、]+',re.I)
PATH = re.compile(r'(?<![\w])(?:\.[A-Za-z][\w.-]*|(?:[\w@-]+/)*[\w@-]+\.(?:md|txt|json|csv|env|pem|key|py|sh|exe|yaml|yml))(?![\w])',re.I)
DIRECTIVE = re.compile(r'\b(read|write|send|upload|post|fetch|execute|run|must|before|register|ignore|use|call)\b|读取|写入|发送|外发|上传|执行|必须|忽略|调用|之前',re.I)
NEGATION = re.compile(r'\b(no|not|never|without|avoid|explain|quote|example)\b|禁止|不要|不得|示例|解释|引用|不允许',re.I)
READ = re.compile(r'\b(read|open|view|review|inspect|summari[sz]e)\b|读取|查看|打开|读|查阅|审查',re.I)
WRITE = re.compile(r'\b(write|generate|create|save|put)\b|写|生成|保存|创建|存入|输出',re.I)
NET_GET = re.compile(r'\b(fetch|get|download|visit)\b|访问|获取|下载',re.I)
NET_POST = re.compile(r'\b(upload|send|post|submit)\b|上传|发送|提交',re.I)
UNCERTAIN = re.compile(r'\b(if|unless|whether|could|would|might|may|can|should)\b|如果|若|是否|能否|可以.*吗|[?？]',re.I)


def canonical(target):
    target = target_view(target).strip('`\'" ,;。)')
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
    matches=list(PATH.finditer(without))+list(re.finditer(r'(?:~/)?(?:\.?[\w@-]+/)+[\w.@-]+',without))
    matches=[m for m in matches if not any(n.start()<=m.start() and n.end()>=m.end() and n.span()!=m.span() for n in matches)]
    return list(dict.fromkeys(urls+[m.group().rstrip('.') for m in sorted(matches,key=lambda m:m.start())]))



def sensitive(path):
    low=target_view(path).replace('\\','/')
    # Only the credential filename exception; sensitive parent paths still count.
    if PurePosixPath(low).name in {'.env.example','.env.sample','.env.template'}:
        low=str(PurePosixPath(low).parent)+'/'
    return any(x in low for x in ('.env','id_rsa','id_ed25519','.ssh/','.aws/','credential','secret','token','password')) or low.endswith(('.pem','.key'))


DELEGATE = re.compile(r'\b(delegat\w*|specialist)\b|子\s*agent|专家|委派',re.I)


def affirmative_clauses(text):
    # Questions/conditions have sentence scope. Negation has coordinated-clause scope.
    from .user_message import split_user_message
    trusted,_=split_user_message(text)
    for sentence in re.split(r'\n|[;；。]|\.\s+',trusted):
        if UNCERTAIN.search(URL.sub('',sentence)):continue
        parts=re.split(r'[,，]|\bbut\b|(?=\bwithout\b)|(?=\b(?:do not|don\'t|never|avoid)\b)|(?=不要|不得|禁止|不包含)',sentence,flags=re.I)
        # without introduces a negative adjunct; it never cancels the earlier verb.
        for clause in parts:
            language=URL.sub('',clause)
            if NEGATION.search(language) or re.search(r"\b(?:don't|cannot|can't)\b|不上传|不发送|别上传|不包含",language,re.I):continue
            yield clause


def grant(text, ref, version):
    result={'version':version,'intent_mode':'READONLY_REVIEW' if re.search(r'read.?only|只读',text,re.I) else 'TASK',
        'read':[],'write':[],'net':[],'spawn':[],'evidence_ref':ref,'coverage_incomplete':False}
    for clause in affirmative_clauses(target_view(text)):
        local={'read':[],'write':[]}
        for target in targets(clause):
            before=clause[:clause.find(target)]
            try:value=canonical(target)
            except ValueError:result['coverage_incomplete']=True;continue
            if value.startswith('http'):
                after=clause[clause.find(target)+len(target):]
                method=re.search(r'\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b',before,re.I)
                suffix=re.match(r'\s*(?:using|with|使用)\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b',after,re.I)
                if method or suffix:result['net'].append((method or suffix).group(1).upper()+' '+value)
                elif NET_POST.search(before):result['net'].append('POST '+value)
                elif NET_GET.search(before) or READ.search(before):result['net'].append('GET '+value)
            else:
                verbs=sorted([(m.start(),'read') for m in READ.finditer(before) if not re.search(r'\b(?:the|a|an|this|your)\s+$',before[:m.start()],re.I)]+[(m.start(),'write') for m in WRITE.finditer(before)])
                if verbs:
                    key=verbs[-1][1];result[key].append(value);local[key].append(value)
        if DELEGATE.search(clause) and any(local.values()):result['spawn'].append(local)
    for key in ('read','write','net'):
        result[key]=list(dict.fromkeys(result[key]))
        if len(result[key])>16:result['coverage_incomplete']=True;result[key]=result[key][:16]
    if len(result['spawn'])>16:result['coverage_incomplete']=True;result['spawn']=result['spawn'][:16]
    return result


def literal_scope(delta,args,anchor,hits=()):
    name=delta['tool'];target=delta['target']
    if name=='fs.read':return target in anchor.get('read',[])
    if name=='fs.write':return target in anchor.get('write',[])
    if name=='net.fetch':return delta['op']+' '+target in anchor.get('net',[])
    if name=='spawn_subagent' and not hits:
        task=args.get('task','')
        requested=grant(task,{},0)
        try:mentioned={canonical(t) for t in targets(target_view(task))}
        except ValueError:return False
        # No implicit network/exec authority travels with a read/write delegation.
        if not mentioned or requested['net'] or URL.search(task) or re.search(r'\b(exec(?:ute)?|shell|push|commit)\b|执行命令|推送',task,re.I):return False
        for scope in anchor.get('spawn',[]):
            if mentioned<=set(scope['read']+scope['write']) and set(requested['read'])<=set(scope['read']+scope['write']) and set(requested['write'])<=set(scope['write']):return True
    return False


def readonly_write_violation(delta,anchor,existing_sources=()):
    if delta['tool']!='fs.write' or anchor.get('intent_mode')!='READONLY_REVIEW':return False
    # Other writes still need the ordinary grant/taint decision table.
    return delta['target'] in existing_sources


def clauses(raw, ref):
    text,mapping=normalize(raw)
    found=[]
    for match in re.finditer(r'[^\n;。]+',text):
        clause=match.group(); mentioned=targets(clause)
        cues=contextual_cues(clause)
        if not (mentioned and DIRECTIVE.search(clause)) and not cues:continue
        mapped=mapping.char_to_raw[match.start():match.end()]
        a,b=min(x[0] for x in mapped),max(x[1] for x in mapped)
        relations,flows,gap=relation_segments(clause,targets)
        ops=list(dict.fromkeys(r['op'] for r in relations))
        found.append({'induced_ops':ops,'induced_targets':mentioned[:12],
            'clause_kind':'candidate_instruction' if any(r['stance']=='requested' for r in relations) else 'quoted_or_negated' if relations else 'context_only',
            'relation_schema':'operation-target-v2','action_relations':relations[:12],
            'requested_data_flows':flows[:12],'contextual_cues':cues,
            'evidence_ref':{**ref,'char_span':[a,b]},
            'span_unit':'unicode_codepoints','attribution':'candidate',
            'extraction_overflow':len(mentioned)>12 or len(relations)>12 or len(flows)>12,
            'coverage_incomplete':gap or len(mentioned)>12 or len(relations)>12 or len(flows)>12})
    # A capped target list is a coverage gap even when the source is short.
    return found, len(raw)>65536 or any(item['coverage_incomplete'] for item in found)


def unknown_clauses(raw, ref):
    """Until S1 is trained, DIRECTIVE is an explicitly identified rule signal."""
    text,mapping=normalize(raw)
    found=[]
    for match in re.finditer(r'[^\n;。]+',text):
        clause=match.group()
        if not DIRECTIVE.search(clause):continue
        relations,_,gap=relation_segments(clause,targets)
        if (not relations or gap) and not NEGATION.search(clause):
            spans=mapping.char_to_raw[match.start():match.end()]
            found.append({'evidence_ref':{**ref,'char_span':[min(s[0] for s in spans),max(s[1] for s in spans)]},
                          'reason':'DIRECTIVE rule signal without complete operation/target relation',
                          'signal':'rule:DIRECTIVE','s1':None})
    return found


def action(tool,args):
    mapping={'fs_read':'fs.read','fs_write':'fs.write','net_fetch':'net.fetch','spawn_subagent':'spawn_subagent','mcp_call':'mcp.call',
             'memory_read':'memory.read','memory_write':'memory.write','git_push':'git.push','git_commit':'git.commit'}
    name=mapping.get(tool,tool)
    raw_target=args.get('url') if name=='net.fetch' else args.get('key','') if name.startswith('memory.') else args.get('path','')
    valid=True
    try: target=target_view(raw_target) if name.startswith('memory.') and isinstance(raw_target,str) else '' if name.startswith('memory.') else canonical(raw_target) if raw_target else ''
    except ValueError:target='invalid';valid=False
    op=(str(args.get('method','GET')).upper() if name=='net.fetch' else name)
    return {'event_kind':'ACTION_CANDIDATE','tool':name,'op':op,'target':target,
        'raw_target':raw_target,'target_normalization_changed':raw_target!=target,
        'manipulation_cues':['normalized_action_target'] if raw_target!=target else [],
        'sensitive_target':sensitive(target),'valid_target':valid,
        'coverage_incomplete':name not in {'fs.read','fs.write','net.fetch','spawn_subagent','mcp.call','memory.read','memory.write','exec','git.push','git.commit'}}


def fast_view(value):
    """Drop storage mechanics, never security facts. Full references remain in SQLite."""
    if isinstance(value,list):return [fast_view(item) for item in value]
    if isinstance(value,dict):
        omitted={'evidence_ref','span_unit','call_id','ref','actual_leakage_semantics'}
        if value.get('relation_schema')=='operation-target-v2':
            # Legacy unordered sets are retained for audit compatibility, but the
            # model sees the precise relation list instead of contradictory duplicates.
            omitted.update({'induced_ops','induced_targets','taint_id'})
        return {key:fast_view(item) for key,item in value.items()
            if key not in omitted}
    return value
