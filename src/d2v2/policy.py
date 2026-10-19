"""Validated, non-evaluating state-predicate DSL for the five safety policies."""
import fnmatch
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import yaml
import bashlex
from d2core.execution import analyze_command, command_name, git_subcommand, exec_violation
from d2core.policy_engine import normalized_path
from .compression import sensitive
from .normalization import target_view
from .command_effects import command_effects

PREDICATES={
    'args.contains_secret_fingerprint','args.references_secret_asset',
    'ctx.confidentiality.nonempty','ctx.integrity.nonempty','authority.net_granted',
    'target.domain not in trust.domains','action.egress_sink','action.fingerprint_egress',
    'cmd.ast.pipe_to_interpreter','cmd.ast.decode_then_exec','cmd.ast.remote_download_exec',
    'cmd.ast.unverifiable','cmd.reads_sensitive_env',
}


def validate_expression(expr):
    if isinstance(expr,str):
        atom=expr.removeprefix('not ')
        if atom not in PREDICATES:raise ValueError('Unknown policy predicate: '+atom)
    elif isinstance(expr,dict) and len(expr)==1:
        key,value=next(iter(expr.items()))
        if key in {'any','all'}:
            if not isinstance(value,list) or not value:raise ValueError('Empty policy expression')
            for child in value:validate_expression(child)
        elif key=='not':validate_expression(value)
        elif key=='target.path matches':
            if not isinstance(value,list) or not value or not all(isinstance(x,str) for x in value):raise ValueError('Invalid path patterns')
        elif key=='authority.mode':
            if value not in {'READONLY_REVIEW','TASK'}:raise ValueError('Invalid authority mode')
        else:raise ValueError('Unsupported policy expression')
    else:raise ValueError('Invalid policy expression')


def predicate(expr,facts):
    if isinstance(expr,str):
        if expr.startswith('not '):return not predicate(expr[4:],facts)
        if expr not in PREDICATES:raise ValueError('Unknown policy predicate')
        return bool(facts[expr])
    key,value=next(iter(expr.items()))
    if key=='any':return any(predicate(child,facts) for child in value)
    if key=='all':return all(predicate(child,facts) for child in value)
    if key=='not':return not predicate(value,facts)
    if key=='authority.mode':return facts[key]==value
    if key=='target.path matches':
        return any(fnmatch.fnmatchcase(path,pattern) for path in facts['target.paths'] for pattern in value)
    raise ValueError('Unknown predicate operator')


def autoload_urls(content):
    """Resource references that renderers load; ordinary hyperlinks are excluded."""
    urls=[]
    class Resources(HTMLParser):
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            keys={'img':('src','srcset'),'script':('src',),'iframe':('src',),
                  'audio':('src',),'video':('src','poster'),'source':('src','srcset'),
                  'embed':('src',),'object':('data',),'input':('src',)}.get(tag,())
            if tag=='link' and set(attrs.get('rel','').lower().split()) & {'stylesheet','preload','prefetch','icon'}:keys=('href',)
            for key in keys:
                value=attrs.get(key,'') or ''
                urls.extend(x.strip().split()[0] for x in value.split(',') if x.strip()) if key=='srcset' else urls.append(value)
    parser=Resources(convert_charrefs=True)
    parser.feed(content)
    # Markdown inline and reference-style images; optional angle brackets/titles.
    urls.extend(re.findall(r'!\[[^\]]*\]\(\s*<?([^\s)>]+)',content))
    definitions={k.strip().casefold():v for k,v in re.findall(r'^\s*\[([^\]]+)\]:\s*<?([^\s>]+)',content,re.M)}
    for alt,key in re.findall(r'!\[([^\]]*)\]\[([^\]]*)\]',content):
        urls.append(definitions.get((key or alt).strip().casefold(),''))
    for alt in re.findall(r'!\[([^\]]+)\](?![\[(])',content):urls.append(definitions.get(alt.strip().casefold(),''))
    urls.extend(re.findall(r'url\(\s*[\'\"]?([^\s)\'\"]+)',content,re.I))
    urls.extend(re.findall(r'@import\s+[\'\"]([^\'\"]+)',content,re.I))
    return list(dict.fromkeys(unescape(u) for u in urls if urlsplit(unescape(u)).hostname and urlsplit(unescape(u)).scheme in {'','http','https'}))


