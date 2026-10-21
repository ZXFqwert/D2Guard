'use strict';
// 溯源分析：攻击路径 DAG、时序链路、裁决明细、来源原文、研判报告。

const tstate = { trace: null, tab: 'graph', selCall: null };

async function renderTracePage(el, id) {
  const t = tstate.trace = await api('/api/runs/' + encodeURIComponent(id));
  if (tstate.lastId !== id) { tstate.selCall = null; tstate.lastId = id; }
  el.innerHTML = `
    <section class="card run-head" id="run-head"></section>
    <section class="pairs" id="pairs"></section>
    ${(t.memory_links || []).length ? `<section class="card"><h3>跨会话记忆来源</h3>${t.memory_links.map(m => `<p><b>${esc(m.key)}</b> · ${m.native_write_verified ? '已核对原生写入调用及内容哈希' : '写入证据未核实'}<br>
      写入会话：${m.writer_run_id ? `<a class="link" href="#/trace/${esc(m.writer_run_id)}">${esc(m.writer_run_id)} → 查看写入过程</a>` : esc(m.writer_session)}<br>
      <small class="mono">内容 SHA-256：${esc(m.content_sha256)}</small></p>`).join('')}</section>` : ''}
    <nav class="tabs" id="tabs">
      <button data-tab="graph">攻击路径 DAG</button>
      <button data-tab="timeline">时序链路</button>
      <button data-tab="calls">裁决明细</button>
      <button data-tab="sources">来源原文</button>
      <button data-tab="report">研判报告</button>
    </nav>
    <section class="card tab-body" id="tab-graph"></section>
    <section class="card tab-body hidden" id="tab-timeline"></section>
    <section class="card tab-body hidden" id="tab-calls"></section>
    <section class="card tab-body hidden" id="tab-sources"></section>
    <section class="card tab-body hidden" id="tab-report"></section>`;
  renderHead(t);
  renderPairs(t.run);
  $$('#tabs button').forEach((b) => b.addEventListener('click', () => { tstate.tab = b.dataset.tab; renderTab(); }));
  renderTab();
  if (!t.run.complete) later(() => { if (location.hash === '#/trace/' + id) renderTracePage(el, id); }, 1500);
}

function renderHead(t) {
  const r = t.run;
  const [label, cls] = outcomeLabel(r);
  const asked = t.calls.filter((c) => c.verdict === 'ASK' && !c.executed).length;
  const blocked = t.calls.filter((c) => c.verdict === 'BLOCK').length;
  const would = t.calls.filter((c) => c.would_verdict && c.would_verdict !== c.verdict).length;
  $('#run-head').innerHTML = `
    <div class="rh-main">
      <h2>${esc(r.scenario)}</h2>
      <div class="meta">${badge(ENV_ZH[r.environment] || r.environment, r.environment)} ${badge(PROTECT_ZH[r.protection] || r.protection, r.protection)}
        ${badge('决策 ' + (r.decision_mode || 'unknown'), 'gray')} ${badge('模型 ' + (r.model || '未知'), 'gray')} ${badge('Pi ' + (r.pi_version || ''), 'gray')} <span class="muted">${esc(r.id)}</span></div>
      <div class="task"><b>用户任务：</b>${esc(r.task)}</div>
    </div>
    <div class="verdict-box">
      <span class="big badge ${cls}">${esc(label)}</span>
      <div class="kpis">
        <div><b>${t.calls.length}</b>工具调用</div>
        <div><b class="c-ask">${asked}</b>挂起</div>
        <div><b class="c-block">${blocked}</b>阻断</div>
        ${r.protection === 'off' ? `<div><b class="c-block">${would}</b>防护本应介入</div>` : ''}
        <div><b>${r.received_bytes ?? 0}</b>接收端字节</div>
        <div><b>${r.elapsed_seconds != null ? r.elapsed_seconds.toFixed(1) + 's' : '—'}</b>耗时</div>
      </div>
    </div>`;
}

