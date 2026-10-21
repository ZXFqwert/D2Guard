'use strict';
// 攻防大屏：竞赛评测指标、运行时防御链路、“同一攻击 · 两种结局”证据回放、安全链 vs 原始上下文、攻击家族与三臂消融。
// 页面不写死任何结果数字：指标来自 /api/summary（console/data/evaluation-summary.json），
// 回放与曲线来自 /api/replay、/api/compaction 对 runs/ 运行证据的只读投影。

const scr = { speed: 10, duel: null, pairKey: null, cmpRun: null };
const REDUCED = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const rate = (o) => (o && o.d ? (100 * o.n) / o.d : null);
const r1 = (v) => (v == null ? null : Math.round(v * 10) / 10);
const dpOf = (v) => (Number.isInteger(v) ? 0 : 1);
const pctTxt = (v) => (v == null ? '—' : `${r1(v).toFixed(dpOf(r1(v)))}%`);
const kb = (b) => (b == null ? '—' : `${(b / 1000).toFixed(1)} KB`);
const frac = (s) => { const m = /^(\d+)\s*\/\s*(\d+)$/.exec(String(s ?? '')); return m ? { n: +m[1], d: +m[2] } : null; };
const fracTxt = (o) => (o ? `${o.n}/${o.d}` : '—');
const VZH = { ALLOW: '放行', ASK: '挂起', BLOCK: '阻断' };
const S1ZH = { request: '请求', none: '无请求', quoted: '引用' };
const isHold = (v) => v === 'ASK' || v === 'BLOCK';
const cu = (v, dp = dpOf(v)) => `<span class="cu" data-v="${v}" data-dp="${dp}">${Number(v).toFixed(dp)}</span>`;

PAGES.screen = async (el, args) => {
  const full = args[0] === 'full';
  document.body.classList.toggle('scr-full', full);
  onLeave(() => document.body.classList.remove('scr-full'));
  const [summary, runs, comp, scenarios] = await Promise.all([
    api('/api/summary').catch(() => null),
    api('/api/runs?environment=attack&limit=3000').catch(() => ({ runs: [] })),
    api('/api/compaction').catch(() => ({ runs: [] })),
    getScenarios().catch(() => []),
  ]);
  const modes = {};
  runs.runs.forEach((r) => { if (r.decision_mode && r.decision_mode !== 'unknown') modes[r.decision_mode] = (modes[r.decision_mode] || 0) + 1; });
  const mode = Object.entries(modes).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
  const pairs = duelPairs(runs.runs, scenarios);
  el.innerHTML = `
  <div class="scr" id="scr">
    <canvas class="scr-bg" id="scr-bg"></canvas>
    ${scrHeader(summary, mode, full)}
    ${summary ? kpiRibbon(summary) : `<div class="scr-note">未找到竞赛评测汇总 <span class="mono">console/data/evaluation-summary.json</span>：已隐藏评测指标、攻击家族与消融板块。下方回放与曲线仍直接读取运行证据。</div>`}
    ${pipelinePanel(summary)}
    ${duelPanel(pairs)}
    ${cmpPanel(comp.runs || [], summary)}
    ${summary ? `<div class="scr-grid2">${famPanel(summary)}${ablPanel(summary, mode)}</div>` : ''}
    <div class="sp-src" style="text-align:center;margin-top:4px">指标取自竞赛评测汇总 evaluation-summary.json；回放、曲线取自 runs/ 运行证据，只读投影，不重算、不改写任何裁决；合成凭据已脱敏。</div>
  </div>`;
  startBackdrop();
  startClock();
  countUp($('#scr'));
  $('#scr-full').addEventListener('click', toggleFull);
  if (pairs.length) initDuel(pairs);
  initCompaction(comp.runs || []);
};

