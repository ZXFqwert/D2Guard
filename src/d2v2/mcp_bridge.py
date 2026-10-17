"""MCP stdio bridge with an actual initialize/list/call lifecycle and bounded replies."""
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path


class MCPBridge:
    def __init__(self, observe, fixture=None):
        self.observe=observe;self.server_id='local-docs';self.next_id=0
        self.lock=threading.Lock();self.responses=queue.Queue(maxsize=8)
        self.process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('mcp_fixture.py'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
            env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','TEMP','TMP','USERPROFILE','APPDATA'}})
        self.reader=threading.Thread(target=self._reader,daemon=True);self.reader.start()
        if fixture:self.request('fixture/configure',{k:v for k,v in fixture.items() if k in {'mcp_description','mcp_return'}})
        handshake=self.request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'D2Guard','version':'2'}})
        if handshake.get('protocolVersion')!='2024-11-05':
            self.close();raise ValueError('Unsupported MCP protocol version')
        self._send({'jsonrpc':'2.0','method':'notifications/initialized'})
        self.tools=self.request('tools/list',{})['tools']
        for tool in self.tools:
            observe({'type':'mcp_description','event_id':'mcp-desc-'+self.server_id+'-'+tool['name'],
                'agent_id':'mcp-probe','server_id':self.server_id,'tool_name':tool['name'],
                'text':json.dumps(tool,ensure_ascii=False)})

    def _reader(self):
        try:
            while True:
                line=self.process.stdout.readline(262145)
                if not line or len(line)>262144:break
                self.responses.put(json.loads(line),timeout=1)
        except Exception:pass

    def _send(self,payload):
        self.process.stdin.write(json.dumps(payload)+'\n');self.process.stdin.flush()

    def request(self,method,params):
        with self.lock:
            self.next_id+=1;rid=self.next_id
            self._send({'jsonrpc':'2.0','id':rid,'method':method,'params':params})
            reply=self.responses.get(timeout=10)
            if reply.get('jsonrpc')!='2.0' or reply.get('id')!=rid or 'error' in reply:raise ValueError('MCP response failed validation')
            return reply['result']

    def call(self,name,args):
        if name not in {t['name'] for t in self.tools}:raise ValueError('Unregistered MCP tool')
        return self.request('tools/call',{'name':name,'arguments':args})

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdin.close();self.process.stdout.close()
