"""Validated, non-evaluating state-predicate DSL for the five safety policies."""
import fnmatch
import re
from pathlib import Path
from urllib.parse import urlsplit
import yaml
import bashlex
from d2core.execution import analyze_command, command_name, git_subcommand, exec_violation
from d2core.policy_engine import normalized_path
from .compression import sensitive

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


def is_egress_sink(name,args):
    if name=='net.fetch':
        return str(args.get('method','GET')).upper()!='GET' or bool(urlsplit(args.get('url','')).query) or bool(args.get('body'))
    if name=='spawn_subagent':return True
    if name=='mcp.call':return args!={'name':'project_facts'}
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
        paths=[normalized_path(args.get('path',''),self.workspace)] if name=='fs.write' else []
        effect='file_write' if name=='fs.write' else 'vcs_publish' if name in {'git.commit','git.push'} else ''
        flags={x:False for x in PREDICATES}
        if name=='exec':
            command=args.get('command',args.get('cmd',''))
            analysis=analyze_command(command)
            names={command_name(argv[0]) for argv in analysis.commands if argv}
            download=bool(names & set(self.commands['download_commands']))
            interpreter=bool(names & set(self.commands['execution_commands']))
            flags.update({'cmd.ast.pipe_to_interpreter':analysis.has_pipeline and interpreter,
                'cmd.ast.remote_download_exec':download and (interpreter or analysis.has_pipeline or analysis.has_chain),
                'cmd.ast.decode_then_exec':bool(re.search(r'base64|frombase64string|b64decode',command,re.I)) and (interpreter or any(x in command for x in ('-d','--decode','eval','exec'))),
                'cmd.reads_sensitive_env':bool(re.search(r'API_KEY|SECRET|TOKEN|SSH_AUTH_SOCK|\.env\b',command,re.I)),
                'cmd.ast.unverifiable':bool(exec_violation(command,self.commands,readonly=False))})
            if any(git_subcommand(argv) in {'push','commit'} for argv in analysis.commands):effect='vcs_publish'
            for argv in analysis.commands:
                if argv and command_name(argv[0]) in {'touch','cp','mv','mkdir','install','ln','sed','rm','tee','set-content','out-file'}:
                    paths.extend(normalized_path(word,self.workspace) for word in argv[1:] if not word.startswith('-'))
            def visit(node):
                if node.kind=='redirect' and getattr(node,'output',None) and hasattr(node.output,'word'):
                    paths.append(normalized_path(node.output.word,self.workspace))
                for value in vars(node).values():
                    if isinstance(value,bashlex.ast.node):visit(value)
                    elif isinstance(value,list):
                        for child in value:
                            if isinstance(child,bashlex.ast.node):visit(child)
            try:
                for tree in bashlex.parse(command):visit(tree)
            except (ValueError,NotImplementedError,bashlex.errors.ParsingError):pass
            if paths:effect='file_write'
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
        return sorted(matches,key=lambda m:m['risk'],reverse=True)

    def check(self,name,args,readonly,hits):
        matches=self.evaluate(name,args,readonly,hits)
        hard=next((m for m in matches if m['risk']=='R3'),None)
        return (hard['rule_id'],hard['reason']) if hard else (None,None)
