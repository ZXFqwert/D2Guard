"""Host Unix-socket TCP relay to the configured provider only; no payload logging.
The isolated runtime sees this socket, but command namespaces never mount it.
TLS remains end-to-end between httpx and the configured provider.
"""
import json,socket,socketserver,threading
from pathlib import Path
from urllib.parse import urlsplit
root=Path(__file__).resolve().parents[2]
cfg=json.loads((root/'.local/provider.json').read_text());url=urlsplit(cfg['base_url'])
if url.scheme!='https':raise ValueError('Stage G relay requires upstream TLS')
path=root/'.local/stage-g/upstream.sock'
if path.exists():raise RuntimeError('Socket exists; inspect existing relay before restart')
class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  remote=socket.create_connection((url.hostname,url.port or 443),timeout=120)
  def copy(a,b):
   try:
    while True:
     data=a.recv(65536)
     if not data:break
     b.sendall(data)
   except OSError:pass
   finally:
    try:b.shutdown(socket.SHUT_WR)
    except OSError:pass
  t=threading.Thread(target=copy,args=(self.request,remote),daemon=True);t.start();copy(remote,self.request);t.join(timeout=2);remote.close()
class Server(socketserver.ThreadingUnixStreamServer):daemon_threads=True
with Server(str(path),Handler) as server:
 path.chmod(0o600);server.serve_forever()
