"""Container-only command execution in an additional unprivileged mount/PID namespace."""
import os,subprocess
from pathlib import Path

def command_argv(tool,args):
 if tool=='exec':return ['/bin/sh','-c',args['command']]
 if tool=='git_push':return ['/usr/bin/git','push',args.get('remote','origin'),args.get('ref','HEAD')]
 if tool=='git_commit':return ['/usr/bin/git','-c','user.name=D2 Lab','-c','user.email=lab@example.invalid','commit','-m',args['message']]
 raise ValueError('Unknown sandbox tool')

def execute(workspace,tool,args,timeout=None):
 if os.environ.get('D2_OS_SANDBOX')!='1' or not Path('/.dockerenv').exists():
  raise RuntimeError('exec/git require the verified container deployment')
 root=Path(workspace).resolve(strict=True)
 argv=['/usr/bin/bwrap','--unshare-all','--share-net','--die-with-parent','--new-session','--cap-drop','ALL',
       '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64',
       '--dev','/dev','--tmpfs','/tmp','--dir','/etc','--ro-bind','/etc/hosts','/etc/hosts',
       '--ro-bind','/etc/resolv.conf','/etc/resolv.conf','--bind',str(root),'/workspace','--chdir','/workspace',
       '--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/workspace/.home',
       '--setenv','LANG','C.UTF-8','--',*command_argv(tool,args)]
 p=subprocess.run(argv,cwd=root,env={'PATH':'/usr/bin:/bin'},capture_output=True,timeout=timeout)
 text=(p.stdout+p.stderr)[:65536].decode('utf-8',errors='replace')
 return {'text':text,'exit_code':p.returncode,'is_error':p.returncode!=0,'truncated':len(p.stdout)+len(p.stderr)>65536}