function toggleFull() {
  const on = !document.body.classList.contains('scr-full');
  document.body.classList.toggle('scr-full', on);
  history.replaceState(null, '', on ? '#/screen/full' : '#/screen');
  app.lastHash = location.hash;
  $('#scr-full').textContent = on ? '⤡ 退出全屏' : '⛶ 全屏';
  try {
    if (on && !document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
    if (!on && document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  } catch { /* fullscreen is a convenience; the full-bleed layout already applies */ }
}

// ---------------- header, clock, backdrop ----------------
function scrHeader(s, mode, full) {
  const batch = s ? `竞赛评测（2026-10，83 个场景）· ${esc(s.cells)} 格` : '竞赛评测汇总缺失';
  return `
  <header class="scr-head">
    <div class="scr-brand">
      <div class="scr-logo"><svg viewBox="0 0 46 46"><defs><linearGradient id="lg-logo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#2563eb"/></linearGradient></defs>
        <path d="M23 2 L41 12.5 V33.5 L23 44 L5 33.5 V12.5 Z" fill="rgba(37,99,235,.25)" stroke="url(#lg-logo)" stroke-width="2"/>
        <path d="M23 8 L36 15.5 V30.5 L23 38 L10 30.5 V15.5 Z" fill="none" stroke="rgba(34,211,238,.35)" stroke-width="1"/></svg><b>D²</b></div>
      <div><div class="scr-title">双镜 D²Guard</div><div class="scr-sub">智能体运行时攻防态势大屏</div></div>
    </div>
    <div class="scr-slogan" id="scr-slogan"><span>检测</span><i>→</i><span>研判</span><i>→</i><span>阻断</span><i>→</i><span>溯源</span></div>
    <div class="scr-right">
      <div class="scr-clock"><b id="scr-time">--:--:--</b><small id="scr-date"></small></div>
      <button class="scr-btn" id="scr-full">${full ? '⤡ 退出全屏' : '⛶ 全屏'}</button>
    </div>
  </header>
  <div class="scr-strip">
    <div class="scr-badges">
      <span class="scr-badge live">宿主 <b>Pi Agent</b></span><span class="scr-badge">内核 <b>d2v2</b></span>
      <span class="scr-badge">快镜 <b>D²Guard-Laya</b></span>${mode ? `<span class="scr-badge">决策模式 <b>${esc(mode)}</b></span>` : ''}
      <span class="scr-badge">本地 <b>127.0.0.1</b></span>
    </div>
    <div>数据来源：${batch} · 运行证据 runs/</div>
  </div>`;
}

function startClock() {
  const pad = (n) => String(n).padStart(2, '0');
  const WD = '日一二三四五六';
  const tick = () => {
    const d = new Date(), t = $('#scr-time');
    if (!t) return;
    t.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    $('#scr-date').textContent = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} 星期${WD[d.getDay()]}`;
  };
  tick();
  const spans = $$('#scr-slogan span');
  let k = 0;
  const lit = () => { spans.forEach((s, i) => s.classList.toggle('lit', i === k % spans.length)); k++; };
  lit();
  const a = setInterval(tick, 1000), b = setInterval(lit, 1400);
  onLeave(() => { clearInterval(a); clearInterval(b); });
}

function startBackdrop() {
  const cv = $('#scr-bg');
  if (!cv || REDUCED()) return;
  const ctx = cv.getContext('2d');
  let w = 0, h = 0, raf = 0;
  const P = [];
  const resize = () => {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    w = cv.clientWidth; h = cv.clientHeight;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  resize();
  for (let i = 0; i < 64; i++) P.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.22, vy: (Math.random() - 0.5) * 0.22, r: Math.random() * 1.3 + 0.5, atk: Math.random() < 0.14 });
  const D = 140;
  const frame = () => {
    ctx.clearRect(0, 0, w, h);
    for (const p of P) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < -10) p.x = w + 10; if (p.x > w + 10) p.x = -10;
      if (p.y < -10) p.y = h + 10; if (p.y > h + 10) p.y = -10;
    }
    ctx.lineWidth = 1;
    for (let i = 0; i < P.length; i++) {
      for (let j = i + 1; j < P.length; j++) {
        const dx = P[i].x - P[j].x, dy = P[i].y - P[j].y, d2 = dx * dx + dy * dy;
        if (d2 > D * D) continue;
        ctx.strokeStyle = `rgba(56,189,248,${(1 - Math.sqrt(d2) / D) * 0.16})`;
        ctx.beginPath(); ctx.moveTo(P[i].x, P[i].y); ctx.lineTo(P[j].x, P[j].y); ctx.stroke();
      }
    }
    for (const p of P) {
      ctx.fillStyle = p.atk ? 'rgba(255,107,122,.75)' : 'rgba(125,211,252,.7)';
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
    }
    raf = requestAnimationFrame(frame);
  };
  frame();
  window.addEventListener('resize', resize);
  onLeave(() => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); });
}

function countUp(root) {
  const bars = $$('[data-w]', root);
  const els = $$('.cu', root);
  if (REDUCED()) { bars.forEach((b) => { b.style.width = b.dataset.w + '%'; }); return; }
  els.forEach((e) => { e.textContent = (0).toFixed(+e.dataset.dp); });
  const t0 = performance.now(), dur = 1600;
  let raf = 0;
  const frame = (now) => {
    const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    els.forEach((x) => { x.textContent = (+x.dataset.v * e).toFixed(+x.dataset.dp); });
    if (k < 1) raf = requestAnimationFrame(frame);
  };
  raf = requestAnimationFrame(frame);
  requestAnimationFrame(() => requestAnimationFrame(() => bars.forEach((b) => { b.style.width = b.dataset.w + '%'; })));
  onLeave(() => cancelAnimationFrame(raf));
}

// ---------------- KPI ribbon (evaluation-summary.json only) ----------------
function kpiRibbon(s) {
  const off = r1(rate(s.off_asr)), on = r1(rate(s.on_asr));
  const doneOff = r1(rate(s.clean_off_done)), doneOn = r1(rate(s.clean_on_done));
  const benign = s.benign_hold, local = s.local_path, L = s.latency_ms || {};
  const src = esc(`竞赛评测 ${s.cells} 格`);
  const tile = (style, body, srcTxt = src) => `<div class="kt" style="${style}">${body}<div class="kt-src">${srcTxt}</div></div>`;
  const tiles = [];
  if (off != null && on != null) tiles.push(tile('--kc:#ff4d61;--kg:rgba(255,77,97,.2)', `
    <div class="kt-l"><span>攻击成功率</span><span style="color:var(--s-faint)">防护关闭 → 开启</span></div>
    <div class="kt-v"><span class="atk">${cu(off)}<i>%</i></span><span class="arrow">→</span><span class="def">${cu(on)}<i>%</i></span></div>
    <div class="kt-bars"><span>关闭</span><span class="tr"><span class="fl atk" data-w="${off}"></span></span><em>${fracTxt(s.off_asr)}</em>
      <span>开启</span><span class="tr"><span class="fl def" data-w="${on}"></span></span><em>${fracTxt(s.on_asr)}</em></div>
    ${s.asr_basis ? `<div class="kt-s">${esc(s.asr_basis)}</div>` : ''}`, `${src} · 攻击环境`));
  if (doneOff != null && doneOn != null) tiles.push(tile('--kc:#38bdf8;--kg:rgba(56,189,248,.2)', `
    <div class="kt-l"><span>正常任务自动完成</span><span style="color:var(--s-faint)">防护关闭 → 开启</span></div>
    <div class="kt-v sm"><span class="def">${cu(doneOff)}<i>%</i></span><span class="arrow">→</span><span class="def">${cu(doneOn)}<i>%</i></span></div>
    <div class="kt-s"><b>${fracTxt(s.clean_off_done)} → ${fracTxt(s.clean_on_done)}</b>${s.clean_on_pending != null ? ` · 其余 ${esc(s.clean_on_pending)} 次等待人工确认，阻断 ${esc(s.clean_on_blocked ?? 0)}` : ''}</div>`, `${src} · 干净环境`));
  if (benign) tiles.push(tile('--kc:#34d399;--kg:rgba(52,211,153,.18);--kg2:rgba(52,211,153,.5)', `
    <div class="kt-l">良性动作误挂起</div>
    <div class="kt-v glow">${cu(benign.n, 0)}<i>/${esc(benign.d)}</i></div>
    <div class="kt-bars" style="grid-template-columns:1fr auto"><span class="tr"><span class="fl" style="background:linear-gradient(90deg,#047857,#34d399);box-shadow:0 0 10px rgba(52,211,153,.6)" data-w="${r1(100 - rate(benign))}"></span></span><em>${esc(benign.d - benign.n)} 放行</em></div>
    <div class="kt-s">自身裁决${s.benign_session_cascade ? `；另有 ${esc(s.benign_session_cascade)} 次会话连带暂停` : ''}</div>`));
  if (L.decision_p50 != null) tiles.push(tile('--kc:#60a5fa;--kg:rgba(96,165,250,.2)', `
    <div class="kt-l">单动作裁决 <span style="color:var(--s-faint)">p50</span></div>
    <div class="kt-v glow">${cu(Math.round(L.decision_p50), 0)}<i>ms</i></div>
    ${L.decision_p95 != null ? `<div class="kt-gauge" title="0–100 ms 刻度；虚线为 p95"><span data-w="${Math.min(100, L.decision_p50)}" style="width:0"></span><em style="left:${Math.min(100, L.decision_p95)}%"></em></div>` : ''}
    <div class="kt-s">${L.decision_p95 != null ? `p95 <b>${Math.round(L.decision_p95)} ms</b> · ` : ''}本地决策</div>`));
  if (L.s1_gpu_p50 != null) tiles.push(tile('--kc:#22d3ee;--kg:rgba(34,211,238,.2)', `
    <div class="kt-l">快镜推理 <span style="color:var(--s-faint)">GPU p50</span></div>
    <div class="kt-v glow">${cu(Math.round(L.s1_gpu_p50), 0)}<i>ms</i></div>
    ${L.s1_cpu_p50 != null ? `<div class="kt-gauge" title="0–200 ms 刻度；虚线为 CPU p50"><span data-w="${Math.min(100, L.s1_gpu_p50 / 2)}" style="width:0"></span><em style="left:${Math.min(100, L.s1_cpu_p50 / 2)}%"></em></div>` : ''}
    <div class="kt-s">${L.s1_cpu_p50 != null ? `CPU p50 <b>${Math.round(L.s1_cpu_p50)} ms</b>` : 'D²Guard-Laya'}</div>`));
  if (local) tiles.push(tile('--kc:#a78bfa;--kg:rgba(167,139,250,.2);--kg2:rgba(167,139,250,.55)', `
    <div class="kt-l">本地裁决</div>
    <div class="kt-v glow">${cu(r1(rate(local)))}<i>%</i></div>
    <div class="kt-bars" style="grid-template-columns:1fr auto"><span class="tr"><span class="fl" style="background:linear-gradient(90deg,#6d28d9,#a78bfa);box-shadow:0 0 10px rgba(167,139,250,.6)" data-w="${r1(rate(local))}"></span></span><em>${fracTxt(local)}</em></div>
    <div class="kt-s">全部裁决走本地路径</div>`));
  return `<section class="kr">${tiles.join('')}</section>`;
}

// ---------------- animated architecture / pipeline ----------------
function pipelinePanel(s) {
  const L = (s && s.latency_ms) || {};
  const fastMs = L.s1_gpu_p50 != null ? `GPU p50 ${Math.round(L.s1_gpu_p50)} ms` : '同步判定';
  const N = [
    { x: 0, w: 180, num: '01', title: '原生 Agent' },
    { x: 212, w: 200, num: '02', title: '三组件接入', tag: '检测' },
    { x: 444, w: 200, num: '03', title: 'D² 增量安全链', tag: '检测' },
    { x: 676, w: 252, num: '04', title: 'D¹ 快慢双镜内核', tag: '研判' },
    { x: 960, w: 170, num: '05', title: '三态裁决', tag: '阻断' },
    { x: 1162, w: 158, num: '06', title: '溯源', tag: '溯源' },
  ];
  const Y = 46, H = 160, MID = Y + 80;
  const body = [
    `<text class="pn-line em" x="14" y="72">Pi CLI · 真实 LLM</text>
     <text class="pn-line" x="14" y="92">工具调用循环（tool-use）</text>
     <text class="pn-line" x="14" y="112">主 / 子 Agent 多层派发</text>
     <rect x="14" y="124" width="152" height="24" rx="5" fill="#040a18" stroke="rgba(96,165,250,.35)"/>
     <text x="24" y="140" style="font:11px var(--mono);fill:#7dd3fc">&gt; tool_call(…)</text><rect x="118" y="131" width="7" height="11" fill="#7dd3fc"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>`,
    ['宿主 Hook 插件', 'API 网关 · Sidecar', 'MCP 中间代理'].map((t, i) => `<g class="pn-chip" id="chip-${['hook', 'gw', 'mcp'][i]}"><rect x="14" y="${60 + i * 31}" width="172" height="25" rx="6"/><text x="26" y="${77 + i * 31}">${t}</text></g>`).join(''),
    `${[0, 1, 2, 3, 4, 5].map((i) => `${i ? `<line class="chain-l" x1="${14 + i * 29 - 11}" y1="71" x2="${14 + i * 29}" y2="71"/>` : ''}<rect class="chain-b${i === 5 ? ' new' : ''}" x="${14 + i * 29}" y="62" width="18" height="18" rx="4"/>`).join('')}
     <text class="pn-line em" x="14" y="106">原始轨迹 → 安全要素</text>
     <text class="pn-line" x="14" y="126">只追加（append-only）</text>
     <text class="pn-line" x="14" y="146">裁决读取有界状态快照</text>`,
    `<g class="pn-sub" id="sub-rule"><rect x="14" y="58" width="108" height="92" rx="8"/><text class="h" x="26" y="80">规则</text><text class="l" x="26" y="100">策略 DSL</text><text class="l" x="26" y="118">＋ 决策表</text><text class="v" x="26" y="138">确定性</text></g>
     <g class="pn-sub fast" id="sub-fast"><rect x="130" y="58" width="108" height="92" rx="8"/><text class="h" x="142" y="80">快镜</text><text class="l" x="142" y="100">Laya 322M</text><text class="l" x="142" y="118">请求意图判定</text><text class="v" x="142" y="138">${esc(fastMs)}</text></g>`,
    ['ALLOW', 'ASK', 'BLOCK'].map((v, i) => `<g class="pv ${v.toLowerCase()}" id="pv-${v}"><rect x="14" y="${60 + i * 31}" width="142" height="25" rx="6"/><text x="85" y="${77 + i * 31}" text-anchor="middle">${v} ${VZH[v]}</text></g>`).join(''),
    `<g class="glyph"><line x1="34" y1="72" x2="79" y2="88"/><line x1="34" y1="104" x2="79" y2="88"/><line x1="79" y1="88" x2="124" y2="72"/><line x1="79" y1="88" x2="124" y2="104"/></g>
     <circle class="glyph-f" cx="34" cy="72" r="5"/><circle class="glyph-f" cx="34" cy="104" r="5"/><circle cx="79" cy="88" r="7" fill="#fbbf24"/><circle class="glyph-f" cx="124" cy="72" r="5"/><circle cx="124" cy="104" r="5" fill="none" stroke="#7dd3fc" stroke-dasharray="2 2"/>
     <text class="pn-line em" x="14" y="132">攻击路径 DAG</text><text class="pn-line" x="14" y="150">时序链路 · 研判报告</text>`,
  ];
  const nodes = N.map((n, i) => `<g class="pn" id="pn-${i}" transform="translate(${n.x},${Y})">
      <rect class="pn-box" width="${n.w}" height="${H}" rx="12"/>
      <text class="pn-num" x="14" y="22">${n.num}</text>
      ${n.tag ? `<rect class="pn-tag-bg${n.tag === '阻断' ? ' atk' : ''}" x="${n.w - 50}" y="9" width="38" height="18" rx="5"/><text class="pn-tag" x="${n.w - 31}" y="22" text-anchor="middle">${n.tag}</text>` : ''}
      <text class="pn-title" x="14" y="46">${n.title}</text>${body[i]}</g>`).join('');
  const flow = `M180,${MID} L1162,${MID}`;
  const ret = `M1045,${Y} L1045,26 Q1045,16 1035,16 L100,16 Q90,16 90,26 L90,${Y}`;
  const slowDown = `M802,${Y + H} L802,238`, slowUp = `M1241,238 L1241,${Y + H}`;
  const particles = (path, n, dur, cls = '') => Array.from({ length: n }, (_, i) => `<circle class="pp ${cls}" r="${cls ? 2.4 : 3}"><animateMotion dur="${dur}s" repeatCount="indefinite" begin="${(-i * dur) / n}s" path="${path}"/></circle>`).join('');
  return `
  <section class="sp pipe">
    <div class="sp-h">
      <div><div class="sp-t">D² 运行时防御链路 <small>检测 → 研判 → 阻断 → 溯源</small></div>
        <div class="sp-d">接入真实 Pi Agent 的工具循环：安全要素从原始轨迹抽取进入增量安全链，规则与快镜同步检测，决策表研判后在执行前裁决，慢镜异步溯源并生成研判报告，全程留证。回放时高亮当前事件所在环节。</div></div>
      <div class="pipe-legend"><span><i style="border-color:#38bdf8"></i>工具调用 / 来源内容</span><span><i style="border-color:#34d399"></i>裁决回传 Agent</span><span><i style="border-color:#a78bfa;border-top-style:dashed"></i>异步溯源（不改裁决）</span></div>
    </div>
    <svg viewBox="0 0 1320 292" role="img" aria-label="D²Guard 运行时防御链路">
      <defs>
        <linearGradient id="pn-grad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#11214a"/><stop offset="1" stop-color="#0a142f"/></linearGradient>
        <filter id="pn-glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <marker id="pn-arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#38bdf8"/></marker>
        <marker id="pn-arr-g" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#34d399"/></marker>
      </defs>
      <path class="pe pe-back" d="${ret}" marker-end="url(#pn-arr-g)"/><path class="pe-flow ret" d="${ret}"/>${particles(ret, 3, 7, 'ret')}
      <rect class="ret-bg" x="372" y="6" width="390" height="20" rx="4"/>
      <text class="ret-label" x="567" y="20" text-anchor="middle">裁决回传：ALLOW 执行 · ASK 挂起待用户确认 · BLOCK 拒绝</text>
      ${N.slice(0, -1).map((n, i) => `<path class="pe" d="M${n.x + n.w},${MID} L${N[i + 1].x - 2},${MID}" marker-end="url(#pn-arr)"/>`).join('')}
      <path class="pe-flow" d="${flow}"/>
      <path class="pe pe-slow" d="${slowDown}"/><path class="pe-flow slow" d="${slowDown}"/>
      <path class="pe pe-slow" d="${slowUp}"/><path class="pe-flow slow" d="${slowUp}"/>
      ${particles(flow, 7, 6)}
      ${nodes}
      <g id="pn-slow"><rect class="slow-box" x="676" y="238" width="644" height="50" rx="10"/>
        <text class="slow-t" x="694" y="259">慢镜 · 异步溯源与研判报告</text>
        <text class="slow-l" x="694" y="278">读取只读证据包，还原攻击路径并生成研判报告；不改变裁决</text>
        <rect class="pn-tag-bg vio" x="1268" y="249" width="38" height="18" rx="5"/><text class="pn-tag" x="1287" y="262" text-anchor="middle">溯源</text></g>
    </svg>
  </section>`;
}

// Light the stages an evidence event passes through, in the pipeline and in the duel spine.
function pulse(lane, steps) {
  const color = lane === 'off' ? '#ff4d61' : '#22d3ee';
  steps.forEach((s, k) => later(() => {
    const li = $(`#spine li[data-st="${s.st}"]`);
    const els = [$('#pn-' + s.st), ...(s.el || []).map((id) => $('#' + id))].filter(Boolean);
    li?.classList.add('on-' + lane);
    els.forEach((x) => { x.style.setProperty('--hc', color); x.classList.add('hot'); x.querySelector('.slow-box')?.classList.add('hot'); });
    later(() => { li?.classList.remove('on-' + lane); els.forEach((x) => { x.classList.remove('hot'); x.querySelector('.slow-box')?.classList.remove('hot'); }); }, 900);
  }, k * 150));
}

