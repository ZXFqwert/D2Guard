"""Host-configured MCP proxy: stdio and Streamable HTTP JSON/SSE responses."""
import json,os,queue,re,subprocess,sys,threading
from pathlib import Path
import httpx

class MCPBridge:
    def __init__(self,observe,fixture=None,config=None,configure_fixture=None):
        if configure_fixture is None:configure_fixture=not config
        config=config or {};fixture=fixture or {}
        self.observe=observe;self.server_id=config.get('server_id','local-docs');self.next_id=0
        self.lock=threading.Lock();self.responses=queue.Queue(maxsize=64)
        self.process=None;self.reader=None;self.client=None;self.session=None
        self.transport=config.get('transport',fixture.get('mcp_transport','stdio'))
        if self.transport not in {'stdio','http'}:raise ValueError('Unsupported MCP transport')
        self.url=config.get('url')
        command=config.get('command') or [sys.executable,str(Path(__file__).with_name('mcp_fixture.py'))]
        if self.transport=='stdio' or not self.url:
            if self.transport=='http':command=[*command,'--http']
            self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
                env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','TEMP','TMP','USERPROFILE','APPDATA'}})
            if self.transport=='http':self.url=self.process.stdout.readline().strip()
            else:
                self.reader=threading.Thread(target=self._reader,daemon=True);self.reader.start()
        if self.transport=='http':self.client=httpx.Client(timeout=30,trust_env=False,follow_redirects=False)
        try:
            handshake=self.request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'D2Guard','version':'2'}})
            self.protocol=handshake.get('protocolVersion')
            if self.protocol not in {'2024-11-05','2025-03-26','2025-06-18'}:raise ValueError('Unsupported MCP protocol version')
            self._send({'jsonrpc':'2.0','method':'notifications/initialized'})
            if configure_fixture:self.request('fixture/configure',{k:v for k,v in fixture.items() if k in {'mcp_description','mcp_return','mcp_write'}})
            self.tools=[];cursor=None
            for _ in range(20):
                page=self.request('tools/list',{'cursor':cursor} if cursor else {})
                self.tools.extend(page['tools']);cursor=page.get('nextCursor')
                if not cursor:break
            else:raise ValueError('MCP tool pagination exceeded')
            if not self.tools or len({t['name'] for t in self.tools})!=len(self.tools):raise ValueError('Invalid MCP tools')
            for tool in self.tools:
                observe({'type':'mcp_description','event_id':'mcp-desc-'+self.server_id+'-'+tool['name'],'agent_id':'mcp-probe','server_id':self.server_id,'tool_name':tool['name'],'text':json.dumps(tool,ensure_ascii=False)})
        except Exception:
            self.close();raise

    def _reader(self):
        try:
            while True:
                line=self.process.stdout.readline(262145)
                if not line or len(line)>262144:break
                self.responses.put(json.loads(line),timeout=1)
        except Exception:pass

    def _send(self,payload):
        if self.transport=='stdio':
            self.process.stdin.write(json.dumps(payload)+'\n');self.process.stdin.flush();return
        headers={'Accept':'application/json, text/event-stream'}
        if self.session:headers['Mcp-Session-Id']=self.session
        if getattr(self,'protocol',None):headers['MCP-Protocol-Version']=self.protocol
        with self.client.stream('POST',self.url,json=payload,headers=headers) as response:
            response.raise_for_status()
            if response.headers.get('Mcp-Session-Id'):self.session=response.headers['Mcp-Session-Id']
            if 'id' not in payload:return
            if 'text/event-stream' in response.headers.get('content-type',''):
                total=0;data=[]
                for line in response.iter_lines():
                    total+=len(line)
                    if total>262144:raise ValueError('MCP reply too large')
                    if line.startswith('data:'):data.append(line[5:].lstrip())
                    elif not line and data:
                        item=json.loads('\n'.join(data));data=[]
                        if item.get('id')==payload['id']:return item
                raise ValueError('MCP SSE ended without response')
            body=b''
            for chunk in response.iter_bytes():
                body+=chunk
                if len(body)>262144:raise ValueError('MCP reply too large')
            return json.loads(body)

    def request(self,method,params):
        with self.lock:
            self.next_id+=1;rid=self.next_id
            reply=self._send({'jsonrpc':'2.0','id':rid,'method':method,'params':params})
            if self.transport=='stdio':
                while True:
                    reply=self.responses.get(timeout=30)
                    if 'id' in reply:break
            if reply.get('jsonrpc')!='2.0' or reply.get('id')!=rid or 'error' in reply:raise ValueError('MCP response failed validation')
            return reply['result']

    def call(self,name,args):
        if name not in {t['name'] for t in self.tools}:raise ValueError('Unregistered MCP tool')
        return self.request('tools/call',{'name':name,'arguments':args})

    def close(self):
        if self.client:self.client.close()
        if self.process:
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            if self.reader:self.reader.join(timeout=2)
            self.process.stdin.close();self.process.stdout.close()


SERVER_ID=re.compile(r'[a-z0-9][a-z0-9-]{0,40}')


class MCPRouter:
    """Several MCP servers attached to one task.

    With one server, tool names stay as the server reports them (unchanged single-bridge behaviour).
    With two or more, every tool is exposed as ``server_id/tool`` so same-named tools on different
    servers never collide; each call is routed to exactly one bridge and returns its server_id.
    Sources: host config ``{"servers":[{server_id,...},...]}`` or scenario fixture ``mcp_servers``.
    """
    def __init__(self,observe,fixture=None,config=None):
        fixture=fixture or {}
        if config and config.get('servers'):
            specs=[(dict(c),{},False) for c in config['servers']]
        elif not config and fixture.get('mcp_servers'):
            specs=[({'server_id':s.get('server_id'),'transport':s.get('mcp_transport',fixture.get('mcp_transport','stdio'))},s,True) for s in fixture['mcp_servers']]
        else:
            specs=[(config,fixture,None)]
        ids=[(c or {}).get('server_id','local-docs') for c,_,_ in specs]
        if len(specs)>1 and (len(set(ids))!=len(ids) or not all(isinstance(i,str) and SERVER_ID.fullmatch(i) for i in ids)):
            raise ValueError('MCP server ids must be unique lowercase identifiers')
        self.bridges={};self.multi=len(specs)>1
        try:
            for (cfg,fx,configure),sid in zip(specs,ids):
                if self.multi:cfg={**cfg,'server_id':sid}
                self.bridges[sid]=MCPBridge(observe,fixture=fx,config=cfg or None,configure_fixture=configure)
        except Exception:
            self.close();raise
        self.server_ids=list(self.bridges);self.server_id=self.server_ids[0] if not self.multi else None
        self.tools=[];self.routes={}
        for sid,bridge in self.bridges.items():
            for tool in bridge.tools:
                # Single-server tool descriptions stay byte-identical to the plain bridge.
                name=sid+'/'+tool['name'] if self.multi else tool['name']
                self.tools.append({**tool,'name':name,'server_id':sid} if self.multi else tool)
                self.routes[name]=(sid,tool['name'])

    def resolve(self,name):
        if name not in self.routes:raise ValueError('Unregistered MCP tool')
        return self.routes[name]

    def call(self,name,args):
        sid,tool=self.resolve(name)
        return {**self.bridges[sid].call(tool,args),'server_id':sid,'tool_name':tool}

    def close(self):
        for bridge in getattr(self,'bridges',{}).values():
            try:bridge.close()
            except Exception:pass
