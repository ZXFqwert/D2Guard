async (page) => {
  await page.goto('http://127.0.0.1:5173');
  const errors=[], failures=[]; let metrics=0;
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('response',r=>{ if(r.url().includes('127.0.0.1:8765')){if(!r.ok())failures.push(r.status());if(r.url().endsWith('/metrics'))metrics++;} });
  const assert=(v,m)=>{if(!v)throw new Error(m);};
  await page.getByRole('button',{name:'设置与接入',exact:true}).click();
  await page.getByRole('button',{name:'拉取/测试模型',exact:true}).click();
  await page.getByText('已连接模型服务并取得可用模型',{exact:true}).waitFor({timeout:30000});
  await page.getByRole('combobox',{name:'当前主模型',exact:true}).selectOption('Qwen/Qwen3.8-27B');
  await page.getByRole('combobox',{name:'慢镜裁判模型',exact:true}).selectOption('huihui-ai/Huihui-Qwen3.8-27B-abliterated');
  await page.getByRole('button',{name:'保存并同步后端',exact:true}).click();
  await page.getByText('已保存到本地内核，主模型与慢镜配置立即生效',{exact:true}).waitFor();
  let actual=await (await page.request.get('http://127.0.0.1:8765/api/desktop/models/config')).json();
  assert(actual.main_model==='Qwen/Qwen3.8-27B' && actual.slow_model==='huihui-ai/Huihui-Qwen3.8-27B-abliterated','Both model selections persisted');
  assert(actual.has_api_key&&!('api_key' in actual),'Key is retained but never returned');
  await page.getByRole('combobox',{name:'当前主模型',exact:true}).selectOption('huihui-qwen3.8-27b');
  await page.getByRole('combobox',{name:'慢镜裁判模型',exact:true}).selectOption('huihui-qwen3.8-27b');
  await page.getByRole('button',{name:'保存并同步后端',exact:true}).click();
  await page.getByText('已保存到本地内核，主模型与慢镜配置立即生效',{exact:true}).waitFor();
  await page.getByRole('button',{name:'启动双镜铠甲',exact:true}).click();
  await page.getByTestId('armor-frame').waitFor();
  await page.getByRole('button',{name:'执行工作台',exact:true}).click();
  await page.getByRole('combobox',{name:'快捷演练剧本'}).selectOption('PB-02');
  await page.getByRole('button',{name:'演练 ↗',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.run-state')?.textContent==='审计完成',null,{timeout:90000});
  assert(metrics>=4,'Independent mirror metrics refresh after each action');
  assert((await page.locator('.verdict-card.block').count())===2,'PB02 still blocks two fragments');
  await page.getByRole('button',{name:'展开安全详情'}).click();
  assert((await page.locator('.security-drawer').innerText()).includes('慢镜耗时'),'Drawer has independent slow latency');
  await page.screenshot({path:'output/playwright/final-workbench.png'});
  for(const approve of [true,false]) {
    await page.getByRole('combobox',{name:'快捷演练剧本'}).selectOption('PB-06');
    await page.getByRole('button',{name:'演练 ↗',exact:true}).click();
    await page.getByRole('button',{name:'批准本次动作',exact:true}).waitFor({timeout:60000});
    const seconds=Number((await page.locator('.countdown strong').innerText()).replace('s',''));
    assert(seconds>=58,'Full approval countdown after remote review');
    await page.getByRole('button',{name:approve?'批准本次动作':'拒绝并阻断',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.run-state')?.textContent==='审计完成',null,{timeout:10000});
    assert((await page.locator('.verdict-card > .row-between .badge').last().innerText()).includes(approve?'ALLOW':'BLOCK'),'Approval loop final verdict');
  }
  assert(errors.length===0,errors.join('\n')); assert(failures.length===0,JSON.stringify(failures));
  return {passed:true,modelSelection:true,secretRedaction:true,perActionMetrics:metrics,remoteApprovalWindow:true,askApprove:true,askReject:true,pageErrors:errors,httpFailures:failures};
}