def artifact_egress_urls(args,net_grants=()):
    # A renderer performs GET; a POST grant never authorizes an automatic GET.
    from .compression import canonical
    suffix=Path(args.get('path','')).suffix.casefold()
    if suffix not in {'.md','.markdown','.mdx','.html','.htm','.xhtml','.svg','.css'}:return []
    content=args.get('content','')
    # Literal code in Markdown does not trigger a renderer fetch.
    if suffix in {'.md','.markdown','.mdx'}:
        content=re.sub(r'(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$','',content)
        content=re.sub(r'(`+).*?\1','',content,flags=re.S)
        content=re.sub(r'(?m)^(?: {4}|\t).*$', '',content)
    content=re.sub(r'<!--.*?-->','',content,flags=re.S)
    grants={g[4:] for g in net_grants if g.startswith('GET ')}
    return [u for u in autoload_urls(content)
            if canonical('https:'+u if u.startswith('//') else u) not in grants]


def is_egress_sink(name,args,net_grants=(),mcp_effect=None,command_analysis=None):
    if name=='exec':return bool((command_analysis if command_analysis is not None else command_effects(args.get('command',args.get('cmd',''))))['network_targets'])
    if name=='git.push':return True
    if name=='net.fetch':
        return str(args.get('method','GET')).upper()!='GET' or bool(urlsplit(args.get('url','')).query) or bool(args.get('body'))
    if name=='spawn_subagent':return False
    if name=='mcp.call':return mcp_effect=='network'
    if name=='fs.write':return bool(artifact_egress_urls(args,net_grants))
    return False