// ---------------- duel replay: same attack, two endings ----------------
function duelPairs(runs, scenarios) {
  const by = {};
  for (const r of runs) { // newest first
    if (!r.complete || r.environment !== 'attack' || r.category === 'normal' || !['on', 'off'].includes(r.protection)) continue;
    const s = (by[r.scenario] ||= {});
    if (!s[r.protection]) s[r.protection] = r;
  }
  const info = Object.fromEntries(scenarios.map((s) => [s.id, s]));
  return Object.entries(by).filter(([, s]) => s.off && s.on)
    .map(([id, s]) => ({ id, off: s.off, on: s.on, info: info[id] || {}, showcase: !!s.off.attack_succeeded && !s.on.attack_succeeded }))
    .sort((a, b) => (b.showcase - a.showcase) || a.id.localeCompare(b.id));
}

function duelPanel(pairs) {
  const head = `<div class="sp-h"><div><div class="sp-t">同一攻击 · 两种结局 <small>证据回放</small></div>
    <div class="sp-d">同一任务、同一载荷，分别在防护关闭 / 开启下运行真实 Pi Agent；按运行证据记录的真实时间顺序回放每一次工具调用、来源判定与裁决。</div></div></div>`;
  if (!pairs.length) return `<section class="sp" id="duel">${head}<div class="scr-note">运行记录中暂无同一场景“攻击环境 · 防护关闭 / 开启”的成对运行。</div></section>`;
  const label = (p) => `${p.id} · ${p.info.family_label || p.off.family || ''}${p.showcase ? '　关闭得逞 / 开启拦截' : ''}`;
  return `
  <section class="sp" id="duel">${head}
    <div class="duel-ctl">
      <select id="duel-pair">${pairs.map((p) => `<option value="${esc(p.id)}">${esc(label(p))}</option>`).join('')}</select>
      <button class="scr-btn primary" id="duel-play">▶ 播放</button>
      <button class="scr-btn" id="duel-skip">⏭ 跳到结果</button>
      <button class="scr-btn" id="duel-reset">↺ 重置</button>
      <span class="sp-src" style="margin-left:6px">回放速度</span>
      <div class="scr-seg" id="duel-speed">${[5, 10, 25, 50].map((v) => `<button data-s="${v}">${v}×</button>`).join('')}</div>
      <div class="duel-clock">证据时间 <b id="duel-t">0.0</b> s / <span id="duel-tmax">—</span> s</div>
    </div>
    <div class="duel-info" id="duel-info"></div>
    <div class="duel-track" id="duel-track"></div>
    <div class="duel-body">
      <div class="dl off" id="dl-off"></div>
      <div class="spine" id="spine">
        <div class="spine-core">D²<small>GUARD</small></div>
        <ol>${[['原生 Agent', 'Pi CLI'], ['三组件', 'Hook·网关·MCP'], ['增量安全链', '安全要素入链'], ['双镜内核', '规则＋快镜'], ['三态裁决', 'ALLOW/ASK/BLOCK'], ['溯源', 'DAG·时序']]
          .map(([a, b], i) => `<li data-st="${i}">${a}<small>${b}</small></li>`).join('')}</ol>
        <div class="spine-cap">两路运行同一内核<br>关闭时只记录“本应裁决”</div>
      </div>
      <div class="dl on" id="dl-on"></div>
    </div>
  </section>`;
}

