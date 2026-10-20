"""Host workspace executor with application limits; this is not an OS sandbox."""
import os,subprocess,shutil,sys
from pathlib import Path
from urllib.parse import urlsplit
from d2v2.command_effects import command_effects
from process_tree import ProcessTree


def shell_path():
 if os.name!='nt':return '/bin/sh'
 override=os.environ.get('D2_BASH')
 git=shutil.which('git')
 candidates=[Path(override)] if override else []
 if git:
  base=Path(git).resolve().parent.parent
  candidates.extend([base/'bin/bash.exe',base/'usr/bin/bash.exe'])
 for variable in ('ProgramFiles','LOCALAPPDATA'):
  if os.environ.get(variable):candidates.append(Path(os.environ[variable])/'Git/bin/bash.exe')
 for candidate in candidates:
  if candidate.is_file():return str(candidate)
 raise RuntimeError('Install Git for Windows (including Git Bash), or set D2_BASH to its bash.exe')


def command_environment(home):
 env={'HOME':str(home),'LANG':'C.UTF-8'}
 if os.name!='nt':
  env['PATH']=os.defpath
  return env
 shell=Path(shell_path());base=shell.parent.parent
 paths=[str(base/'usr/bin'),str(base/'mingw64/bin'),str(base/'bin'),str(Path(sys.executable).parent)]
 for executable in ('python','node','git'):
  found=shutil.which(executable)
  if found:paths.append(str(Path(found).parent))
 for key in ('SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC'):
  if key in os.environ:env[key]=os.environ[key]
 if os.environ.get('SYSTEMROOT'):paths.append(str(Path(os.environ['SYSTEMROOT'])/'System32'))
 env.update(PATH=os.pathsep.join(dict.fromkeys(paths)),USERPROFILE=str(home),PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
 return env


def command_argv(tool,args):
 if tool=='exec':return [shell_path(),'-c',args['command']]
 if tool=='git_push':return ['git','push',args.get('remote','origin'),args.get('ref','HEAD')]
 if tool=='git_commit':return ['git','-c','user.name=D2 Lab','-c','user.email=lab@example.invalid','commit','-m',args['message']]
 raise ValueError('Unknown workspace tool')


def execute(workspace,tool,args,timeout=None,lab_origin=None):
 if os.environ.get('D2_HOST_EXEC')!='1':raise RuntimeError('Host command tools are not enabled')
 root=Path(workspace).resolve(strict=True);home=root/'.home';home.mkdir(exist_ok=True)
 env=command_environment(home)
 command=args.get('command','') if tool=='exec' else 'git '+('push '+args.get('remote','origin')+' '+args.get('ref','HEAD') if tool=='git_push' else 'commit')
 effects=command_effects(command,root)
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
 with ProcessTree() as tree:
  p=tree.popen(argv,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  timed_out=False
  try:
   stdout,stderr=p.communicate(timeout=timeout)
  except subprocess.TimeoutExpired:
   timed_out=True;tree.close();stdout,stderr=p.communicate(timeout=10)
 text=(stdout+stderr)[:65536].decode('utf-8',errors='replace')
 return {'text':text,'exit_code':p.returncode,'is_error':p.returncode!=0 or timed_out,'timed_out':timed_out,'truncated':len(stdout)+len(stderr)>65536}
