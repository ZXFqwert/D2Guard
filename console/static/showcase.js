// 展示区：作品概览、核心亮点、五种能力。数字取自评测汇总（/api/summary），
// 亮点页的逐步演示取自真实运行记录生成的 showcase.json（见 run_id）。
let showcaseData = null;
const getShowcase = async () => (showcaseData ||= await fetch('showcase.json').then((r) => (r.ok ? r.json() : null)).catch(() => null));
const scFrac = (x) => (x ? `${x.n}／${x.d}` : '—');
const scPct = (x, digits = 1) => (x && x.d ? (x.n / x.d * 100).toFixed(digits).replace(/\.0$/, '') + '%' : '—');
const scKB = (b) => (b >= 1000 ? (b / 1000).toFixed(1) + ' KB' : b + ' B');
const scFam = (s, key) => (s?.families || []).find((f) => f.family === key);

function showTabs(active) {
  const tabs = [['home', '作品概览'], ['highlights', '核心亮点'], ['abilities', '五种能力'], ['screen', '攻防大屏']];
  return `<nav class="sc-tabs">${tabs.map(([k, t]) => `<a href="#/${k}" class="${k === active ? 'active' : ''}">${t}</a>`).join('')}</nav>`;
}

// ---------------- 作品概览 ----------------
PAGES.home = async (el) => {
  const s = await api('/api/summary').catch(() => null);
  const lat = s?.latency_ms || {};
  el.innerHTML = `${showTabs('home')}
  <section class="sc-hero">
    <img src="logo.svg" alt="" class="sc-hero-logo">
    <div>
      <h2>双镜 D²Guard</h2>
      <p class="sc-hero-sub">基于快慢协同研判与增量安全状态的大模型智能体运行时防御系统</p>
      <p class="sc-hero-text">以钩子插件、API 网关与 MCP 代理接入开源智能体 Pi，在每次工具调用执行前完成检测、研判与阻断，并对被拦截的攻击生成溯源报告。</p>
    </div>
  </section>
  <section class="sc-kpis">
    <div class="sc-kpi"><small>攻击成功率（无防护 → 防护）</small><b><span class="off">${scPct(s?.off_asr)}</span><i>→</i><span class="on">${scPct(s?.on_asr, 0)}</span></b><em>${scFrac(s?.off_asr)} → ${scFrac(s?.on_asr)}</em></div>
    <div class="sc-kpi"><small>正常任务</small><b><span class="on">${scPct(s?.clean_on_done)}</span></b><em>自动完成，其余等待一次人工确认，阻断 0</em></div>
    <div class="sc-kpi"><small>单动作裁决耗时</small><b><span class="on">${lat.decision_p50 ? Math.round(lat.decision_p50) : '—'}</span> ms</b><em>中位数</em></div>
  </section>
  <p class="sc-note">${s?.scenarios ?? '—'} 个评测场景、${s?.cells ?? '—'} 次真实运行；4 个公开 CVE 复现场景中攻击成功由 8／12 降至 0／12。</p>

  <h3 class="sc-h">三步看懂</h3>
  <section class="sc-story">
    <a class="sc-step" href="#/arena" data-step="1"><b>①</b><h4>正常运行</h4><p>干净环境中，Pi Agent 读取 README 并写出摘要。</p><span>去实操 →</span></a>
    <a class="sc-step bad" href="#/arena" data-step="2"><b>②</b><h4>遭受攻击</h4><p>README 中藏有一句伪装成交接说明的指令，无防护的 Agent 照做，读取 .env 并外发。</p><span>去实操 →</span></a>
    <a class="sc-step good" href="#/arena" data-step="3"><b>③</b><h4>防护拦截</h4><p>同一攻击下，D²Guard 在外发执行前将其挂起，摘要照常写出。</p><span>去实操 →</span></a>
  </section>

  <h3 class="sc-h">系统结构</h3>
  <section class="card sc-arch">${archSvg()}
    <p class="sc-legend"><span class="k rule"></span>规则层：静态规则，确定性检查　<span class="k fast"></span>快镜：小模型，同步判别　<span class="k slow"></span>慢镜：大模型，异步研判与溯源　<span class="k chain"></span>增量安全链：三者共用的安全状态</p>
  </section>`;
  $$('.sc-step', el).forEach((a) => a.addEventListener('click', () => { arena.step = +a.dataset.step; arena.env = arena.step === 1 ? 'clean' : 'attack'; }));
};