class HardPolicies:
    def __init__(self,workspace,policy_path=None):
        self.workspace=Path(workspace)
        data=yaml.safe_load(Path(policy_path or Path(__file__).with_name('policies.yaml')).read_text(encoding='utf-8'))
        if set(data)!={'version','rules','trust','commands'} or data['version']!=2:raise ValueError('Invalid policy document')
        self.trust=data['trust']['domains'];self.commands=data['commands']
        self.rules={}
        for rule in data['rules']:
            if set(rule)-{'id','match','when','risk','verdict','explain'}:raise ValueError('Unknown policy fields')
            if rule['id'] in self.rules:raise ValueError('Duplicate policy id')
            if set(rule['match'])-{'tool','method','effect'}:raise ValueError('Unknown match field')
            validate_expression(rule['when'])
            risk=rule['risk']
            if set(risk)-{'base','escalate','downgrade'} or risk['base'] not in {'R0','R1','R2','R3'}:raise ValueError('Invalid risk')
            for key in ('escalate','downgrade'):
                for step in risk.get(key,[]):
                    validate_expression(step['if'])
                    if step['to'] not in {'R0','R1','R2','R3'}:raise ValueError('Invalid risk transition')
            if any(k not in {'R0','R1','R2','R3'} or v not in {'ALLOW','ASK','BLOCK'} for k,v in rule['verdict'].items()):raise ValueError('Invalid verdict')
            if rule['verdict'].get('R3','BLOCK')!='BLOCK':raise ValueError('R3 cannot be weakened')
            self.rules[rule['id']]=rule
        if set(self.rules)!={'POL-FS-WRITE-SENSITIVE','POL-NET-SECRET-EXFIL','POL-EXEC-RESTRICT','POL-GIT-REVIEW-NO-PUSH','POL-SUBAGENT-SECRET-LEAK'}:raise ValueError('Expected five policies')

    def facts(self,name,args,readonly,hits,context=None,network_granted=False,secret_assets=()):
        context=context or {}
        method=str(args.get('method','GET')).upper()
        sink=is_egress_sink(name,args)
        domain=(urlsplit(args.get('url','')).hostname or '').lower()
        paths=[normalized_path(target_view(args.get('path','')),self.workspace)] if name=='fs.write' else []
        effect='file_write' if name=='fs.write' else 'vcs_publish' if name in {'git.commit','git.push'} else ''
        flags={x:False for x in PREDICATES}
        if name=='exec':
            command=args.get('command',args.get('cmd',''))
            analysis=command_effects(command)
            flags.update({'cmd.ast.pipe_to_interpreter':analysis['pipe_to_interpreter'],
                'cmd.ast.remote_download_exec':analysis['download_exec'],
                'cmd.ast.decode_then_exec':analysis['decode_exec'],
                'cmd.reads_sensitive_env':bool(re.search(r'\$\{?(?:API_KEY|SECRET|TOKEN|SSH_AUTH_SOCK)\b',command,re.I)),
                'cmd.ast.unverifiable':not analysis['parsed']})
            if analysis['git_action']:effect='vcs_publish'
            paths.extend(normalized_path(target_view(word),self.workspace) for word in analysis['write_paths'])
            if paths and not analysis['git_action']:effect='file_write'
        # No domain trust can override exact fingerprint disclosure (table 2a).
        flags.update({'args.contains_secret_fingerprint':bool(hits),
            'args.references_secret_asset':name=='spawn_subagent' and (any(asset and asset in args.get('task','') for asset in secret_assets) or any(sensitive(t) for t in re.findall(r'[\w./-]+',args.get('task','')))),
            'ctx.confidentiality.nonempty':bool(context.get('confidentiality')),
            'ctx.integrity.nonempty':bool(context.get('integrity')),
            'authority.net_granted':network_granted,
            'target.domain not in trust.domains':domain not in self.trust,
            'action.egress_sink':sink,
            'action.fingerprint_egress':sink or name=='net.fetch' and bool(hits)})
        flags.update({'tool':name,'method':method,'effect':effect,'target.paths':paths,
                      'authority.mode':'READONLY_REVIEW' if readonly else 'TASK'})
        return flags

    def evaluate(self,name,args,readonly,hits,context=None,network_granted=False,secret_assets=()):
        facts=self.facts(name,args,readonly,hits,context,network_granted,secret_assets)
        matches=[]
        for rule in self.rules.values():
            if any((facts[k] not in v if isinstance(v,list) else facts[k]!=v) for k,v in rule['match'].items()):continue
            if not predicate(rule['when'],facts):continue
            risk=rule['risk']['base']
            for direction in ('downgrade','escalate'):
                for step in rule['risk'].get(direction,[]):
                    if predicate(step['if'],facts):
                        if (direction=='escalate' and step['to']<risk) or (direction=='downgrade' and step['to']>risk):raise ValueError('Invalid risk direction')
                        risk=step['to']
            matches.append({'rule_id':rule['id'],'risk':risk,'verdict':rule['verdict'][risk],'reason':rule.get('explain',rule['id'])})
        if name=='exec' and facts['cmd.ast.unverifiable']:
            matches.append({'rule_id':'POL-EXEC-UNPARSEABLE','risk':'R2','verdict':'ASK','reason':'命令含动态语法或无法解析，需要确认。'})
        return sorted(matches,key=lambda m:m['risk'],reverse=True)

    def check(self,name,args,readonly,hits):
        matches=self.evaluate(name,args,readonly,hits)
        hard=next((m for m in matches if m['risk']=='R3'),None)
        return (hard['rule_id'],hard['reason']) if hard else (None,None)

    def sensitive_read(self,value):
        """Detection only: the executor retains its separate workspace boundary."""
        if self.memory_storage_path(value):return False
        text=target_view(value).replace('\\','/')
        root=normalized_path(str(self.workspace),self.workspace)
        resolved=normalized_path(text,self.workspace)
        outside=(text.startswith('~') or resolved!=root and not resolved.startswith(root.rstrip('/')+'/'))
        patterns=self.rules['POL-FS-WRITE-SENSITIVE']['when']['target.path matches']
        protected=any(fnmatch.fnmatchcase(resolved,p) or
                      p.endswith('/*') and fnmatch.fnmatchcase(resolved,p[:-2]) for p in patterns)
        return sensitive(text) or outside or protected

    def memory_storage_path(self,value):
        """Only this Agent's workspace/home stores, never arbitrary .pi paths."""
        text=target_view(value).replace('\\','/')
        resolved=normalized_path(text,self.workspace)
        for base in (self.workspace,Path.home()):
            root=normalized_path(str(base/'.pi'),self.workspace)
            if resolved==root+'/memory.json' or resolved==root+'/memory' or resolved.startswith(root+'/memory/'):
                return resolved
        return None