function initDuel(pairs) {
  const sel = $('#duel-pair');
  const want = scr.pairKey && pairs.some((p) => p.id === scr.pairKey) ? scr.pairKey : (pairs.find((p) => p.id === 'e-attack-04') || pairs[0]).id;
  sel.value = want;
  const setSpeed = (v) => { scr.speed = v; $$('#duel-speed button').forEach((b) => b.classList.toggle('on', +b.dataset.s === v)); };
  setSpeed(scr.speed);
  $$('#duel-speed button').forEach((b) => b.addEventListener('click', () => setSpeed(+b.dataset.s)));
  let observer = null;
  const load = async (id) => {
    scr.pairKey = id;
    scr.duel?.stop();
    const p = pairs.find((x) => x.id === id);
    $('#duel-info').innerHTML = '<div class="task">正在读取运行证据…</div>';
    const [off, on] = await Promise.all([api('/api/replay/' + p.off.id), api('/api/replay/' + p.on.id)]);
    if (scr.pairKey !== id || !$('#duel-info')) return;
    scr.duel = makeDuel(p, { off, on });
    if (!observer && 'IntersectionObserver' in window && !REDUCED()) { // auto-play once, the first time the duel scrolls into view
      observer = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) { observer.disconnect(); if (scr.duel && !scr.duel.touched) scr.duel.play(); }
      }, { threshold: 0.35 });
      observer.observe($('#duel'));
      onLeave(() => observer.disconnect());
    }
  };
  sel.addEventListener('change', () => load(sel.value));
  $('#duel-play').addEventListener('click', () => { const d = scr.duel; if (!d) return; d.touched = true; d.playing ? d.pause() : d.play(); });
  $('#duel-skip').addEventListener('click', () => { const d = scr.duel; if (d) { d.touched = true; d.seek(d.tmax); } });
  $('#duel-reset').addEventListener('click', () => { const d = scr.duel; if (d) { d.touched = true; d.seek(0); } });
  $('#duel-track').addEventListener('click', (e) => {
    const d = scr.duel, box = e.currentTarget.getBoundingClientRect();
    if (!d) return;
    const f = Math.max(0, Math.min(1, (e.clientX - box.left - 48) / (box.width - 60)));
    d.touched = true; d.seek(f * d.tmax);
  });
  onLeave(() => scr.duel?.stop());
  load(want);
}

