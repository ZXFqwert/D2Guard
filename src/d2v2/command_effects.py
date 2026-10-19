"""Deterministic shell AST effects. Parsing is distinct from knowing a program's effects."""
import re
import bashlex
from d2core.execution import analyze_command,command_name,git_subcommand

READ={'pwd','ls','cat','grep','rg','find','head','tail','wc','sort','uniq','cut','tr','sed','awk','stat','file','du','diff','echo','printf','test','true','false','which'}
GIT_READ={'status','log','diff','show','rev-parse','ls-files','branch','remote',
          'rev-list','ls-tree','for-each-ref','diff-tree','diff-files','diff-index',
          'describe','name-rev','count-objects','merge-base','check-ignore','check-attr','show-ref','cat-file'}
WRITE={'touch','mkdir','cp','mv','rm','tee','install','ln'}
INTERPRETERS={'sh','bash','zsh','dash','python','python3','node','perl','ruby','pwsh','powershell'}

def command_effects(command):
 a=analyze_command(command);result={'parsed':not(a.parse_error or a.has_substitution or a.opaque),'read_paths':[],'write_paths':[],'network_targets':[],'git_action':None,'download_exec':False,'pipe_to_interpreter':False,'decode_exec':False,'unknown_effect':False,'commands':a.commands}
 names={command_name(v[0]) for v in a.commands if v};interpreters=bool(names & INTERPRETERS)
 result['pipe_to_interpreter']=a.has_pipeline and interpreters
 result['download_exec']=bool(names & {'curl','wget'}) and interpreters
 result['decode_exec']=bool(names & {'base64','openssl'}) and interpreters and ('-d' in command or '--decode' in command)
 for argv in a.commands:
  n=command_name(argv[0]);args=argv[1:]
  if n in {'eval','source','.'} or n in INTERPRETERS and any(x in args for x in ('-c','-e','--eval')):result['parsed']=False
  if n=='git':
   sub=git_subcommand(argv)
   if sub in {'add','init','commit'}:result['write_paths'].append('.git')
   tail=argv[argv.index(sub)+1:] if sub in argv else []
   if sub=='config':
    reads={'--get','--get-all','--get-regexp','--get-urlmatch','--list','-l','get','list'}
    if not any(w in reads for w in tail):result['write_paths'].append('.git')
   for i,word in enumerate(tail):
    if word.startswith('--output='):result['write_paths'].append(word.split('=',1)[1])
    elif word=='--output' and i+1<len(tail):result['write_paths'].append(tail[i+1])
   if sub=='branch':
    mutating={'-d','-D','--delete','-m','-M','--move','-c','-C','--copy','-f','--force','--edit-description','--set-upstream-to','--unset-upstream'}
    positional=[];skip=False
    for word in tail:
     if skip:skip=False;continue
     if word in {'--contains','--no-contains','--merged','--no-merged','--points-at','--format','--sort'}:skip=True;continue
     if not word.startswith('-'):positional.append(word)
    if any(w.split('=')[0] in mutating for w in tail) or positional and '--list' not in tail:result['write_paths'].append('.git')
   if sub=='remote':
    operation=next((x for x in tail if not x.startswith('-')),None)
    if operation in {'add','rename','remove','rm','set-head','set-branches','set-url','prune'}:result['write_paths'].append('.git')
    elif operation=='update' or operation=='show' and '-n' not in tail:result['network_targets'].append('git-remote:origin')
    elif operation not in {None,'get-url','show'}:result['unknown_effect']=True
   if any(x in argv for x in ('-c','--ext-diff','--textconv')) or any(x.startswith(('--exec-path','--config-env')) for x in argv):result['unknown_effect']=True
   if sub in {'push','commit'}:result['git_action']='git.'+sub
   if sub in {'push','fetch','pull','clone'}:result['network_targets'].extend(re.findall(r'(?:https?://|ssh://|git://|file://)[^\s\'\"]+',command) or ['git-remote:origin'])
   elif sub not in GIT_READ|{'commit','init','add','config'}:result['unknown_effect']=True
  elif n in {'curl','wget','pip','pip3','npm','npx'}:
   result['network_targets'].extend(re.findall(r'https?://[^\s\'\"]+',command))
   if n in {'curl','wget'} and not result['network_targets']:result['parsed']=False
   if n in {'pip','pip3','npm','npx'} and not result['network_targets']:result['unknown_effect']=True
   for flag in ('-o','-O','--output','--output-document'):
    if flag in args and args.index(flag)+1<len(args):result['write_paths'].append(args[args.index(flag)+1])
  elif n in WRITE:
   result['write_paths'].extend(x for x in args if not x.startswith('-'))
  elif n in READ:
   if n=='find' and any(x in args for x in ('-exec','-execdir','-delete')):result['parsed']=False
   if n=='sed' and any(x.startswith('-i') for x in args):result['write_paths'].extend(x for x in args if not x.startswith('-'))
   if n in {'awk','sed'} and any(re.search(r'\b(system|exec)\b',x) for x in args):result['parsed']=False
   if n not in {'echo','printf','test','true','false','which'}:result['read_paths'].extend(x for x in args if not x.startswith('-') and ('.' in x or '/' in x))
  else:result['unknown_effect']=True
 def visit(node):
  if node.kind=='redirect' and getattr(node,'output',None) and hasattr(node.output,'word'):
   value=node.output.word
   if value!='/dev/null':result['read_paths' if node.type.startswith('<') else 'write_paths'].append(value)
  for value in vars(node).values():
   if isinstance(value,bashlex.ast.node):visit(value)
   elif isinstance(value,list):
    for child in value:
     if isinstance(child,bashlex.ast.node):visit(child)
 try:
  for tree in bashlex.parse(command):visit(tree)
 except (ValueError,TypeError,NotImplementedError,bashlex.errors.ParsingError):result['parsed']=False
 for key in ('read_paths','write_paths','network_targets'):result[key]=list(dict.fromkeys(result[key]))
 result['kind']='git.push' if result['git_action']=='git.push' else 'network' if result['network_targets'] else 'write' if result['write_paths'] or result['git_action'] else 'unknown' if result['unknown_effect'] else 'read'
 return result
