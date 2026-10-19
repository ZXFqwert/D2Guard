"""Real isolated MCP fixture, both transports share the same implementation."""
import json,sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
fixture={};notes=[]
def handle(request):
    global fixture
    method=request.get('method');rid=request.get('id');params=request.get('params',{})
    if rid is None:return None
    if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'d2-local-docs','version':'2.0'}}
    elif method=='fixture/configure':fixture=params;result={'configured':True}
    elif method=='tools/list':
        result={'tools':[{'name':'project_facts','description':fixture.get('mcp_description','Read public project facts. No parameters and no side effects.'),'inputSchema':{'type':'object','properties':{},'additionalProperties':False}}]}
        if fixture.get('mcp_write'):result['tools'].append({'name':'save_note','description':'Save a project handoff note in the local MCP server note store.','inputSchema':{'type':'object','properties':{'content':{'type':'string'}},'required':['content'],'additionalProperties':False}})
    elif method=='tools/call' and params.get('name')=='project_facts' and not params.get('arguments'):
        result={'content':[{'type':'text','text':fixture.get('mcp_return','Aster Tasks stores tasks in SQLite and exports CSV.')}],'isError':False}
    elif method=='tools/call' and params.get('name')=='save_note' and fixture.get('mcp_write') and isinstance(params.get('arguments',{}).get('content'),str):
        notes.append(params['arguments']['content']);result={'content':[{'type':'text','text':'Saved note '+str(len(notes))+': '+notes[-1]}],'isError':False}
    else:return {'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Unknown method or invalid arguments'}}
    return {'jsonrpc':'2.0','id':rid,'result':result}
if __name__=='__main__':
    if '--http' in sys.argv:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                n=int(self.headers.get('Content-Length',0))
                if n>262144:self.send_error(413);return
                result=handle(json.loads(self.rfile.read(n)))
                body=json.dumps(result).encode() if result is not None else b''
                self.send_response(200 if result is not None else 202);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        print('http://127.0.0.1:'+str(server.server_port)+'/mcp',flush=True);server.serve_forever()
    else:
        for line in sys.stdin:
            result=handle(json.loads(line))
            if result is not None:print(json.dumps(result),flush=True)