function makeDuel(pair, data) {
  const tmax = Math.max(data.off.end_t || 0, data.on.end_t || 0, 1);
  const st = { t: 0, playing: false, raf: 0, last: 0, tmax, touched: false };
  const info = pair.info || {};
  const task = data.on.run.task || data.off.run.task || '';
  // The payload shown is the source content the fast mirror flagged as a request in the unprotected run's own evidence.
  const flagged = [...data.off.events, ...data.on.events].find((e) => (e.kind === 'source' || e.kind === 'context') && e.s1?.label === 'request' && e.excerpt);
  const payload = flagged ? `<b>注入来源 ${esc(flagged.uri)}</b><span class="tag" style="background:rgba(167,139,250,.2);color:#e9d5ff">快镜 S1 request ${flagged.s1.p_request != null ? flagged.s1.p_request.toFixed(2) : ''}</span>${esc(flagged.excerpt)}`
    : info.payload_text ? `<b>攻击载荷</b>${esc(info.payload_text)}` : '<b>攻击载荷</b>见场景库';
  $('#duel-info').innerHTML = `
    <div class="task"><b>用户任务</b>${esc(task)}</div>
    <div class="pay"><span class="tag">${esc(info.family_label || pair.off.family || '攻击')}</span>${info.attack_source ? `<span class="tag">载荷来源 ${esc(info.attack_source)}</span>` : ''}${payload}</div>`;
  $('#duel-tmax').textContent = (tmax / 1000).toFixed(1);
  const pos = (t) => `calc(48px + (100% - 60px) * ${Math.min(1, t / tmax)})`;
  const ticks = (lane) => data[lane].events.filter((e) => e.kind === 'call' || (e.kind === 'source' && e.s1?.label === 'request')).map((e) => {
    const cls = e.kind === 'source' ? 'req' : lane === 'off' ? (e.executed && isHold(e.would) ? 'danger' : '') : (isHold(e.verdict) ? 'held' : '');
    return `<span class="tk ${lane} ${cls}" data-t="${e.t}" style="left:${pos(e.t)};top:${lane === 'off' ? 14 : 29}px"></span>`;
  }).join('');
  $('#duel-track').innerHTML = `
    <span class="lane-tag" style="left:40px;top:14px;color:#ff8f9b">关闭</span><span class="lane-tag" style="left:40px;top:29px;color:#7dd3fc">开启</span>
    <span class="row off" style="left:48px"></span><span class="row on" style="left:48px"></span>${ticks('off')}${ticks('on')}
    <span class="ph" id="duel-ph" style="left:${pos(0)}"></span>
    <span class="lb" style="left:48px">0 s</span><span class="lb" style="right:12px">${(tmax / 1000).toFixed(1)} s</span>`;
  const lanes = {};
  for (const side of ['off', 'on']) {
    const d = data[side], r = d.run;
    $('#dl-' + side).innerHTML = `
      <div class="dl-h"><div><b>${side === 'off' ? '防护关闭 · 裸奔 Agent' : '防护开启 · D²Guard 护航'}</b>
        <small>${side === 'off' ? '内核旁路记录“本应裁决”，不拦截' : '每次工具调用先裁决、后执行'} · ${runTime(r.id)}</small></div>
        <a href="#/trace/${esc(r.id)}">溯源 →</a></div>
      <div class="dl-k"><div><b id="k-${side}-n">0</b>工具调用</div><div><b id="k-${side}-x">0</b>本应拦截·已执行</div>
        <div><b id="k-${side}-h">0</b>挂起 / 阻断</div><div><b id="k-${side}-b">—</b>接收端字节</div></div>
      <div class="dl-feed" id="feed-${side}"></div>
      <div class="dl-end" id="end-${side}"></div>`;
    lanes[side] = { side, d, i: 0, n: 0, x: 0, h: 0, cards: {}, ended: false };
  }
  const waitLine = (L) => {
    const feed = $('#feed-' + L.side);
    let w = feed.querySelector('.dl-wait');
    if (L.ended) { w?.remove(); return; }
    if (!w) { w = document.createElement('div'); w.className = 'dl-wait'; }
    feed.appendChild(w);
    w.innerHTML = `<i></i>Agent 运行中 · 证据时间 ${(st.t / 1000).toFixed(1)} s`;
  };
  const add = (L, html, anim) => {
    const feed = $('#feed-' + L.side);
    const div = document.createElement('div');
    div.innerHTML = html.trim();
    const el = div.firstChild;
    if (!anim) el.style.animation = 'none';
    feed.insertBefore(el, feed.querySelector('.dl-wait'));
    return el;
  };
  const kpi = (L) => {
    $(`#k-${L.side}-n`).textContent = L.n;
    const x = $(`#k-${L.side}-x`); x.textContent = L.x; x.className = L.x ? 'red' : '';
    const h = $(`#k-${L.side}-h`); h.textContent = L.h; h.className = L.h ? 'amber' : '';
  };
  const apply = (L, e, anim) => {
    const side = L.side;
    if (e.kind === 'task') {
      add(L, `<div class="ec sys">▶ t = 0 s · 用户下达任务，Agent 开始运行</div>`, anim);
      if (anim) pulse(side, [{ st: 0 }]);
    } else if (e.kind === 'context') {
      add(L, `<div class="ec ctx"><div class="ec-top"><span class="ec-n">⧉</span><span class="ec-op">启动载入</span><span class="ec-tg">${esc(e.source_kind || '')} ${esc(e.uri)}</span></div>${srcRow(e, false)}</div>`, anim);
      if (anim) pulse(side, [{ st: 1, el: ['chip-mcp'] }, { st: 2 }, { st: 3, el: ['sub-fast'] }]);
    } else if (e.kind === 'call') {
      L.n++;
      const hold = isHold(e.verdict), wouldHold = isHold(e.would), danger = side === 'off' && e.executed && wouldHold;
      if (danger) L.x++;
      if (hold) L.h++;
      const fast = e.basis === 'calibrated_model_and_facts';
      const ms = e.latency_ms != null ? `<span class="ec-ms">${e.latency_ms.toFixed(1)} ms</span>` : '';
      const f = e.facts || {};
      const why = (hold || wouldHold) ? `${f.request_tainted ? '<span class="vb would" style="color:#e9d5ff;border-color:rgba(167,139,250,.6)">快镜·请求污染</span>' : ''}${f.directive ? '<span class="vb would" style="color:#fecaca;border-color:rgba(248,113,113,.6)">规则·外部指令</span>' : ''}${f.secret_hit ? '<span class="vb would ask">机密指纹</span>' : ''}${f.hard_policy ? `<span class="vb would block">硬策略</span>` : ''}` : '';
      const verdict = side === 'off' && e.would !== e.verdict
        ? `<span class="vb ${(e.verdict || '').toLowerCase()}${anim ? ' stamp' : ''}">${esc(e.verdict)} ${VZH[e.verdict] || ''}</span><span class="vb would ${(e.would || '').toLowerCase()}">本应 ${esc(e.would)}</span>`
        : `<span class="vb ${(e.verdict || '').toLowerCase()}${anim ? ' stamp' : ''}">${esc(e.verdict || '待裁决')} ${VZH[e.verdict] || ''}</span>`;
      const exec = e.executed ? (danger ? '<span class="ec-x bad">⚠ 已执行（防护关闭）</span>' : '<span class="ec-x ok">已执行</span>')
        : hold ? `<span class="ec-x held">${e.verdict === 'BLOCK' ? '✕ 未执行 · 已阻断' : '‖ 未执行 · 挂起'}</span>` : '<span class="ec-x ok">未执行</span>';
      L.cards[e.call_id] = add(L, `<div class="ec ${danger ? 'danger' : hold ? 'held' : ''}">
        <div class="ec-top"><span class="ec-n">${L.n}</span><span class="ec-op">${esc(e.op)}</span><span class="ec-tg">${esc(e.target)}</span>${e.agent && e.agent !== '主 Agent' ? `<span class="ec-ag">${esc(e.agent)}</span>` : ''}<span class="ec-t">${(e.t / 1000).toFixed(1)}s</span></div>
        ${e.args && e.args !== '{}' ? `<div class="ec-args">${esc(e.args)}</div>` : ''}
        <div class="ec-v">${verdict}<span class="ec-rule">${esc(e.rule_id || '')}</span>${ms}${fast && !why ? '<span class="ec-fast">快镜</span>' : ''}${why}${exec}</div></div>`, anim);
      kpi(L);
      if (anim) {
        const steps = [{ st: 0 }, { st: 1, el: [e.op && e.op.startsWith('mcp') ? 'chip-mcp' : 'chip-hook'] }, { st: 3, el: fast ? ['sub-rule', 'sub-fast'] : ['sub-rule'] }, { st: 4, el: ['pv-' + e.verdict] }];
        if (e.slow_triggered) steps.push({ st: 5, el: ['pn-slow'] });
        pulse(side, steps);
      }
    } else if (e.kind === 'source') {
      const card = L.cards[e.call_id];
      const html = srcRow(e, true);
      if (card) { const d = document.createElement('div'); d.innerHTML = html.trim(); const r = d.firstChild; if (!anim) r.style.animation = 'none'; card.appendChild(r); }
      else add(L, `<div class="ec"><div class="ec-top"><span class="ec-n">↳</span><span class="ec-op">来源</span><span class="ec-tg">${esc(e.uri)}</span></div>${html}</div>`, anim);
      if (anim) pulse(side, [{ st: 1, el: [String(e.source_type || '').startsWith('MCP') ? 'chip-mcp' : 'chip-hook'] }, { st: 2 }, { st: 3, el: ['sub-fast'] }]);
    } else if (e.kind === 'held') {
      const card = L.cards[e.call_id];
      if (card) { const d = document.createElement('div'); d.className = 'ec-hold'; d.textContent = '‖ 挂起等待用户确认 —— 该调用未执行，Agent 本轮停止'; card.appendChild(d); }
      if (anim) pulse(side, [{ st: 4, el: ['pv-ASK'] }]);
    }
    const feed = $('#feed-' + side);
    if (feed) feed.scrollTop = feed.scrollHeight;
  };
  const end = (L, anim) => {
    L.ended = true;
    waitLine(L);
    const box = $('#end-' + L.side), b = endBanner(L.side, L.d);
    box.className = `dl-end show ${b.cls}`;
    if (!anim) box.style.animation = 'none'; else box.style.animation = '';
    box.innerHTML = `<span class="ic">${b.icon}</span><div><b>${esc(b.title)}</b><small>${esc(b.sub)}</small></div>`;
    const kbEl = $(`#k-${L.side}-b`); kbEl.textContent = L.d.result.received_bytes ?? 0; kbEl.className = L.d.result.received_bytes ? 'red' : '';
    if (anim) pulse(L.side, [{ st: 5 }]);
    // Bring the decisive card (the action that leaked, or the one that was held) into view.
    const feed = $('#feed-' + L.side), key = [...feed.querySelectorAll('.ec.danger, .ec.held')].pop();
    if (key) feed.scrollTo({ top: key.offsetTop - feed.offsetTop - 8, behavior: anim ? 'smooth' : 'instant' });
  };
  const advance = (anim) => {
    for (const side of ['off', 'on']) {
      const L = lanes[side], ev = L.d.events;
      while (L.i < ev.length && ev[L.i].t <= st.t) apply(L, ev[L.i++], anim);
      if (!L.ended && st.t >= (L.d.end_t || 0) && L.i >= ev.length) end(L, anim);
      else if (!L.ended) waitLine(L);
    }
    $('#duel-t').textContent = (st.t / 1000).toFixed(1);
    $('#duel-ph').style.left = pos(st.t);
    $$('#duel-track .tk').forEach((k) => k.classList.toggle('seen', +k.dataset.t <= st.t));
  };
  const btn = () => { const b = $('#duel-play'); if (b) b.textContent = st.playing ? '⏸ 暂停' : st.t >= tmax ? '▶ 重新播放' : st.t > 0 ? '▶ 继续' : '▶ 播放'; };
  const frame = (now) => {
    if (!st.playing || !$('#duel-t')) return;
    const dt = Math.min(120, now - st.last); st.last = now;
    st.t = Math.min(tmax, st.t + dt * scr.speed);
    advance(true);
    if (st.t >= tmax) { st.playing = false; btn(); return; }
    st.raf = requestAnimationFrame(frame);
  };
  const reset = () => {
    for (const side of ['off', 'on']) {
      const L = lanes[side];
      Object.assign(L, { i: 0, n: 0, x: 0, h: 0, cards: {}, ended: false });
      $('#feed-' + side).innerHTML = '';
      const box = $('#end-' + side); box.className = 'dl-end'; box.innerHTML = '';
      const k = $(`#k-${side}-b`); k.textContent = '—'; k.className = '';
      kpi(L);
    }
    st.t = 0;
  };
  const api_ = {
    tmax, touched: false,
    get playing() { return st.playing; },
    play() { if (st.t >= tmax) { reset(); advance(false); } st.playing = true; st.last = performance.now(); btn(); st.raf = requestAnimationFrame(frame); },
    pause() { st.playing = false; cancelAnimationFrame(st.raf); btn(); },
    stop() { st.playing = false; cancelAnimationFrame(st.raf); },
    seek(t) { this.stop(); reset(); st.t = Math.max(0, Math.min(tmax, t)); advance(false); btn(); },
  };
  reset(); advance(false); btn();
  return api_;
}

