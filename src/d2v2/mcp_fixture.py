"""A real local MCP stdio server for bridge conformance checks (no attack replay)."""
import json
import sys
fixture={}

for line in sys.stdin:
    request=json.loads(line);method=request.get('method');rid=request.get('id')
    if rid is None:continue
    if method=='fixture/configure':
        fixture=request['params'];result={'configured':True}
    elif method=='initialize':
        result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'d2-local-docs','version':'1.0'}}
    elif method=='tools/list':
        result={'tools':[{'name':'project_facts','description':fixture.get('mcp_description','Read public project facts. No parameters and no side effects.'),
            'inputSchema':{'type':'object','properties':{},'additionalProperties':False}}]}
    elif method=='tools/call' and request.get('params',{}).get('name')=='project_facts' and not request['params'].get('arguments'):
        result={'content':[{'type':'text','text':fixture.get('mcp_return','Aster Tasks stores tasks in SQLite and exports CSV.')}],'isError':False}
    else:
        print(json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Unknown method or invalid arguments'}}),flush=True);continue
    print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
