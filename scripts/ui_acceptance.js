async (page) => {
  await page.goto("http://127.0.0.1:5173");
  const flows = async (page) => {
  const errors = [], failures = [], endpoints = new Set(), results = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('response', r => { if (r.url().startsWith('http://127.0.0.1:8765/')) { endpoints.add(new URL(r.url()).pathname.replace(/sessions\/[^/]+\//, 'sessions/SESSION/')); if (!r.ok()) failures.push({url:r.url(),status:r.status()}); } });
  const assert = (value, message) => { if (!value) throw new Error(message); };
  await page.setViewportSize({width:1600,height:1000});
  await page.getByRole('button',{name:'执行工作台',exact:true}).click();
  await page.getByRole('button',{name:'重置会话',exact:true}).waitFor();
  await page.screenshot({path:'output/playwright/normal-mode.png'});
  const play = async (id, approve = true) => {
    await page.getByRole('combobox',{name:'快捷演练剧本'}).selectOption(id);
    await page.getByRole('button',{name:'演练 ↗',exact:true}).click();
    const deadline = Date.now() + 180000;
    let asks = 0;
    while(Date.now() < deadline) {
      if(await page.getByRole('button',{name:'批准本次动作',exact:true}).isVisible()) {
        asks++;
        assert(!await page.getByRole('button',{name:'重置会话',exact:true}).isEnabled(),'Session reset must be locked during ASK');
        if(id === 'PB-06') await page.screenshot({path:'output/playwright/ask-approval.png'});
        await page.getByRole('button',{name:approve ? '批准本次动作' : '拒绝并阻断',exact:true}).click();
      }
      if(await page.getByRole('button',{name:'重置会话',exact:true}).isEnabled()) break;
      await page.waitForTimeout(120);
    }
    assert(await page.getByRole('button',{name:'重置会话',exact:true}).isEnabled(), 'Playbook timed out '+id);
    assert(await page.locator('.run-state').innerText() === '审计完成', 'Run failed '+id);
    const verdicts = await page.locator('.verdict-card > .row-between .badge').allTextContents();
    const text = await page.locator('body').innerText();
    assert(!/\$D\^/.test(text),'Unescaped math');
    assert(!/\d+\.\d{3,}\s?ms/.test(text),'Unformatted latency');
    results.push({id, asks, verdicts});
    return verdicts;
  };
  // Run all six scenarios in ordinary mode through the actual kernel.
  for (let i=1;i<=6;i++) { const v = await play('PB-0'+i); assert(v.length && v.every(x => x.includes('ALLOW')), 'Armor off must allow PB-0'+i); }
  await page.getByRole('button',{name:'启动双镜铠甲',exact:true}).click();
  await page.getByTestId('armor-frame').waitFor();
  await page.getByRole('button',{name:'重置会话',exact:true}).click();
  await page.getByRole('heading',{name:'让 Agent 放手做事， 让双镜守住边界。'}).waitFor();
  await page.screenshot({path:'output/playwright/armor-mode.png'});
  // Guarded runs include real remote slow-mirror reviews.
  for (let i=1;i<=6;i++) { const v = await play('PB-0'+i); if(i<6) assert(v.some(x=>x.includes('BLOCK')), 'Guard must block PB-0'+i); }
  await play('PB-06', false);
  assert((await page.locator('.verdict-card > .row-between .badge').last().innerText()).includes('BLOCK'),'ASK rejection must block');
  await page.getByRole('textbox',{name:'任务或 JSON 工具动作'}).fill(JSON.stringify({initial_task:'只读检视项目 README',tool_name:'git.push',tool_args:{remote:'origin/main'}}));
  await page.getByRole('button',{name:'执行任务',exact:true}).click();
  await page.waitForFunction(() => document.querySelector('.run-state')?.textContent === '审计完成', null, {timeout:60000});
  assert((await page.locator('.verdict-card').innerText()).includes('POL-GIT-REVIEW-NO-PUSH'),'Free JSON must hit real policy');
  await page.getByRole('textbox',{name:'任务或 JSON 工具动作'}).fill('只读检视 README.md，请申请 fs.read 读取 README.md，不要修改文件。');
  await page.getByRole('button',{name:'执行任务',exact:true}).click();
  await page.waitForFunction(() => document.querySelector('.run-state')?.textContent === '审计完成', null, {timeout:60000});
  assert((await page.locator('.tool-card').innerText()).includes('fs.read'),'Real main model must propose tool action');
  await page.getByRole('button',{name:'展开安全详情'}).click();
  await page.screenshot({path:'output/playwright/workbench-live.png'});
  await page.getByRole('button',{name:'防护总览',exact:true}).click();
  await page.setViewportSize({width:1600,height:1700});
  await page.screenshot({path:'output/playwright/dashboard.png'});
  assert(await page.locator('.kpi').count()===4,'Four KPI cards');
  assert(await page.locator('.line-chart circle').count()>0,'Real statistics must populate curves');
  await page.locator('table tbody tr').first().click();
  await page.getByRole('heading',{name:'节点证据检查器'}).waitFor();
  assert((await page.locator('.evidence-inspector').innerText()).includes('token_span'),'Recent events navigate to evidence');
  assert(errors.length===0,errors.join('\n'));
  assert(failures.length===0,JSON.stringify(failures));
  for(const name of ['events/ingest','actions/decide','actions/approve','sessions/SESSION/telemetry','sessions/SESSION/armor']) assert(endpoints.has('/api/v1/'+name),'Missing actual endpoint '+name);
  return {passed:true,results,pageErrors:errors,httpFailures:failures,endpoints:[...endpoints]};
};
  const management = async (page) => {
  const errors=[],failures=[]; page.on('pageerror',e=>errors.push(String(e))); page.on('response',r=>{if(r.url().includes('127.0.0.1:8765')&&!r.ok()) failures.push(r.status());});
  const assert=(v,m)=>{if(!v)throw new Error(m);};
  await page.setViewportSize({width:1600,height:1000});
  await page.getByRole('button',{name:'场景库管理',exact:true}).click();
  await page.getByRole('heading',{name:'场景库管理',exact:true}).waitFor();
  assert(await page.locator('tbody tr').count()===6,'Six official scenarios');
  await page.setViewportSize({width:1600,height:1100});
  await page.screenshot({path:'output/playwright/scenario-library.png'});
  await page.setViewportSize({width:1600,height:1000});
  await page.getByRole('textbox',{name:'搜索场景'}).fill('PB-04');
  assert(await page.locator('tbody tr').count()===1,'Search filters');
  await page.getByRole('textbox',{name:'搜索场景'}).fill('');
  await page.getByRole('combobox',{name:'能力分类筛选'}).selectOption('对抗混淆');
  assert(await page.locator('tbody tr').count()===2,'Category filters');
  await page.getByRole('combobox',{name:'能力分类筛选'}).selectOption('全部能力');
  await page.getByRole('combobox',{name:'风险等级筛选'}).selectOption('CRITICAL');
  assert(await page.locator('tbody tr').count()===3,'Risk filters');
  await page.getByRole('combobox',{name:'风险等级筛选'}).selectOption('全部风险');
  await page.getByRole('button',{name:'卡片视图',exact:true}).click();
  assert(await page.locator('.scenario-card').count()===6,'Card view');
  await page.getByRole('button',{name:'表格视图',exact:true}).click();
  await page.locator('.scenario-title').first().click();
  const detail=page.getByRole('dialog',{name:'场景详情'}); await detail.waitFor();
  assert((await detail.innerText()).includes('原始攻击载荷'),'Source payload detail');
  await detail.getByRole('button',{name:'关闭',exact:true}).click();
  await page.getByRole('button',{name:'新增场景',exact:true}).click();
  let dialog=page.getByRole('dialog');
  await dialog.getByLabel('场景名称',{exact:true}).fill('UI 验收自定义场景');
  await dialog.getByLabel('初始任务',{exact:true}).fill('只读检视 README');
  await dialog.getByLabel('预期策略 ID',{exact:true}).fill('POL-FS-WRITE-SENSITIVE');
  await dialog.getByRole('button',{name:'保存场景',exact:true}).click();
  const row=page.locator('tbody tr').filter({hasText:'UI 验收自定义场景'});
  await row.waitFor();
  await row.getByRole('button',{name:/编辑/}).click();
  await page.getByRole('dialog').getByLabel('场景名称',{exact:true}).fill('UI 验收已编辑场景');
  await page.getByRole('button',{name:'保存场景',exact:true}).click();
  const edited=page.locator('tbody tr').filter({hasText:'UI 验收已编辑场景'});
  await edited.waitFor();
  const downloadEvent=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出',exact:true}).click();
  const download=await downloadEvent; await download.saveAs('output/playwright/scenarios-export.json');
  const exported=JSON.parse(await page.evaluate(()=>localStorage.getItem('d2guard.scenarios.v2')));
  assert(exported.length===7 && exported.some(s=>s.title==='UI 验收已编辑场景'),'CRUD persisted');
  await page.getByLabel('导入场景 JSON').setInputFiles({name:'scenario-package.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify([exported.at(-1)]))});
  await page.getByText(/已导入 1 个场景/).waitFor();
  assert(await page.locator('tbody tr').count()===8,'Import adds independent custom scenario');
  const invalid=page.getByLabel('导入场景 JSON');
  await invalid.setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{broken')});
  await page.getByRole('alert').waitFor();
  assert(await page.locator('tbody tr').count()===8,'Invalid import must not mutate library');
  // Run imported scenario through the original harness, then inspect its real result.
  const custom=page.locator('tbody tr').filter({hasText:'UI 验收已编辑场景'}).first();
  await custom.getByRole('button',{name:/运行/}).click();
  await page.waitForFunction(()=>document.querySelector('.run-state')?.textContent==='审计完成',null,{timeout:60000});
  assert((await page.locator('.verdict-card').innerText()).includes('BLOCK'),'Custom scenario must run against kernel');
  await page.getByRole('button',{name:'场景库管理',exact:true}).click();
  for(let i=0;i<2;i++) { await page.locator('tbody tr').filter({hasText:'UI 验收已编辑场景'}).first().getByRole('button',{name:/删除/}).click(); await page.getByRole('button',{name:'确认删除',exact:true}).click(); }
  assert(await page.locator('tbody tr').count()===6,'Delete only custom scenarios');
  // Model settings are read from and written back to the real kernel, retaining the secret.
  await page.getByRole('button',{name:'设置与接入',exact:true}).click();
  await page.getByLabel('Base URL',{exact:true}).waitFor();
  await page.getByRole('button',{name:'拉取/测试模型',exact:true}).click();
  await page.getByText('已连接模型服务并取得可用模型',{exact:true}).waitFor({timeout:30000});
  assert((await page.getByLabel('当前主模型').locator('option').count())>=1,'Real model list');
  await page.getByRole('button',{name:'保存并同步后端',exact:true}).click();
  await page.getByText('已保存到本地内核，主模型与慢镜配置立即生效',{exact:true}).waitFor();
  assert(await page.locator('.policy-list details').count()===5,'Five actual YAML policies');
  assert((await page.locator('body').innerText()).includes('heuristic'),'Real Laya fallback health');
  await page.screenshot({path:'output/playwright/settings-model.png'});
  // Select the cross-MCP session already produced by the flow suite.
  await page.getByRole('button',{name:'溯源分析',exact:true}).click();
  const options=await page.getByRole('combobox',{name:'分析会话'}).locator('option').evaluateAll(es=>es.map(e=>({value:e.value,label:e.textContent})));
  const cross=options.find(o=>o.label.includes('跨 MCP')&&o.label.includes('铠甲'));
  assert(cross,'Guarded cross-MCP session exists');
  await page.getByRole('combobox',{name:'分析会话'}).selectOption(cross.value);
  await page.getByRole('button',{name:'DAG 拓扑图',exact:true}).click();
  await page.locator('.react-flow__node').first().waitFor();
  await page.waitForTimeout(500);
  const bounds=await page.locator('.react-flow__node').evaluateAll(ns=>ns.map(n=>({id:n.dataset.id,x:n.getBoundingClientRect().x,y:n.getBoundingClientRect().y,w:n.getBoundingClientRect().width,h:n.getBoundingClientRect().height})));
  for(let i=0;i<bounds.length;i++)for(let j=i+1;j<bounds.length;j++){const a=bounds[i],b=bounds[j];assert(a.x+a.w<=b.x+.5||b.x+b.w<=a.x+.5||a.y+a.h<=b.y+.5||b.y+b.h<=a.y+.5,'DAG overlap '+a.id+' / '+b.id);}
  assert(await page.locator('.dag-node.block').count()>0,'Blocked nodes red');
  const color=await page.locator('.dag-node.block').first().evaluate(n=>getComputedStyle(n).borderColor);
  assert(color==='rgb(197, 94, 89)','Real red border');
  await page.setViewportSize({width:1600,height:1150});
  await page.screenshot({path:'output/playwright/trace-analysis.png'});
  await page.setViewportSize({width:1600,height:1000});
  await page.locator('.dag-node.block').first().click();
  await page.getByRole('heading',{name:'节点证据检查器'}).waitFor();
  assert(await page.locator('.highlighted-text mark').count()>0,'Character span highlight');
  assert(await page.locator('.token-map .tainted').count()>0,'Token span highlight');
  await page.screenshot({path:'output/playwright/trace-evidence.png'});
  await page.getByRole('button',{name:'时序链路',exact:true}).click();
  assert(await page.locator('.timeline-row').count()>0,'Timeline uses logs');
  await page.screenshot({path:'output/playwright/trace-timeline.png'});
  for(const [name,path] of [['Markdown 报告','output/playwright/audit-report.md'],['JSONL 证据','output/playwright/audit-evidence.jsonl']]) { const pending=page.waitForEvent('download');await page.getByRole('button',{name,exact:true}).click();await (await pending).saveAs(path); }
  await page.setViewportSize({width:390,height:844});
  for(const name of ['防护总览','执行工作台','场景库管理','溯源分析','设置与接入']) { await page.getByRole('button',{name,exact:true}).click(); assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Mobile overflow '+name); }
  await page.getByRole('button',{name:'执行工作台',exact:true}).click();
  await page.screenshot({path:'output/playwright/mobile-workbench.png'});
  await page.setViewportSize({width:1600,height:1000});
  await page.getByRole('button',{name:'场景库管理',exact:true}).click();
  assert(errors.length===0,errors.join('\n')); assert(failures.length===0,JSON.stringify(failures));
  return {passed:true,checks:['search','category and risk filters','cards and table','details','create','edit','persist','import','invalid import atomicity','export','real custom scenario','delete','real model list','config sync','Laya health','five YAML policies','DAG non-overlap','red BLOCK nodes','char span','token span','timeline','Markdown and JSONL exports','five mobile layouts'],pageErrors:errors,httpFailures:failures};
};
  return { flows: await flows(page), management: await management(page) };
}