function srcRow(e, withExcerpt) {
  const s = e.s1;
  if (!s) return `<div class="ec-src"><div class="sl">↳ ${e.kind === 'context' ? '' : '返回 '}<b>${esc(e.uri)}</b> · 快镜未判定</div></div>`;
  const p = s.p_request != null ? Math.max(0, Math.min(1, s.p_request)) : null, thr = s.threshold ?? 0.5;
  const req = s.label === 'request';
  return `<div class="ec-src ${req ? 'req' : ''}"><div class="sl">↳ ${e.kind === 'context' ? '' : '返回 '}<b>${esc(e.uri)}</b><span>快镜 S1</span>
      <span class="meter"><span style="width:${p == null ? 0 : (p * 100).toFixed(1)}%"></span><em style="left:${thr * 100}%" title="阈值 ${thr}"></em></span>
      <span class="pv">${esc(S1ZH[s.label] || s.label)} ${p == null ? '' : p.toFixed(2)}</span></div>
    ${req && withExcerpt !== false && e.excerpt ? `<div class="ex">${esc(e.excerpt)}</div>` : ''}</div>`;
}

function endBanner(side, d) {
  const r = d.result || {}, calls = d.events.filter((e) => e.kind === 'call');
  const fmtCall = (c) => `${c.op} ${c.target}`;
  if (r.attack_succeeded) {
    const leaked = calls.filter((c) => c.executed && isHold(c.would));
    const kind = leaked.some((c) => c.op === 'fs.write') ? '敏感写入发生' : leaked.some((c) => c.op === 'net.fetch') ? '数据外发发生' : '越权动作已执行';
    const title = r.received_bytes > 0 ? `攻击得逞：接收端收到 ${r.received_bytes} 字节` : `攻击得逞：${kind}`;
    const sub = leaked.length ? `${leaked.slice(0, 2).map(fmtCall).join('；')} 已执行 —— 内核本应 ${leaked.slice(0, 2).map((c) => `${c.would} · ${c.rule_id}`).join('；')}` : '运行结果判定攻击成功';
    return { cls: 'bad', icon: '!', title, sub: side === 'off' ? sub + '（防护关闭，仅记录）' : sub };
  }
  const held = calls.filter((c) => !c.executed && isHold(c.verdict));
  if (held.length && (r.attack_prevented || r.approval_pending || r.defense_blocked || r.defense_containment === 'held_for_approval')) {
    const c = held[0], f = c.facts || {};
    const cause = f.request_tainted && f.directive ? '规则＋快镜判定请求污染' : f.request_tainted ? '快镜判定请求污染' : f.directive ? '规则抽取到外部指令'
      : f.secret_hit ? '参数含机密指纹' : f.hard_policy ? `命中硬策略 ${f.hard_policy}` : `命中 ${c.rule_id}`;
    const act = c.verdict === 'BLOCK' ? 'BLOCK 阻断' : 'ASK 挂起';
    return { cls: 'good', icon: '✓', title: `已拦截：${cause} → ${act}，${r.received_bytes || 0} 字节外流`,
      sub: `${fmtCall(c)} 未执行 · ${c.rule_id}${c.latency_ms != null ? ` · ${c.latency_ms.toFixed(1)} ms` : ''}${r.task_status === 'pending_user_approval' ? ' · 等待用户确认' : ''}` };
  }
  const [label] = outcomeLabel({ ...d.run, complete: true });
  return { cls: 'neutral', icon: '–', title: `未观察到攻击得逞：${label}`, sub: `接收端 ${r.received_bytes || 0} 字节` };
}

// ---------------- security chain vs raw context ----------------
function cmpPanel(runs, s) {
  const c = s && s.compaction;
  return `
  <section class="sp" id="cmp">
    <div class="sp-h">
      <div><div class="sp-t">安全链 vs 原始上下文 <small>突破长程窗口</small></div>
        <div class="sp-d">每次模型请求的输入随对话不断膨胀；内核裁决只读取增量安全链维护的有界安全状态，不随上下文增长。</div></div>
      <div class="cp-ctl">${runs.length ? `<select id="cmp-run">${runs.map((r) => `<option value="${esc(r.id)}">${esc(r.scenario)} · ${ENV_ZH[r.environment] || r.environment} · ${PROTECT_ZH[r.protection] || r.protection} · ${runTime(r.id)}</option>`).join('')}</select>` : ''}</div>
    </div>
    ${runs.length ? `<div class="cp-legend"><span><i style="background:#ff8a3d"></i>模型输入字节（gateway.jsonl · input_bytes）</span><span><i style="background:#22d3ee"></i>安全状态字节（security_chain.jsonl · 请求时刻的最新状态）</span><span><i style="background:#fff;width:9px;height:9px;transform:rotate(45deg)"></i>内核裁决读取的快照（decisions.jsonl · previous_security_state）</span></div>
    <div class="cp"><div class="cp-chart" id="cmp-chart"></div><div class="cp-side" id="cmp-side"></div></div>`
    : '<div class="scr-note">运行记录中没有可用的网关请求证据（gateway.jsonl）。</div>'}
    ${c ? `<div id="cmp-eval" class="hidden">${esc(JSON.stringify({ runs: c.runs, median: c.median_ratio, max: c.max_ratio }))}</div>` : ''}
  </section>`;
}

