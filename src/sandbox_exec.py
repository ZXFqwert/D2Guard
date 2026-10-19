"""Host workspace executor with application limits; this is not an OS sandbox."""
import os,signal,subprocess,re
from pathlib import Path
from urllib.parse import urlsplit
from d2v2.command_effects import command_effects


def command_argv(tool,args):
 if tool=='exec':return ['/bin/sh','-c',args['command']]
 if tool=='git_push':return ['git','push',args.get('remote','origin'),args.get('ref','HEAD')]
 if tool=='git_commit':return ['git','-c','user.name=D2 Lab','-c','user.email=lab@example.invalid','commit','-m',args['message']]
 raise ValueError('Unknown workspace tool')


def execute(workspace,tool,args,timeout=None,lab_origin=None):
 if os.environ.get('D2_HOST_EXEC')!='1':raise RuntimeError('Host command tools are not enabled')
 if os.name!='posix':raise RuntimeError('The verified host executor currently requires POSIX process groups')
 root=Path(workspace).resolve(strict=True);home=root/'.home';home.mkdir(exist_ok=True)
 env={'PATH':os.defpath,'HOME':str(home),'LANG':'C.UTF-8'}
 command=args.get('command','') if tool=='exec' else 'git '+('push '+args.get('remote','origin')+' '+args.get('ref','HEAD') if tool=='git_push' else 'commit')
 effects=command_effects(command)
 if not effects['parsed']:raise ValueError('Dynamic shell syntax is not supported by this application executor')
 for value in effects['read_paths']+effects['write_paths']:
  if value in ('/dev/null',):continue
  target=(home/value[2:] if value.startswith('~/') else root/value).resolve()
  if not target.is_relative_to(root):raise ValueError('Command path escaped the per-run workspace')
 if effects['git_action']=='git.push' or tool=='git_push':
  expected=(root/'.lab-remote.git').resolve()
  remote=subprocess.run(['git','remote','get-url','origin'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',check=True).stdout.strip()
  if (root/remote).resolve()!=expected:raise ValueError('Git origin must be this run bare repository')
  if tool=='git_push' and args.get('remote','origin')!='origin':raise ValueError('Only the per-run origin is available')
  for argv in effects['commands']:
   if argv[0]=='git' and 'push' in argv:
    tail=argv[argv.index('push')+1:]
    if tail and tail[0]!='origin':raise ValueError('Only the per-run origin is available')
 for url in effects['network_targets']:
  if url=='git-remote:origin':continue
  u=urlsplit(url)
  if not lab_origin or u.scheme!='http' or u.netloc!='lab.test' or u.username or u.password:raise ValueError('Downloads are confined to the local lab service')
  if u.path not in {'/install.sh','/docs/project','/collect'}:raise ValueError('Unsupported lab resource')
 if tool=='exec':
  args={**args,'command':command.replace('http://lab.test',lab_origin or 'http://lab.test')}
 argv=command_argv(tool,args)
 p=subprocess.Popen(argv,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 timed_out=False
 try:
  stdout,stderr=p.communicate(timeout=timeout)
 except subprocess.TimeoutExpired:
  timed_out=True;os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
 finally:
  try:os.killpg(p.pid,signal.SIGKILL)
  except ProcessLookupError:pass
 text=(stdout+stderr)[:65536].decode('utf-8',errors='replace')
 return {'text':text,'exit_code':p.returncode,'is_error':p.returncode!=0 or timed_out,'timed_out':timed_out,'truncated':len(stdout)+len(stderr)>65536}
