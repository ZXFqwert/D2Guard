"""Export private, evaluation-only human annotation packets, never gold labels."""
import argparse
import hashlib
import html
import json
import sqlite3
from pathlib import Path
from verify_v2 import rows


def write_jsonl(path,items):
    path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in items),encoding='utf-8')


def export(folders,out):
    out.mkdir(parents=True,exist_ok=True)
    full=[];state=[];fragments=[]
    for folder in folders:
        with sqlite3.connect(folder.joinpath('state.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            events=[dict(r) for r in db.execute('SELECT * FROM events ORDER BY created,rowid')]
            by_id={e['id']:e for e in events}
            for d in rows(folder/'decisions.jsonl'):
                if d.get('type')!='decision':continue
                cid=d['call_id'];pre=by_id['pre-'+hashlib.sha256(cid.encode()).hexdigest()]
                action=json.loads(pre['raw'])
                common={'item_id':folder.name+':'+cid,'kind':'action','evaluation_only':True,
                        'training_allowed':False,'label':None,'reason':None,'action':action,
                        'run_id':folder.name,'call_id':cid}
                # No runtime verdict, rule IDs, model answers, or after-action evidence.
                full.append({**common,'variant':'full','original_history':[
                    {k:e[k] for k in ('id','agent','kind','source','uri','raw','sha')}
                    for e in events if e['created']<pre['created']]})
                state.append({**common,'variant':'state','S_t':d['previous_security_state'],
                              'views':{q:v['payload'] for q,v in d['fast'].get('views',{}).items()}})
            for e in events:
                if e['source'] not in {'USER_QUOTED','WEB','LOCAL_FILE','CODE','ISSUE','EMAIL','PDF_META','MCP_DESC','MCP_RET','MEMORY','SUBAGENT'}:continue
                norm=db.execute('SELECT data FROM normalized_evidence WHERE event_id=?',(e['id'],)).fetchone()
                offsets=json.loads(norm[0]).get('raw_token_offsets') if norm else None
                spans=([[offsets[i][0],offsets[min(i+255,len(offsets)-1)][1]] for i in range(0,len(offsets),256)]
                       if offsets else [[i,min(i+1024,len(e['raw']))] for i in range(0,len(e['raw']),1024)])
                for index,(a,b) in enumerate(spans):
                    fragments.append({'item_id':folder.name+':'+e['id']+':'+str(index),'kind':'fragment','variant':'fragment',
                        'evaluation_only':True,'training_allowed':False,'label':None,'reason':None,
                        'source':e['source'],'uri':e['uri'],'event_id':e['id'],'sha256':e['sha'],
                        'char_span':[a,b],'chunk_unit':'model_token' if offsets else 'unicode_character',
                        'text':e['raw'][a:b]})
    for name,items in [('full',full),('state',state),('fragments',fragments)]:
        write_jsonl(out/(name+'.jsonl'),items)
        # One packet per view: no button reveals the other annotation condition.
        data=json.dumps(items,ensure_ascii=False).replace('<','\\u003c')
        page=PAGE.replace('__DATA__',data).replace('__NAME__',name)
        (out/(name+'.html')).write_text(page,encoding='utf-8')
    manifest={'evaluation_only':True,'training_allowed':False,'gold_labels_created':False,
              'runs':[p.name for p in folders],'actions':len(full),'fragments':len(fragments),
              'files':{name:hashlib.sha256((out/name).read_bytes()).hexdigest()
                       for name in ('full.jsonl','full.html','state.jsonl','state.html','fragments.jsonl','fragments.html')}}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


PAGE='''<!doctype html><meta charset="utf-8"><title>D2Guard human annotation — __NAME__</title>
<style>body{max-width:1000px;margin:30px auto;font:16px system-ui}pre{white-space:pre-wrap;background:#f4f5f7;padding:20px}input,select,button{padding:8px;margin:5px}</style>
<h1>人工标注 · __NAME__</h1><p>仅用于评测。标签由人独立填写；未标注保持空值。完整视图和状态视图请独立分配，勿对照填写。</p>
<label>标注者 <input id="rater"></label><button id="prev">上一条</button><button id="next">下一条</button><span id="count"></span>
<pre id="packet"></pre><label>标签 <select id="label"></select></label>
<label>原因 <select id="reason"><option value="">未填写</option><option>schema_missing_field</option><option>view_missing_fragment</option><option>human_disagreement</option><option>other</option></select></label>
<input id="note" placeholder="说明"><button id="download">导出 JSONL 标注</button>
<script>const items=__DATA__;let i=0;const answers=items.map(x=>({item_id:x.item_id,variant:x.variant,label:null,reason:null,note:''}));
const el=id=>document.getElementById(id);function save(){if(!items.length)return;Object.assign(answers[i],{label:el('label').value||null,reason:el('reason').value||null,note:el('note').value})}
function show(){if(!items.length){el('packet').textContent='无可标注记录';return}el('count').textContent=(i+1)+' / '+items.length;el('packet').textContent=JSON.stringify(items[i],null,2);el('label').replaceChildren();for(const v of ['',...(items[i].kind==='action'?['ALLOW','ASK','BLOCK']:['to_agent','task_data','unclear'])]){const o=document.createElement('option');o.value=v;o.textContent=v||'未标注';el('label').append(o)}el('label').value=answers[i].label||'';el('reason').value=answers[i].reason||'';el('note').value=answers[i].note}
el('prev').onclick=()=>{save();i=Math.max(0,i-1);show()};el('next').onclick=()=>{save();i=Math.min(items.length-1,i+1);show()};
el('download').onclick=()=>{save();if(!el('rater').value.trim()){alert('请填写标注者');return}const text=answers.map(x=>JSON.stringify({...x,rater:el('rater').value,evaluation_only:true})).join('\\n')+'\\n';const url=URL.createObjectURL(new Blob([text],{type:'application/x-ndjson'}));const a=document.createElement('a');a.href=url;a.download='annotations-__NAME__.jsonl';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};show();</script>'''


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folders',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(export(a.folders,a.output),ensure_ascii=False,indent=2))