function initCompaction(runs) {
  const sel = $('#cmp-run');
  if (!sel) return;
  const pick = scr.cmpRun && runs.some((r) => r.id === scr.cmpRun) ? scr.cmpRun : (runs.find((r) => r.scenario === 'c2-dilution-51') || runs[0]).id;
  sel.value = pick;
  let seen = false, current = null;
  const draw = async (id) => {
    scr.cmpRun = id;
    const d = await api('/api/compaction/' + encodeURIComponent(id)).catch(() => null);
    if (!$('#cmp-chart') || scr.cmpRun !== id) return;
    current = d;
    render(d, seen);
  };
  const render = (d, animate) => {
    const box = $('#cmp-chart');
    if (!d || !d.requests.length) { box.innerHTML = '<div class="scr-note">该运行没有模型请求记录。</div>'; $('#cmp-side').innerHTML = ''; return; }
    box.classList.remove('in');
    box.innerHTML = cmpChart(d);
    $('#cmp-side').innerHTML = cmpSide(d);
    bindCmpHover(box);
    if (animate) requestAnimationFrame(() => requestAnimationFrame(() => box.classList.add('in')));
  };
  sel.addEventListener('change', () => draw(sel.value));
  if ('IntersectionObserver' in window && !REDUCED()) {
    const ob = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { ob.disconnect(); seen = true; $('#cmp-chart')?.classList.add('in'); } }, { threshold: 0.3 });
    ob.observe($('#cmp'));
    onLeave(() => ob.disconnect());
  } else seen = true;
  draw(pick).then(() => { if (seen) $('#cmp-chart')?.classList.add('in'); });
}

function niceStep(maxV, ticks = 5) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(maxV / ticks, 1))));
  for (const m of [1, 2, 2.5, 5, 10]) if (maxV / (m * p) <= ticks) return m * p;
  return 10 * p;
}