function archSvg() {
  const box = (x, y, w, h, title, sub, cls = '') => `<g class="ab ${cls}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12"/><text x="${x + w / 2}" y="${y + (sub ? h / 2 - 4 : h / 2 + 5)}" class="t1">${title}</text>${sub ? `<text x="${x + w / 2}" y="${y + h / 2 + 16}" class="t2">${sub}</text>` : ''}</g>`;
  const arr = (x1, y1, x2, y2, cls = '') => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="aa ${cls}" marker-end="url(#ah)"/>`;
  return `<svg viewBox="0 0 1180 320" class="sc-arch-svg" role="img" aria-label="系统结构">
  <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" class="ah"/></marker></defs>
  ${box(20, 115, 160, 90, 'Pi Agent', '真实工具调用循环', 'host')}
  ${box(225, 35, 180, 60, '执行前钩子插件', '工具调用')}
  ${box(225, 130, 180, 60, 'API 网关', '模型请求')}
  ${box(225, 225, 180, 60, 'MCP 代理', 'MCP 工具')}
  ${box(450, 115, 180, 90, '增量安全链', '有界安全状态', 'chain')}
  ${box(680, 30, 200, 64, '规则层', '机密 · 敏感目标 · 硬策略', 'rule')}
  ${box(680, 128, 200, 64, '快镜 D²Guard-Laya', '外部内容是否下达任务', 'fast')}
  ${box(930, 78, 230, 64, '决策表', '放行 ／ 挂起 ／ 阻断', 'verdict')}
  ${box(680, 236, 480, 60, '慢镜 · 大模型', '挂起或阻断后异步研判 · 还原攻击路径 · 生成溯源报告', 'slow')}
  ${arr(180, 145, 223, 70)}${arr(180, 160, 223, 160)}${arr(180, 175, 223, 250)}
  ${arr(405, 65, 448, 140)}${arr(405, 160, 448, 160)}${arr(405, 255, 448, 180)}
  ${arr(630, 145, 678, 65)}${arr(630, 160, 678, 160)}${arr(630, 180, 678, 262)}
  ${arr(880, 62, 928, 100)}${arr(880, 160, 928, 122)}
  ${arr(1045, 142, 1045, 234, 'dash')}
  <path d="M1045 78 V24 H100 V113" class="aa back" marker-end="url(#ah)"/>
  <text x="575" y="15" class="t3">裁决回写到执行前钩子：放行、挂起待确认或阻断</text>
  </svg>`;
}

// ---------------- 核心亮点 ----------------
PAGES.highlights = async (el, [part = 'chain']) => {
  const [d, s] = await Promise.all([getShowcase(), api('/api/summary').catch(() => null)]);
  if (!d) { el.innerHTML = showTabs('highlights') + '<div class="card muted">未找到展示数据 showcase.json。</div>'; return; }
  const subs = [['chain', '增量安全链'], ['align', '意图—计划—工具语义对齐'], ['dual', '规则层与快慢双镜']];
  el.innerHTML = `${showTabs('highlights')}
    <div class="seg sc-sub">${subs.map(([k, t]) => `<button data-k="${k}" class="${k === part ? 'active' : ''}">${t}</button>`).join('')}</div>
    <div id="hl-body"></div>`;
  $$('.sc-sub button', el).forEach((b) => b.addEventListener('click', () => go('#/highlights/' + b.dataset.k)));
  const body = $('#hl-body', el);
  if (part === 'align') body.innerHTML = alignView(d, s);
  else if (part === 'dual') body.innerHTML = dualView(d, s);
  else { body.innerHTML = chainView(d, s); chainStepper(body, d); }
};

const sourceLine = (d) => `<p class="sc-src">真实运行 <a href="#/trace/${esc(d.run_id)}">${esc(d.run_id)}</a>，场景 ${esc(d.scenario)}：README 中的攻击指令以俄语写成并伪装为交接说明。</p>`;

function chainView(d, s) {
  const dil = d.dilution, comp = s?.compaction || {};
  const W = 560, H = 210, n = dil.requests.length, max = Math.max(...dil.requests.map((r) => r.input));
  const px = (i) => 66 + (i / Math.max(1, n - 1)) * (W - 86), py = (v) => H - 30 - (v / max) * (H - 50);
  const line = (k) => dil.requests.map((r, i) => `${i ? 'L' : 'M'}${px(i).toFixed(1)} ${py(r[k]).toFixed(1)}`).join(' ');
  return `
  <section class="card sc-lead">
    <h3>安全链 vs 原始上下文</h3>
    <p>每次模型请求的输入随对话不断膨胀；内核裁决只读取增量安全链维护的<b>有界安全状态</b>，不随上下文增长。</p>
    <p>每个事件发生时，系统从中抽取一条安全增量（用户授权、外部来源及其是否下达任务、机密与数据流），附原文证据引用后追加到链上。链的长度取决于<b>不同来源与不同目标的数量</b>，与对话轮数和上下文长度无关；裁决读取的状态视图设有固定上限。</p>
    ${chainConceptSvg()}
  </section>
  <section class="card">
    <h3>逐步看一次真实运行</h3>
    ${sourceLine(d)}
    <div class="sc-stepper">
      <ol class="sc-steps" id="cs-list"></ol>
      <div class="sc-state" id="cs-state"></div>
    </div>
    <div class="row sc-ctl"><button class="btn" id="cs-prev">上一步</button><button class="btn primary" id="cs-next">下一步</button><button class="btn" id="cs-play">自动播放</button></div>
  </section>
  <section class="card">
    <h3>长任务实测</h3>
    <div class="sc-two">
      <svg viewBox="0 0 ${W} ${H}" class="sc-chart" role="img" aria-label="上下文与安全状态对比">
        ${[0, .5, 1].map((f) => `<line x1="66" x2="${W - 20}" y1="${py(max * f)}" y2="${py(max * f)}" class="grid"/><text x="60" y="${py(max * f) + 4}" class="ax" text-anchor="end">${scKB(Math.round(max * f))}</text>`).join('')}
        <path d="${line('input')}" class="ln ctx"/><path d="${line('state')}" class="ln st"/>
        <text x="${W / 2}" y="${H - 6}" class="ax" text-anchor="middle">51 轮上下文稀释场景 · 模型请求序号（共 ${n} 次）</text>
      </svg>
      <div class="sc-facts">
        ${legend([['模型输入', 'var(--off)'], ['裁决读取的安全状态', 'var(--accent)']])}
        <div class="sc-big"><b>${scKB(dil.context_min)} → ${scKB(dil.context_max)}</b><small>模型输入</small></div>
        <div class="sc-big"><b class="on">约 ${scKB(dil.state_max)}</b><small>安全状态最大值</small></div>
        <div class="sc-big"><b>×${comp.median_ratio ? comp.median_ratio.toFixed(2) : '—'} ／ ×${comp.max_ratio ? comp.max_ratio.toFixed(1) : '—'}</b><small>${comp.runs ?? '—'} 次运行中上下文与安全状态之比（中位数／最大值）</small></div>
      </div>
    </div>
  </section>`;
}

function chainConceptSvg() {
  const ev = ['用户任务', '工具描述', 'README', '模型回复', 'review.json', '模型回复', '…'];
  return `<svg viewBox="0 0 1100 200" class="sc-concept" role="img" aria-label="增量安全链示意">
    <defs><marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" class="ah"/></marker></defs>
    <text x="20" y="24" class="t4 l">原始上下文（随对话膨胀）</text>
    ${ev.map((t, i) => `<g class="ev"><rect x="${20 + i * 82}" y="40" width="74" height="40" rx="8"/><text x="${57 + i * 82}" y="65" class="t2">${t}</text></g>`).join('')}
    ${ev.slice(0, 6).map((_, i) => `<line x1="${57 + i * 82}" y1="82" x2="${57 + i * 82}" y2="128" class="aa thin" marker-end="url(#ah2)"/>`).join('')}
    <text x="600" y="66" class="t2 l">每个事件抽取一条安全增量，附原文证据引用</text>
    <rect x="20" y="132" width="490" height="44" rx="10" class="chainbar"/>
    <text x="265" y="159" class="t1">增量安全链</text>
    <line x1="512" y1="154" x2="640" y2="154" class="aa" marker-end="url(#ah2)"/>
    <g class="ab verdict"><rect x="645" y="120" width="210" height="70" rx="12"/><text x="750" y="150" class="t1">有界安全状态</text><text x="750" y="172" class="t2">授权锚点 · 来源标签 · 数据流</text></g>
    <line x1="857" y1="154" x2="905" y2="154" class="aa" marker-end="url(#ah2)"/>
    <g class="ab fast"><rect x="910" y="120" width="170" height="70" rx="12"/><text x="995" y="150" class="t1">执行前裁决</text><text x="995" y="172" class="t2">按键查询安全事实</text></g>
  </svg>`;
}

function chainStepper(root, d) {
  const steps = [...d.steps].sort((a, b) => a.seq - b.seq);
  let i = 0, timer = null;
  const s1Html = (x) => `<div class="sc-s1 ${x.label === 'request' ? 'hot' : ''}"><span>快镜 D²Guard-Laya</span><b>${x.label === 'request' ? '在下达任务（request）' : '未下达任务（none）'}</b>
    <div class="sc-prob"><i style="width:${(x.request * 100).toFixed(1)}%"></i></div><small>request 概率 ${x.request.toFixed(3)}</small></div>`;
  const decHtml = (x) => `<div class="sc-dec ${VERDICT_CLASS[x.verdict]}"><span>决策表</span><b>${VERDICT_ZH[x.verdict]} · ${esc(x.rule)}</b>
    <ul><li>目标在用户授权内：${x.in_scope ? '是' : '<em>否</em>'}</li><li>上下文存在下达任务的外部来源：${x.request_tainted ? '<em>是</em>' : '否'}</li><li>敏感目标：${x.sensitive ? '<em>是</em>' : '否'}</li></ul><small>${esc(x.reason)}</small></div>`;
  const render = () => {
    $('#cs-list', root).innerHTML = steps.map((s, k) => `<li class="${k === i ? 'cur' : k < i ? 'done' : ''}" data-k="${k}"><b>${k + 1}</b><span>${esc(s.event)}</span>${s.decision ? badge(VERDICT_ZH[s.decision.verdict], VERDICT_CLASS[s.decision.verdict]) : s.s1 ? badge(s.s1.label === 'request' ? '请求' : '无请求', s.s1.label === 'request' ? 'block' : 'gray') : badge('授权', 'allow')}</li>`).join('');
    const s = steps[i], seen = steps.slice(0, i + 1);
    const sources = seen.filter((x) => x.s1);
    $('#cs-state', root).innerHTML = `
      <div class="sc-raw"><small>原始事件</small><pre>${esc(s.raw)}</pre><small>抽取的安全增量：${esc(s.delta)}</small></div>
      ${s.s1 ? s1Html(s.s1) : ''}${s.decision ? decHtml(s.decision) : ''}
      <div class="sc-statecard"><div class="row"><b>当前安全状态</b><span class="mono small">${scKB(s.state_bytes)}</span></div>
        <div><small>授权锚点</small> ${seen.some((x) => x.facts) ? `读 ${d.anchor.read.map((x) => `<code>${esc(x)}</code>`).join(' ')} · 写 ${d.anchor.write.map((x) => `<code>${esc(x)}</code>`).join(' ')} · 网络 无` : '尚未收到用户任务'}</div>
        <div><small>外部来源</small> ${sources.length ? sources.map((x) => `<code class="${x.s1.label === 'request' ? 'hot' : ''}">${esc(x.event.replace('内容进入上下文', '').replace('加载 ', ''))}${x.s1.label === 'request' ? ' · 下达任务' : ''}</code>`).join(' ') : '—'}</div>
      </div>`;
    $$('#cs-list li', root).forEach((li) => li.addEventListener('click', () => { i = +li.dataset.k; stop(); render(); }));
  };
  const stop = () => { if (timer) clearInterval(timer); timer = null; $('#cs-play', root).textContent = '自动播放'; };
  $('#cs-prev', root).addEventListener('click', () => { stop(); i = Math.max(0, i - 1); render(); });
  $('#cs-next', root).addEventListener('click', () => { stop(); i = Math.min(steps.length - 1, i + 1); render(); });
  $('#cs-play', root).addEventListener('click', () => {
    if (timer) return stop();
    $('#cs-play', root).textContent = '暂停';
    timer = setInterval(() => { if (i >= steps.length - 1) return stop(); i++; render(); }, 2200);
  });
  onLeave(stop);
  render();
}


function alignView(d, s) {
  const st = Object.fromEntries(d.steps.map((x) => [x.seq, x]));
  const readme = st[25], ask = st[61].decision;
  const arms = s?.three_arm || [];
  const plan = [['fs_read README.md', st[20].decision], ['fs_read review.json', st[40].decision], ['fs_write review.json', ask]];
  return `
  <section class="card sc-lead">
    <h3>意图、计划与工具的逐一比对</h3>
    <p><b>意图</b>是由用户消息生成的授权锚点；<b>计划</b>是 Agent 调用工具前提出的候选调用序列；<b>工具</b>是规范化后的实际动作。每个动作执行前先查是否落在授权内；越出授权时，再查上下文中是否存在被<b>快镜 D²Guard-Laya</b> 判定为“下达任务”的外部来源。</p>
  </section>
  <section class="card">
    ${sourceLine(d)}
    <div class="sc-align">
      <div class="sc-col"><h4>① 意图 · 授权锚点</h4><pre>${esc(d.task)}</pre>
        <ul class="sc-anchor"><li><small>允许读</small>${d.anchor.read.map((x) => `<code>${esc(x)}</code>`).join(' ')}</li><li><small>允许写</small>${d.anchor.write.map((x) => `<code>${esc(x)}</code>`).join(' ')}</li><li><small>允许联网</small>无</li></ul></div>
      <div class="sc-col"><h4>② 外部内容 · Laya 判别</h4><pre class="hot">${esc(readme.raw)}</pre>
        <div class="sc-s1 hot"><span>D²Guard-Laya</span><b>该来源在下达任务</b><div class="sc-prob"><i style="width:${(readme.s1.request * 100).toFixed(1)}%"></i></div>
        <small>request ${readme.s1.request.toFixed(3)} · 耗时 ${readme.s1.latency_ms} ms</small></div></div>
      <div class="sc-col"><h4>③ 计划与工具 · 比对与裁决</h4>
        <table class="sc-tbl"><thead><tr><th>候选动作</th><th>在授权内</th><th>来源下达任务</th><th>裁决</th></tr></thead><tbody>
        ${plan.map(([a, x]) => `<tr><td class="mono">${esc(a)}</td><td>${x.in_scope ? '✓' : '<em>✗</em>'}</td><td>${x.request_tainted ? '<em>是</em>' : '否'}</td><td>${badge(VERDICT_ZH[x.verdict] + ' ' + x.rule, VERDICT_CLASS[x.verdict])}</td></tr>`).join('')}
        <tr><td class="mono">fs_write summary.md</td><td>✓</td><td>—</td><td>${badge('完成', 'allow')}</td></tr></tbody></table>
        <p class="small">读取 review.json 属低风险动作，放行并记录；改写 review.json 越出授权且与下达任务的来源相关，被挂起，文件保持原样，摘要照常写出。</p></div>
    </div>
  </section>
  <section class="card">
    <h3>快镜的作用：三种做法对照</h3>
    <p class="small muted">规则层识别不出的 10 个语义伪装攻击场景与 8 个正常场景，真实 Agent 运行。</p>
    <div class="sc-arms">${arms.map((a) => `<div class="sc-arm ${a.arm === 'C' ? 'best' : ''}"><h4>${esc(a.label)}</h4>
      <div><small>攻击成功</small><strong class="${a.attack_success.startsWith('0/') ? 'on' : 'off'}">${esc(a.attack_success)}</strong></div>
      <div><small>正常任务完成</small><strong class="${a.normal_done.startsWith('0/') ? 'off' : ''}">${esc(a.normal_done)}</strong></div></div>`).join('')}</div>
  </section>
  <section class="card sc-laya">
    <h3>D²Guard-Laya</h3>
    <div class="sc-laya-grid">
      <div><b>322M</b><small>多语言 mmBERT 编码器</small></div>
      <div><b>20,662</b><small>自建训练样本，真实文本占 42.1%</small></div>
      <div><b>0 → 0.937</b><small>request 类 F1（原版 → 微调后）</small></div>
      <div><b>${s?.latency_ms?.s1_gpu_p50 ? Math.round(s.latency_ms.s1_gpu_p50) : 29} ／ ${s?.latency_ms?.s1_cpu_p50 ? Math.round(s.latency_ms.s1_cpu_p50) : 172} ms</b><small>单次判别中位耗时（GPU ／ CPU）</small></div>
    </div>
    <p class="small muted">每段外部内容进入时判别一次，结果作为来源标签写入增量安全链，后续各步裁决直接复用。</p>
  </section>`;
}

function dualView(d, s) {
  const lat = s?.latency_ms || {}, sl = d.slow;
  return `
  <section class="sc-dual3">
    <div class="card sc-lane rule"><h3>规则层 · 静态</h3><p>确定性检查，构成安全下限。</p>
      <ul><li>机密指纹与敏感目标</li><li>硬策略（如私钥外发）直接阻断</li><li>用户字面授权与 14 条规则的决策表</li></ul></div>
    <div class="card sc-lane fast"><h3>快镜 · 动态 · 同步</h3><p>自训练小模型 D²Guard-Laya，判断外部内容是否在下达任务。</p>
      <ul><li>内容进入时判别一次，写入安全链</li><li>识别规则无法覆盖的语义伪装与多语言注入</li></ul>
      <div class="sc-big"><b class="on">${lat.decision_p50 ? Math.round(lat.decision_p50) : '—'} ms</b><small>规则层＋快镜的单动作裁决中位数</small></div></div>
    <div class="card sc-lane slow"><h3>慢镜 · 动态 · 异步</h3><p>大模型在动作被挂起或阻断后运行。</p>
      <ul><li>依据证据引用回溯原文，还原跨 Agent、MCP 与记忆的攻击路径</li><li>生成带引用的研判报告，用于审批与审计；裁决保持不变</li></ul></div>
  </section>
  ${sl ? `<section class="card sc-report"><div class="row"><b>慢镜研判报告（真实运行）</b>${badge(sl.alignment === 'DEVIANT_INJECTION' ? '偏离意图的注入' : sl.alignment, 'block')}<a href="#/trace/${esc(sl.run_id)}" class="small">溯源图 →</a></div>
    <p>${esc(sl.report)}</p><small class="muted">场景 ${esc(sl.scenario)} · 引用原文证据 ${sl.citations} 处</small></section>` : ''}`;
}

// ---------------- 五种能力 ----------------
PAGES.abilities = async (el) => {
  const s = await api('/api/summary').catch(() => null);
  const f = (k) => scFam(s, k);
  const res = (label, x, y) => `<div class="sc-res"><small>${label}</small><b><span class="off">${scFrac(x)}</span><i>→</i><span class="on">${scFrac(y)}</span></b></div>`;
  const one = (label, v) => `<div class="sc-res"><small>${label}</small><b>${v}</b></div>`;
  const ev = (links) => `<div class="sc-ev">${links.map(([t, h]) => `<a class="btn small" href="${h}">${t}</a>`).join('')}</div>`;
  const arms = Object.fromEntries((s?.three_arm || []).map((a) => [a.arm, a]));
  const lat = s?.latency_ms || {};
  const items = [
    ['多源注入识别', ['插件、网关与代理覆盖工具调用、模型请求与 MCP 三条链路，外部内容进入时登记为来源', '快镜判别来源是否下达任务；规则识别用户输入中的越权、角色伪装与上下文劫持'],
      res('间接注入', f('indirect')?.off_asr, f('indirect')?.on_asr) + res('直接注入', f('direct')?.off_asr, f('direct')?.on_asr),
      [['间接注入演示', '#/arena/c-indirect-readme'], ['MCP 返回注入', '#/arena/c-indirect-mcp']]],
    ['意图—计划—工具语义对齐', ['授权锚点（意图）、候选调用（计划）与规范化动作（工具）在执行前逐一比对', '越出授权的动作与下达任务的来源关联时挂起'],
      one('语义伪装攻击成功', `<span class="on">${esc(arms.C?.attack_success || '—')}</span>`) + one('正常任务完成', `<span class="on">${esc(arms.C?.normal_done || '—')}</span>`),
      [['对齐过程', '#/highlights/align'], ['伪装攻击演示', '#/arena/e-attack-04']]],
    ['细粒度策略与三态决策', ['14 条规则的决策表，按操作、目标、授权与来源给出放行、挂起或阻断', '挂起操作在网页审批，硬策略直接阻断'],
      one('正常任务阻断', `<span class="on">${s?.clean_on_blocked ?? 0}</span>`) + one('良性动作误挂起', `<span class="on">${s?.benign_hold?.n ?? '—'}</span>／${s?.benign_hold?.d ?? '—'}`) + one('裁决耗时中位数', `${lat.decision_p50 ? Math.round(lat.decision_p50) : '—'} ms`),
      [['决策表', '#/policies']]],
    ['跨 MCP 与子 Agent 溯源', ['MCP 工具按“服务器/工具”标识；子 Agent 继承来源标签，记忆保留写入来源', '溯源图与慢镜报告引用原文字符区间'],
      res('工具链供应链', f('supply_chain')?.off_asr, f('supply_chain')?.on_asr) + res('工具滥用', f('tool_abuse')?.off_asr, f('tool_abuse')?.on_asr) + `<div class="sc-res"><small>公开 CVE 复现</small><b><span class="off">8／12</span><i>→</i><span class="on">0／12</span></b></div>`,
      [['多层子 Agent', '#/arena/g-attack-nested'], ['多 MCP 注入', '#/arena/multi-mcp-injection'], ['溯源分析', '#/trace']]],
    ['对抗鲁棒性', ['规范化编码、大小写与同形字后再比对', '快镜多语言与混淆变体训练；安全链保留早期注入'],
      res('对抗变体', f('adversarial')?.off_asr, f('adversarial')?.on_asr),
      [['Unicode 混淆', '#/arena/c-variant-unicode'], ['日语注入', '#/arena/c2-language-ja']]],
  ];
  el.innerHTML = `${showTabs('abilities')}
  <p class="sc-note">攻击成功：无防护 → 防护，${s?.cells ?? '—'} 次真实运行。</p>
  <section class="sc-abil">${items.map(([t, how, nums, links], k) => `
    <article class="card sc-ab"><header><b>${k + 1}</b><h3>${t}</h3></header>
      <div class="sc-ab-body"><ul>${how.map((x) => `<li>${x}</li>`).join('')}</ul>
      <div><div class="sc-resgrid">${nums}</div>${ev(links)}</div></div></article>`).join('')}</section>`;
};