async function renderPairs(run) {
  const box = $('#pairs');
  try {
    const data = await api('/api/pairs/' + encodeURIComponent(run.scenario));
    const cells = [['clean', 'off'], ['clean', 'on'], ['attack', 'off'], ['attack', 'on']].map(([env, p]) => {
      const r = data.cells[`${env}/${p}`];
      if (!r) return `<div class="pair none">${ENV_ZH[env]} · ${PROTECT_ZH[p]}<br><span class="muted">暂无运行</span></div>`;
      const [label, cls] = outcomeLabel(r);
      return `<a class="pair ${r.id === run.id ? 'current' : ''}" href="#/trace/${esc(r.id)}">${ENV_ZH[env]} · ${PROTECT_ZH[p]}<br>${badge(label, cls)}</a>`;
    }).join('');
    box.innerHTML = `<span class="muted">同场景四格对照：</span>${cells}`;
  } catch { box.innerHTML = ''; }
}

function renderTab() {
  $$('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === tstate.tab));
  for (const name of ['graph', 'timeline', 'calls', 'sources', 'report']) $('#tab-' + name).classList.toggle('hidden', name !== tstate.tab);
  ({ graph: renderGraph, timeline: renderTimeline, calls: renderCalls, sources: renderSources, report: renderReport })[tstate.tab](tstate.trace);
}

// ---------------- attack path DAG ----------------
const COLS = [{ x: 20, title: '① 触发源' }, { x: 310, title: '② Agent' }, { x: 600, title: '③ 工具调用（裁决）' }, { x: 890, title: '④ 裁决 / MCP / 目标' }, { x: 1180, title: '⑤ 执行结果' }];
const NW = 250, NH = 52, GAP = 14, TOP = 44;

function layoutGraph(g) {
  const pos = {};
  const byLayer = COLS.map(() => []);
  g.nodes.forEach((n) => byLayer[n.layer].push(n));
  const place = (list, col, want) => {
    let y = TOP;
    const sorted = want ? [...list].sort((a, b) => (want(a) ?? 1e9) - (want(b) ?? 1e9)) : list;
    for (const n of sorted) {
      const w = want ? want(n) : null;
      y = Math.max(y, w ?? y);
      pos[n.id] = { x: COLS[col].x, y };
      y += NH + GAP;
    }
  };
  place(byLayer[0], 0);
  place(byLayer[2], 2);
  const callYs = (agentId) => g.edges.filter((e) => e.from === agentId && e.kind === 'propose').map((e) => pos[e.to]?.y).filter((v) => v != null);
  place(byLayer[1], 1, (n) => { const ys = callYs(n.id); return ys.length ? Math.min(...ys) : null; });
  place(byLayer[3], 3, (n) => { const e = g.edges.find((x) => x.to === n.id); return e ? pos[e.from]?.y : null; });
  place(byLayer[4], 4, (n) => { const e = g.edges.find((x) => x.to === n.id); return e ? pos[e.from]?.y : null; });
  const h = Math.max(...Object.values(pos).map((p) => p.y), TOP) + NH + 20;
  return { pos, h };
}

function nodeStyle(n) {
  const V = { ALLOW: ['var(--allow-bg)', 'var(--allow)'], ASK: ['var(--ask-bg)', 'var(--ask)'], BLOCK: ['var(--block-bg)', 'var(--block)'] };
  switch (n.kind) {
    case 'user': return { fill: 'var(--user-bg)', stroke: 'var(--user)' };
    case 'agent': return { fill: 'var(--agent-bg)', stroke: 'var(--agent)' };
    case 'source': return n.hot || n.s1 === 'request' ? { fill: 'var(--hot-bg)', stroke: 'var(--induce)' } : { fill: 'var(--source-bg)', stroke: 'var(--source)' };
    case 'target': return n.executed ? { fill: 'var(--target-bg)', stroke: 'var(--target)' } : { fill: 'transparent', stroke: 'var(--node-line)', dash: '4 3' };
    case 'call': {
      const v = n.verdict, w = effectiveVerdict(n);
      const [bg, color] = V[w] || ['var(--node-bg)', 'var(--node-line)'];
      return w !== v ? { fill: 'transparent', stroke: color, dash: '5 3' } : { fill: bg, stroke: color };
    }
    case 'decision': { const [, color] = V[(n.label || '').split(' ')[0]] || [, 'var(--node-line)']; return { fill: 'var(--panel-2)', stroke: color }; }
    case 'mcp_server': case 'mcp_tool': case 'mcp': return { fill: 'var(--source-bg)', stroke: 'var(--mcp)' };
    case 'execution_result': return { fill: 'var(--sunken)', stroke: n.is_error ? 'var(--block-line)' : 'var(--node-line)' };
    default: return { fill: 'var(--node-bg)', stroke: 'var(--node-line)' };
  }
}

// The path that leads to each held action: who proposed it (through the agent / sub-agent chain and the
// model request), flagged sources it is associated with, and the verdict it received. Association only.
function attackPath(g) {
  const held = g.nodes.filter((n) => n.kind === 'call' && ['ASK', 'BLOCK'].includes(effectiveVerdict(n)));
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const flagged = (n) => n && n.kind === 'source' && (n.hot || n.s1 === 'request');
  const nodes = new Set(), edges = new Set();
  const up = ['propose', 'proposal_after_request', 'request', 'spawn', 'task', 'mcp_observation', 'provides'];
  const todo = held.map((n) => n.id);
  held.forEach((n) => nodes.add(n.id));
  while (todo.length) {
    const id = todo.pop();
    g.edges.forEach((e, i) => {
      if (e.to !== id) return;
      const ok = up.includes(e.kind) || e.kind.startsWith('induce') || (e.kind === 'ingest' && flagged(byId[e.from]));
      if (!ok || (['mcp_observation', 'provides'].includes(e.kind) && !nodes.has(e.to))) return;
      edges.add(i);
      if (!nodes.has(e.from)) { nodes.add(e.from); todo.push(e.from); }
    });
  }
  const down = new Set(held.map((n) => n.id));
  g.edges.forEach((e, i) => { if (down.has(e.from) && ['decision', 'prevented', 'effect', 'mcp_dispatch', 'proposed_mcp'].includes(e.kind)) { edges.add(i); nodes.add(e.to); } });
  g.edges.forEach((e, i) => { if (e.kind === 'execution' && nodes.has(e.from) && byId[e.from]?.kind === 'decision') { edges.add(i); nodes.add(e.to); } });
  const verdicts = held.map((n) => n.verdict);
  return { held: new Set(held.map((n) => n.id)), nodes, edges, executed: held.some((n) => n.executed), block: verdicts.includes('BLOCK') };
}

function renderGraph(t) {
  const g = JSON.parse(JSON.stringify(t.graph));
  const hot = new Set(g.edges.filter((e) => e.kind.startsWith('induce')).map((e) => e.from));
  const executedTargets = new Set(g.edges.filter((e) => e.kind === 'effect').map((e) => e.to));
  g.nodes.forEach((n) => { n.hot = hot.has(n.id); if (n.kind === 'target') n.executed = executedTargets.has(n.id); });
  const ap = attackPath(g);
  const showAp = tstate.ap !== false && ap.held.size > 0;
  const { pos, h } = layoutGraph(g);
  const W = COLS.at(-1).x + NW + 20;
  const edgePath = (e) => {
    const a = pos[e.from], b = pos[e.to];
    if (!a || !b) return '';
    const la = g.nodes.find((n) => n.id === e.from).layer, lb = g.nodes.find((n) => n.id === e.to).layer;
    if (la === lb) { // agent -> child agent: loop on the left
      const x = a.x, y1 = a.y + NH / 2, y2 = b.y + NH / 2;
      return `M${x},${y1} C${x - 40},${y1} ${x - 40},${y2} ${x},${y2}`;
    }
    if (la > lb) { // spawn call -> child agent
      const x1 = a.x, y1 = a.y + NH / 2, x2 = b.x + NW, y2 = b.y + NH / 2;
      return `M${x1},${y1} C${x1 - 50},${y1 + 30} ${x2 + 50},${y2 + 30} ${x2},${y2}`;
    }
    const x1 = a.x + NW, y1 = a.y + NH / 2, x2 = b.x, y2 = b.y + NH / 2, mx = (x1 + x2) / 2;
    return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
  };
  const marker = (id, color) => `<marker id="${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${color}"/></marker>`;
  const markerFor = (k) => (k.startsWith('induce') ? 'm-red' : k === 'spawn' ? 'm-purple' : k === 'effect' ? 'm-dark' : 'm-gray');
  const onAp = (i) => showAp && ap.edges.has(i);
  // Attack-path edges are drawn last so they sit above the ordinary flow.
  const order = g.edges.map((e, i) => i).sort((a, b) => onAp(a) - onAp(b));
  const edges = order.map((i) => { const e = g.edges[i]; return `<path class="edge ${e.kind}${onAp(i) ? ' attack-path' : ''}" data-i="${i}" data-from="${esc(e.from)}" data-to="${esc(e.to)}" d="${edgePath(e)}" marker-end="url(#${onAp(i) ? 'm-ap' : markerFor(e.kind)})"/>`; }).join('');
  const nodes = g.nodes.map((n) => {
    const p = pos[n.id]; if (!p) return '';
    const st = nodeStyle(n);
    let sub = '';
    if (n.kind === 'call') {
      const w = effectiveVerdict(n);
      const approvalText = { approved_once: '人工批准本次', rejected: '人工拒绝', expired: '审批过期' }[n.approval_status];
      const v = approvalText || (w !== n.verdict ? `应${VERDICT_ZH[w]}（防护关闭）` : (VERDICT_ZH[n.verdict] || '待裁决'));
      sub = `${n.rule_id || ''} · ${v} · ${n.executed ? '已执行' : '未执行'}`;
    } else if (n.kind === 'source') sub = n.hot ? '关联证据（未证实因果）' + (n.s1 ? ` · S1:${n.s1}` : '') : (n.s1 ? `S1:${n.s1}` : '外部来源（不可信）');
    else if (n.kind === 'target') sub = n.executed ? '已受影响' : '未发生（已拦截或未执行）';
    else if (n.kind === 'user') sub = '可信授权来源';
    else if (n.kind === 'agent') sub = n.id === 'agent:main' ? '宿主 Pi Agent' : '派发的子 Agent';
    else if (n.kind === 'model_request') sub = n.sub || '';
    const label = n.label.length > 28 ? n.label.slice(0, 27) + '…' : n.label;
    if (sub.length > 30) sub = sub.slice(0, 29) + '…';
    const cls = `${showAp && ap.nodes.has(n.id) ? ' on-path' : ''}${showAp && ap.held.has(n.id) ? ' held-node' : ''}`;
    return `<g class="node${cls}" data-id="${esc(n.id)}" transform="translate(${p.x},${p.y})">
      <rect width="${NW}" height="${NH}" fill="${st.fill}" stroke="${st.stroke}" ${st.dash ? `stroke-dasharray="${st.dash}"` : ''}/>
      <text x="12" y="22">${esc(label)}</text><text class="sub" x="12" y="41">${esc(sub)}</text></g>`;
  }).join('');
  const heads = COLS.map((c) => `<text class="colhead" x="${c.x}" y="22">${c.title}</text>`).join('');
  const apCls = t.run.protection === 'on' && !ap.block && !ap.executed ? 'ap-held' : '';
  const apText = t.run.protection === 'on' ? '被挂起 / 阻断动作的上游路径' : '防护本应拦截、实际已执行的动作路径';
  $('#tab-graph').innerHTML = `
    <div class="graph-legend">
      ${ap.held.size ? `<label><input type="checkbox" id="ap-toggle" ${showAp ? 'checked' : ''}> 高亮拦截路径</label>
        <span><i style="border-color:${apCls ? 'var(--ask)' : 'var(--off)'};border-top-style:dashed"></i>${apText}（关联，非因果证明）</span>` : ''}
      <span><i style="border-color:var(--induce);border-top-style:dashed"></i>关联（来源 → 动作，未证实因果）</span>
      <span><i style="border-color:var(--edge)"></i>摄入 / 提出</span>
      <span><i style="border-color:var(--agent)"></i>派发子 Agent</span>
      <span><i style="border-color:var(--edge-effect)"></i>实际影响</span>
      <span><i style="border-color:var(--edge-prevented);border-top-style:dashed"></i>被拦截，未发生</span>
      <span class="muted">图${t.graph.acyclic ? '已通过无环检查' : '存在环，请检查证据'}</span>
    </div>
    <div class="graph-wrap"><svg class="${apCls}" width="${W}" height="${h}" viewBox="0 0 ${W} ${h}">
      <defs>${marker('m-red', 'var(--induce)')}${marker('m-gray', 'var(--edge)')}${marker('m-purple', 'var(--agent)')}${marker('m-dark', 'var(--edge-effect)')}${marker('m-ap', 'var(--ap)')}</defs>
      ${heads}${edges}${nodes}</svg></div>`;
  $('#ap-toggle')?.addEventListener('change', (e) => { tstate.ap = e.target.checked; renderGraph(t); });

  const svg = $('#tab-graph svg');
  const neighbors = (id) => {
    const keep = new Set([id]);
    // walk both directions so the whole path through the node lights up
    let grew = true;
    while (grew) {
      grew = false;
      for (const e of g.edges) {
        if (keep.has(e.from) && !keep.has(e.to) && (e.from === id || g.nodes.find((n) => n.id === e.from).layer <= g.nodes.find((n) => n.id === e.to).layer)) { keep.add(e.to); grew = true; }
      }
    }
    for (const e of g.edges) if (e.to === id || (keep.has(e.to) && e.kind.startsWith('induce'))) keep.add(e.from);
    for (const e of g.edges) if (e.to === id) keep.add(e.from);
    return keep;
  };
  $$('.node', svg).forEach((el) => {
    const n = g.nodes.find((x) => x.id === el.dataset.id);
    el.addEventListener('mouseenter', (ev) => {
      const keep = neighbors(n.id);
      $$('.node', svg).forEach((x) => x.classList.toggle('dim', !keep.has(x.dataset.id)));
      $$('.edge', svg).forEach((x) => x.classList.toggle('dim', !(keep.has(x.dataset.from) && keep.has(x.dataset.to))));
      showTip(ev, tipFor(n, t));
    });
    el.addEventListener('mousemove', moveTip);
    el.addEventListener('mouseleave', () => { $$('.dim', svg).forEach((x) => x.classList.remove('dim')); hideTip(); });
    el.addEventListener('click', () => {
      if (n.kind === 'call') { tstate.selCall = n.id.slice(5); tstate.tab = 'calls'; renderTab(); }
      if (n.kind === 'source') { tstate.tab = 'sources'; renderTab(); const el2 = document.getElementById('src-' + n.id.slice(4)); el2?.scrollIntoView({ behavior: 'smooth' }); }
    });
  });
}

function tipFor(n, t) {
  if (n.kind === 'call') {
    const c = t.calls.find((x) => 'call:' + x.call_id === n.id);
    return c ? `${c.op} ${c.target}\n裁决 ${c.verdict} · ${c.rule_id || ''} · 风险 ${c.risk || ''}\n${c.reason || ''}` : n.label;
  }
  if (n.kind === 'user') return n.detail || '';
  return n.label;
}
// ---------------- timeline (swimlanes) ----------------
function renderTimeline(t) {
  const lanes = t.agents.map((a) => a.id);
  const head = `<tr><th>时间</th>${t.agents.map((a) => `<th>${esc(a.label)}</th>`).join('')}</tr>`;
  const rows = t.timeline.map((ev) => {
    const lane = lanes.indexOf(ev.agent);
    const cls = ev.kind === 'guard_decision' ? 'decision-' + (ev.would_verdict || ev.verdict) : ev.kind;
    const extra = ev.kind === 'guard_decision' ? `<div class="dt">${esc(ev.rule_id || '')} · 风险 ${esc(ev.risk || '')} · ${esc(ev.reason || '')}</div>` : '';
    const card = `<div class="ev ${esc(cls)}"><div class="ttl">${esc(ev.title)}</div>${ev.detail ? `<div class="dt">${esc(ev.detail)}</div>` : ''}${extra}</div>`;
    const cells = lanes.map((_, i) => `<td class="lane">${i === lane ? card : ''}</td>`).join('');
    return `<tr><td class="t">${ev.t_ms != null ? (ev.t_ms / 1000).toFixed(2) + 's' : ''}</td>${cells}</tr>`;
  }).join('');
  $('#tab-timeline').innerHTML = `<table class="lanes">${head}${rows}</table>`;
}

// ---------------- verdict details ----------------
const FACT_ZH = {
  hard_policy: '命中硬策略', soft_policy: '命中状态策略', secret_hit: '参数含机密指纹', untrusted_sink: '不可信外发出口',
  network_granted: '网络目标已授权', context_secret: '上下文含机密', literal_scope: '在字面授权内', sensitive: '敏感目标',
  directive: '命中外部指令', tainted: '上下文已摄入外部内容', request_tainted: '上下文含请求污染', low_risk: '低风险动作',
  high_risk: '高风险动作', unknowns: '存在未解析指令',
};
function renderCalls(t) {
  const rows = t.calls.map((c, i) => {
    const facts = Object.entries(c.decision_facts || {}).filter(([k, v]) => FACT_ZH[k] && v !== null && v !== undefined)
      .map(([k, v]) => `<span class="fact ${v ? 'on' : ''}">${FACT_ZH[k]}：${v === true ? '是' : v === false ? '否' : esc(v)}</span>`).join('');
    const induced = (c.induced_by || []).map((x) => `<div class="quote"><b>${esc(x.uri)}</b>${x.span ? ` [${x.span.join('–')}]` : ''}${x.excerpt ? '：' + esc(x.excerpt) : ''}</div>`).join('');
    const s1 = c.fast && c.fast.model_used ? `<div class="small">快镜：${esc(JSON.stringify(c.fast).slice(0, 300))}</div>` : `<div class="small muted">快镜：${esc((c.fast && c.fast.reason) || '本动作未调用')}</div>`;
    const sel = tstate.selCall === c.call_id;
    return `<tr class="main-row ${sel ? 'sel' : ''}" data-cid="${esc(c.call_id)}">
        <td>${i + 1}</td><td>${esc(t.agents.find((a) => a.id === c.agent)?.label || c.agent)}</td><td>${esc(c.op)}</td>
        <td class="target">${esc(c.target)}</td><td>${verdictBadge(c)}</td><td>${esc(c.rule_id || '')}</td><td>${esc(c.risk || '')}</td>
        <td>${c.latency_ms != null ? c.latency_ms.toFixed(1) + ' ms' : ''}</td><td>${c.executed ? '已执行' : '未执行'}</td></tr>
      <tr class="detail ${sel ? '' : 'hidden'}" data-for="${esc(c.call_id)}"><td></td><td colspan="8">
        <div><b>裁决理由：</b>${esc(c.reason || '')}</div>
        <div class="facts">${facts}</div>
        ${induced ? `<div><b>关联的外部指令：</b>${induced}</div>` : ''}
        ${s1}
        ${c.result_excerpt ? `<div class="small"><b>返回摘要：</b>${esc(c.result_excerpt)}</div>` : ''}
        <div class="small muted">参数：${esc(JSON.stringify(c.args))}</div>
      </td></tr>`;
  }).join('');
  $('#tab-calls').innerHTML = `<table class="calls"><tr><th>#</th><th>Agent</th><th>操作</th><th>目标</th><th>裁决</th><th>规则</th><th>风险</th><th>裁决耗时</th><th>执行</th></tr>${rows}</table>`;
  $$('#tab-calls tr.main-row').forEach((tr) => tr.addEventListener('click', () => {
    tstate.selCall = tstate.selCall === tr.dataset.cid ? null : tr.dataset.cid; renderCalls(t);
  }));
}

// ---------------- sources with highlighted spans ----------------
const PRIORITY = { injection: 4, directive: 3, s1: 2, unknown: 1 };
function highlight(text, marks) {
  const chars = Array.from(text);
  const owner = new Array(chars.length).fill(null);
  for (const m of marks) {
    const [a, b] = m.span;
    for (let i = Math.max(0, a); i < Math.min(chars.length, b); i++) {
      if (!owner[i] || PRIORITY[m.kind] > PRIORITY[owner[i].kind]) owner[i] = m;
    }
  }
  let out = '', i = 0;
  while (i < chars.length) {
    const m = owner[i]; let j = i;
    while (j < chars.length && owner[j] === m) j++;
    const seg = esc(chars.slice(i, j).join(''));
    out += m ? `<mark class="${m.kind}" title="${esc(m.label)}">${seg}</mark>` : seg;
    i = j;
  }
  return out;
}
function renderSources(t) {
  if (!t.sources.length) { $('#tab-sources').innerHTML = '<p class="muted">本轮没有摄入外部内容。</p>'; return; }
  $('#tab-sources').innerHTML = `
    <div class="graph-legend"><span><mark class="injection">　</mark> 直接注入特征</span><span><mark class="directive">　</mark> 规则抽取的指令</span><span><mark class="s1">　</mark> 快镜 S1 检出</span><span><mark class="unknown">　</mark> 未完全解析的指令信号</span></div>
    ${t.sources.map((s) => {
      const s1 = s.s1 && typeof s.s1 === 'object' && s.s1.label ? badge('S1：' + s.s1.label + (s.s1.p != null ? ' ' + Number(s.s1.p).toFixed(2) : ''), s.s1.label === 'request' ? 'block' : '') : '';
      return `<div class="src" id="src-${esc(s.event_id)}"><div class="src-head">${badge(s.kind)}<b>${esc(s.uri)}</b>${s1}
        <span class="muted small">由 ${esc(t.agents.find((a) => a.id === s.agent)?.label || s.agent)} 摄入 · 事件 ${esc(s.event_id.slice(0, 8))}</span>
        ${s.highlights.length ? badge(`${s.highlights.length} 处标记`, 'block') : ''}</div>
        <pre>${highlight(s.text, s.highlights)}</pre></div>`;
    }).join('')}`;
}

// ---------------- analysis report ----------------
function renderReport(t) {
  const imp = t.impact;
  const list = (xs) => (xs.length ? xs.map(esc).join('<br>') : '<span class="muted">无</span>');
  const flagged = t.calls.filter((c) => ['ASK', 'BLOCK'].includes(effectiveVerdict(c)));
  const cards = flagged.map((c) => {
    const rv = c.review;
    let slow = '<div class="slow muted small">慢镜研判：本轮未生成。</div>';
    if (rv && rv.status === 'ok') {
      slow = `<div class="slow"><b>慢镜研判</b> ${badge(rv.semantic_alignment === 'DEVIANT_INJECTION' ? '判定为注入诱导' : rv.semantic_alignment, 'block')} ${badge('建议 ' + rv.recommended_verdict)}
        <span class="muted small">${rv.latency_ms ? '耗时 ' + (rv.latency_ms / 1000).toFixed(1) + 's · ' : ''}异步生成，不改变裁决</span>
        <div class="txt">${esc(rv.explainable_report_zh)}</div>
        <div class="small muted">引用证据：${(rv.supporting_event_ids || []).map((x) => esc(x.slice(0, 12))).join('，')}</div></div>`;
    } else if (rv && rv.status === 'failed') {
      slow = `<div class="slow muted small">慢镜研判未完成（${esc(rv.error_type)}）。上方确定性研判不受影响，裁决也不受影响。</div>`;
    }
    return `<div class="report-card"><h3>${esc(c.op)} <span class="target">${esc(c.target)}</span> ${verdictBadge(c)} ${badge(c.rule_id || '')}</h3>
      <div class="txt">${esc(c.report || '')}</div>${slow}</div>`;
  }).join('');
  $('#tab-report').innerHTML = `
    <div class="impact">
      <div><b>读取的文件</b>${list(imp.files_read)}</div>
      <div><b>写入的文件</b>${list(imp.files_written)}</div>
      <div><b>网络目标</b>${list(imp.network)}</div>
      <div><b>防护处置</b>挂起 ${imp.asked} 次 · 阻断 ${imp.blocked} 次<br>接收端收到 ${imp.received_bytes ?? 0} 字节</div>
    </div>
    ${cards || '<p class="muted">本轮没有需要研判的动作：所有调用都在授权内或为低风险。</p>'}`;
}