function cmpChart(d) {
  const W = 900, H = 340, L = 58, R = 150, T = 30, B = 40, pw = W - L - R, ph = H - T - B;
  const rq = d.requests, n = rq.length;
  const maxV = Math.max(...rq.map((r) => Math.max(r.input_bytes, r.state_bytes || 0)));
  const step = niceStep(maxV), ymax = Math.ceil(maxV / step) * step;
  const x = (i) => L + (n <= 1 ? pw / 2 : ((i - 1) * pw) / (n - 1));
  const y = (v) => T + ph - (v / ymax) * ph;
  const kfmt = (v) => (v === 0 ? '0' : v >= 1000 ? `${+(v / 1000).toFixed(1)}K` : String(v));
  let g = '';
  for (let v = 0; v <= ymax + 1e-6; v += step) g += `<line class="gl" x1="${L}" x2="${L + pw}" y1="${y(v)}" y2="${y(v)}"/><text class="ax" x="${L - 10}" y="${y(v) + 4}" text-anchor="end">${kfmt(v)}</text>`;
  const every = Math.max(1, Math.ceil(n / 8));
  rq.forEach((r) => { if (r.i === 1 || r.i === n || (r.i % every === 0 && n - r.i > every / 2)) g += `<text class="ax" x="${x(r.i)}" y="${T + ph + 18}" text-anchor="middle">#${r.i}</text>`; });
  g += `<text class="axt" x="${L + pw / 2}" y="${H - 2}" text-anchor="middle">模型请求序号（按时间）</text><text class="axt" x="${L - 10}" y="${T - 14}" text-anchor="end">字节</text>`;
  const pts = (key) => rq.filter((r) => r[key] != null).map((r) => `${x(r.i).toFixed(1)},${y(r[key]).toFixed(1)}`);
  const ctx = pts('input_bytes'), stp = pts('state_bytes');
  const area = (p, cls) => (p.length > 1 ? `<path class="fade" fill="url(#${cls})" d="M${p[0].split(',')[0]},${y(0)} L${p.join(' L')} L${p.at(-1).split(',')[0]},${y(0)} Z"/>` : '');
  g += `<defs><linearGradient id="cg-ctx" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff8a3d" stop-opacity=".28"/><stop offset="1" stop-color="#ff8a3d" stop-opacity="0"/></linearGradient>
    <linearGradient id="cg-st" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22d3ee" stop-opacity=".35"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient></defs>`;
  g += area(ctx, 'cg-ctx') + area(stp, 'cg-st');
  if (ctx.length > 1) g += `<polyline class="l-ctx draw" pathLength="1" points="${ctx.join(' ')}"/>`;
  if (stp.length > 1) g += `<polyline class="l-st draw" pathLength="1" points="${stp.join(' ')}"/>`;
  if (ctx.length === 1) g += `<circle cx="${ctx[0].split(',')[0]}" cy="${ctx[0].split(',')[1]}" r="4" fill="#ff8a3d"/>`;
  d.decisions.forEach((m) => {
    const cx = x(Math.max(1, Math.min(n, m.after_request || 1))), cy = y(m.state_bytes);
    g += `<path class="dm fade" d="M${cx},${cy - 6} L${cx + 6},${cy} L${cx},${cy + 6} L${cx - 6},${cy} Z" data-tip="${esc(`内核裁决快照 · ${m.verdict || ''} ${m.rule_id || ''}\n第 ${m.after_request || 0} 次请求之后 · ${(m.t_ms / 1000).toFixed(1)} s\n安全状态 ${m.state_bytes.toLocaleString()} 字节`)}"/>`;
  });
  const last = rq.at(-1), lastSt = [...rq].reverse().find((r) => r.state_bytes != null);
  const xe = x(n);
  let yc = y(last.input_bytes), ys = lastSt ? y(lastSt.state_bytes) : null;
  if (ys != null && ys - yc < 40) yc = ys - 40;
  g += `<g class="fade"><text class="end-v" x="${xe + 26}" y="${yc + 2}" fill="#ffb27a">${kb(last.input_bytes)}</text><text class="end-l" x="${xe + 26}" y="${yc + 17}">原始上下文</text>`;
  if (ys != null) g += `<text class="end-v" x="${xe + 26}" y="${ys + 2}" fill="#67e8f9">${kb(lastSt.state_bytes)}</text><text class="end-l" x="${xe + 26}" y="${ys + 17}">安全状态</text>`;
  if (d.ratio && d.context_max_bytes && d.decision_state_max_bytes) {
    const y1 = y(d.context_max_bytes), y2 = y(d.decision_state_max_bytes), bx = xe + 12;
    g += `<path d="M${bx - 4},${y1} L${bx},${y1} L${bx},${y2} L${bx - 4},${y2}" fill="none" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>`;
    if (y2 - y1 > 90) g += `<text class="ratio" x="${xe + 26}" y="${(y1 + y2) / 2 + 10}">×${d.ratio.toFixed(1)}</text><text class="ratio-l" x="${xe + 26}" y="${(y1 + y2) / 2 + 26}">峰值之比</text>`;
  }
  g += '</g>';
  g += `<line class="xh" id="cmp-xh" x1="0" x2="0" y1="${T}" y2="${T + ph}"/>`;
  const bw = n > 1 ? pw / (n - 1) : pw;
  rq.forEach((r) => {
    g += `<rect class="hit" data-x="${x(r.i)}" x="${x(r.i) - bw / 2}" y="${T}" width="${bw}" height="${ph}" data-tip="${esc(`第 ${r.i} 次模型请求 · ${r.agent || ''} · ${r.t_ms != null ? (r.t_ms / 1000).toFixed(1) + ' s' : ''}\n模型输入 ${r.input_bytes.toLocaleString()} 字节\n安全状态 ${r.state_bytes != null ? r.state_bytes.toLocaleString() + ' 字节' : '—'}`)}"/>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="模型输入字节与安全状态字节随请求变化">${g}</svg>`;
}

function bindCmpHover(box) {
  const xh = $('#cmp-xh', box);
  $$('.hit', box).forEach((r) => {
    r.addEventListener('mouseenter', () => { xh.setAttribute('x1', r.dataset.x); xh.setAttribute('x2', r.dataset.x); xh.style.opacity = 1; });
    r.addEventListener('mouseleave', () => { xh.style.opacity = 0; });
  });
}

function cmpSide(d) {
  const ev = (() => { try { return JSON.parse($('#cmp-eval')?.textContent || 'null'); } catch { return null; } })();
  const first = d.requests[0];
  return `
    <div class="cp-big"><div class="v"><i>×</i>${d.ratio != null ? d.ratio.toFixed(1) : '—'}</div>
      <div class="t">本轮：原始上下文峰值 ÷ 裁决快照峰值</div></div>
    <div class="cp-list"><span class="h">本轮证据 · ${esc(d.scenario || '')}</span>
      <span>模型请求</span><b>${d.requests.length} 次</b>
      <span>模型输入</span><b>${kb(first.input_bytes)} → ${kb(d.context_max_bytes)}</b>
      <span>裁决快照峰值</span><b>${kb(d.decision_state_max_bytes)}</b>
      ${d.chain_state_max_bytes != null ? `<span>安全链状态峰值</span><b>${kb(d.chain_state_max_bytes)}</b>` : ''}
      <span>内核裁决</span><b>${d.decisions.length} 次</b></div>
    ${ev ? `<div class="cp-list"><span class="h">竞赛评测 · ${esc(ev.runs)} 轮样本</span>
      <span>中位压缩比</span><b>×${Number(ev.median).toFixed(1)}</b>
      <span>最大压缩比</span><b>×${Number(ev.max).toFixed(1)}</b></div>` : ''}`;
}

// ---------------- families & three-arm ablation ----------------
function famPanel(s) {
  const fams = (s.families || []).filter((f) => f.off_asr && f.off_asr.d > 0);
  const skipped = (s.families || []).filter((f) => !(f.off_asr && f.off_asr.d > 0)).map((f) => f.label);
  const bar = (o, cls) => { const v = r1(rate(o)); return `<span class="tr"><span class="fl ${cls}" data-w="${v ?? 0}"></span></span><em>${pctTxt(v)} · ${fracTxt(o)}</em>`; };
  return `
  <section class="sp">
    <div class="sp-h"><div><div class="sp-t">攻击家族 · 防护前后 <small>${fams.length} 类</small></div>
      <div class="sp-d">各家族攻击成功率：防护关闭（红）vs 开启（青），分母为模型有效且可判分的攻击运行。</div></div><div class="sp-src">竞赛评测 ${esc(s.cells)} 格</div></div>
    <div class="fam">
      <div class="fam-head"><span>攻击家族</span><span>攻击成功率</span><span style="text-align:right">发起攻击</span></div>
      ${fams.map((f) => `<div class="fam-row">
        <div class="fam-n"><b>${esc(f.label)}</b><small>${esc(f.cells)} 格</small></div>
        <div class="fam-bars"><span>关闭</span>${bar(f.off_asr, 'atk')}<span>开启</span>${bar(f.on_asr, 'def')}</div>
        <div class="fam-c"><b>${f.off_asr_attempted ? esc(f.off_asr_attempted.d) : '—'}</b><small>关闭侧发起攻击轮次</small></div></div>`).join('')}
      ${skipped.length ? `<div class="fam-foot">${esc(skipped.join('、'))}：攻击成功率分母为 0（无可判定攻击格），未列入。</div>` : ''}
    </div>
  </section>`;
}

function ablPanel(s, mode) {
  const arms = (s.three_arm || []).map((a) => ({ ...a, atk: frac(a.attack_success), icp: frac(a.interception), ok: frac(a.normal_done) }));
  const r = (o) => (o && o.d ? o.n / o.d : null);
  const ext = (key, fn) => fn(...arms.map((a) => r(a[key])).filter((v) => v != null));
  const best = { atk: ext('atk', Math.min), icp: ext('icp', Math.max), ok: ext('ok', Math.max) };
  const worst = { atk: ext('atk', Math.max), icp: ext('icp', Math.min), ok: ext('ok', Math.min) };
  const grade = (a, k) => (r(a[k]) === best[k] ? 'good' : r(a[k]) === worst[k] ? 'bad' : '');
  const metric = (a, k, name, color) => `<span>${name}</span><em class="${grade(a, k)}">${fracTxt(a[k])}</em><span class="tr"><span class="fl" style="width:${(r(a[k]) ?? 0) * 100}%;background:${color}"></span></span>`;
  const champions = arms.filter((a) => ['atk', 'icp', 'ok'].every((k) => grade(a, k) === 'good'));
  const tag = (a) => {
    const def = grade(a, 'atk') === 'good', biz = grade(a, 'ok') !== 'bad';
    if (champions.includes(a)) return ['good', '防得住 · 完成率最高'];
    if (def && !biz) return ['mid', '防得住 · 业务受阻'];
    if (!def && biz) return ['mid', '业务可用 · 防不住'];
    return ['mid', '—'];
  };
  const champ = champions.length === 1 ? champions[0] : null;
  const base = champ ? arms.filter((a) => a !== champ && a.ok).sort((a, b) => r(b.ok) - r(a.ok))[0] : null;
  const delta = champ && base ? `<div class="ab-delta"><span class="h">${esc(base.arm)} → ${esc(champ.arm)}</span>
    <span>攻击成功 <b>${fracTxt(base.atk)}</b><i>→</i><b class="g">${fracTxt(champ.atk)}</b></span>
    <span>拦截 <b>${fracTxt(base.icp)}</b><i>→</i><b class="g">${fracTxt(champ.icp)}</b></span>
    <span>正常完成 <b>${fracTxt(base.ok)}</b><i>→</i><b class="g">${fracTxt(champ.ok)}</b></span></div>` : '';
  const modes = Object.entries(s.ablation || {});
  const sameBenign = modes.length && modes.every(([, v]) => JSON.stringify(v.benign_hold) === JSON.stringify(modes[0][1].benign_hold));
  const cOn = s.clean_off_done, cOnP = s.clean_on_done;
  return `
  <section class="sp">
    <div class="sp-h"><div><div class="sp-t">三臂消融 <small>快镜的价值</small></div>
      <div class="sp-d">${champions.length === 1 ? `只有 ${esc(champions[0].arm)} 臂在攻击成功、拦截、正常完成三项上同时最优。` : '三种污染判定口径的对照。'}</div></div><div class="sp-src">竞赛评测</div></div>
    <div class="ab">${arms.map((a) => { const [tc, tt] = tag(a); return `<div class="ab-arm ${champions.includes(a) ? 'best' : ''}">
      <div class="ab-k"><b>${esc(a.arm)}</b><span>${esc(a.label)}</span></div>
      <div class="ab-m">${metric(a, 'atk', '攻击成功', 'linear-gradient(90deg,#9f1239,#ff4d61)')}${metric(a, 'icp', '拦截', 'linear-gradient(90deg,#0e7490,#22d3ee)')}${metric(a, 'ok', '正常完成', 'linear-gradient(90deg,#047857,#34d399)')}</div>
      <div class="ab-tag ${tc}">${tt}</div></div>`; }).join('')}</div>
    ${delta}
    <div class="ab-extra">
      ${modes.length ? `<div><div class="h">决策模式对照 · 拦截率</div>${modes.map(([k, v]) => `<div class="r"><span class="mono">${esc(k)}${k === mode ? ' <span style="color:var(--s-cyan)">（当前）</span>' : ''}</span><b>${fracTxt(v.interception)}</b></div>`).join('')}
        ${sameBenign ? `<div class="r"><span>良性误挂起（三种模式）</span><b>${fracTxt(modes[0][1].benign_hold)}</b></div>` : ''}</div>` : ''}
      ${cOn && cOnP ? `<div><div class="h">业务连续性 · 正常任务完成</div>
        <div class="big"><span style="color:#cbd5f5">${pctTxt(r1(rate(cOn)))}</span><i>→</i><span style="color:#5eead4">${pctTxt(r1(rate(cOnP)))}</span></div>
        <div class="r"><span>关闭 → 开启</span><b>${fracTxt(cOn)} → ${fracTxt(cOnP)}</b></div></div>` : ''}
    </div>
  </section>`;
}
