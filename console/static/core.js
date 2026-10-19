'use strict';
// 双镜 D²Guard 控制台：公共工具、图表与路由。只展示真实运行留下的证据。

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = async (path, opts) => {
  const r = await fetch(path, { ...opts, signal: opts?.signal || AbortSignal.timeout(20000) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
};
const send = (path, method, body) => api(path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });

const OUTCOME = {
  attack_succeeded: ['攻击成功', 'solid-red'],
  guard_blocked: ['已阻断', 'solid-green'],
  approval_pending: ['已挂起待确认', 'solid-amber'],
  no_attack_observed: ['未观察到攻击', 'gray'],
  capability_unavailable: ['能力未开放', 'gray'],
  runtime_error: ['运行错误', 'gray'],
  running: ['运行中…', 'solid-blue'],
};
const VERDICT_CLASS = { ALLOW: 'allow', ASK: 'ask', BLOCK: 'block' };
const VERDICT_ZH = { ALLOW: '放行', ASK: '挂起', BLOCK: '阻断' };
const ENV_ZH = { attack: '攻击环境', clean: '干净环境' };
const PROTECT_ZH = { on: '防护开启', off: '防护关闭' };
const CAT_ZH = { attack: '攻击场景', normal: '正常场景' };

function outcomeLabel(run) {
  if (!run.complete && run.outcome !== 'runtime_error') return OUTCOME.running;
  if (run.environment === 'clean' && run.outcome === 'no_attack_observed') return [run.task_completed ? '正常完成' : '任务未完成', run.task_completed ? 'solid-green' : 'gray'];
  return OUTCOME[run.outcome] || [run.outcome || '未知', 'gray'];
}
const badge = (text, cls = '') => `<span class="badge ${cls}">${esc(text)}</span>`;
const verdictBadge = (c) => {
  const v = c.verdict, w = c.would_verdict || v;
  if (!v) return badge('待裁决', 'gray');
  if (w !== v) return `${badge(VERDICT_ZH[v] || v, VERDICT_CLASS[v])} ${badge('本应' + (VERDICT_ZH[w] || w), VERDICT_CLASS[w] + ' outline')}`;
  return badge(VERDICT_ZH[v] || v, VERDICT_CLASS[v]);
};
const fmtPct = (v) => (v == null ? '—' : `${v}%`);
const fmtDay = (d) => `${d.slice(4, 6)}-${d.slice(6, 8)}`;
const runTime = (id) => `${id.slice(4, 6)}-${id.slice(6, 8)} ${id.slice(9, 11)}:${id.slice(11, 13)}`;

function toast(text, bad = false) {
  const el = $('#toast');
  el.textContent = text; el.className = 'toast' + (bad ? ' bad' : '');
  clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.add('hidden'), 3500);
}
function openModal(html) { $('#modal-box').innerHTML = html; $('#modal').classList.remove('hidden'); }
function closeModal() { $('#modal').classList.add('hidden'); $('#modal-box').innerHTML = ''; }
function openDrawer(html) { $('#drawer-box').innerHTML = html; $('#drawer').classList.remove('hidden'); }
function closeDrawer() { $('#drawer').classList.add('hidden'); }
$('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal' || e.target.closest('[data-close]')) closeModal(); });
$('#drawer').addEventListener('click', (e) => { if (e.target.id === 'drawer' || e.target.closest('[data-close]')) closeDrawer(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeModal(); closeDrawer(); } });

const tip = $('#tooltip');
function showTip(ev, text) { tip.textContent = text; tip.classList.remove('hidden'); moveTip(ev); }
function moveTip(ev) { tip.style.left = Math.min(ev.clientX + 14, innerWidth - 420) + 'px'; tip.style.top = (ev.clientY + 14) + 'px'; }
function hideTip() { tip.classList.add('hidden'); }
document.addEventListener('mouseover', (e) => {
  const el = e.target.closest('[data-tip]');
  if (el) showTip(e, el.dataset.tip);
});
document.addEventListener('mousemove', (e) => { if (e.target.closest('[data-tip]')) moveTip(e); });
document.addEventListener('mouseout', (e) => { if (e.target.closest('[data-tip]')) hideTip(); });

// ---------------- charts (inline SVG, no external libraries) ----------------
const C = { off: '#e5383b', on: '#1f5eff', held: '#f59f00', allow: '#16a34a', ask: '#f59f00', block: '#e5383b', grid: '#e3e8f0', axis: '#5b6578' };

function groupedBars(items, series, { height = 300, max = 100, unit = '%' } = {}) {
  const W = Math.max(640, items.length * 62 + 60), H = height, L = 46, B = 64, T = 16;
  const ph = H - B - T, gw = (W - L - 10) / Math.max(items.length, 1);
  const bw = Math.min(26, (gw - 14) / series.length);
  const y = (v) => T + ph - (v / max) * ph;
  let g = '';
  for (let t = 0; t <= 4; t++) {
    const v = (max / 4) * t;
    g += `<line x1="${L}" x2="${W - 6}" y1="${y(v)}" y2="${y(v)}" stroke="${C.grid}"/><text class="ax" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${v}${unit}</text>`;
  }
  items.forEach((it, i) => {
    const x0 = L + gw * i + (gw - bw * series.length) / 2;
    series.forEach((s, j) => {
      const v = it[s.key];
      if (v == null) return;
      const h = Math.max(1.5, (v / max) * ph);
      g += `<rect x="${x0 + j * bw}" y="${T + ph - h}" width="${bw - 3}" height="${h}" rx="3" fill="${s.color}" data-tip="${esc(`${it.label} · ${s.name}：${v}${unit}${s.n ? `（${it[s.n.s]}/${it[s.n.n]}）` : ''}`)}"/>`;
      if (h > 16) g += `<text class="bar-v" x="${x0 + j * bw + (bw - 3) / 2}" y="${T + ph - h - 4}" text-anchor="middle">${Math.round(v)}</text>`;
    });
    const label = it.label.length > 5 ? it.label.slice(0, 5) + '…' : it.label;
    g += `<text class="ax-x" x="${L + gw * i + gw / 2}" y="${T + ph + 20}" text-anchor="middle">${esc(label)}</text>`;
    if (it.sub) g += `<text class="ax" x="${L + gw * i + gw / 2}" y="${T + ph + 38}" text-anchor="middle">${esc(it.sub)}</text>`;
  });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMinYMin meet">${g}</svg>`;
}

function lineChart(points, series, { height = 320, max = 100, unit = '%', bars } = {}) {
  const W = 860, H = height, L = 46, R = bars ? 46 : 14, B = 40, T = 16;
  const pw = W - L - R, ph = H - B - T;
  const n = points.length;
  const x = (i) => L + (n <= 1 ? pw / 2 : (pw * i) / (n - 1));
  const y = (v) => T + ph - (v / max) * ph;
  let g = '';
  for (let t = 0; t <= 4; t++) {
    const v = (max / 4) * t;
    g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="${C.grid}"/><text class="ax" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${v}${unit}</text>`;
  }
  if (bars) {
    const bmax = Math.max(1, ...points.map((p) => p[bars.key] || 0));
    const bw = Math.min(30, pw / Math.max(n, 1) * 0.5);
    points.forEach((p, i) => {
      const h = ((p[bars.key] || 0) / bmax) * ph;
      g += `<rect x="${x(i) - bw / 2}" y="${T + ph - h}" width="${bw}" height="${h}" fill="${bars.color}" rx="3" data-tip="${esc(`${p.label} · ${bars.name}：${p[bars.key] || 0}`)}"/>`;
    });
    g += `<text class="ax" x="${W - R + 8}" y="${T + 4}">${bmax}</text><text class="ax" x="${W - R + 8}" y="${T + ph + 4}">0</text>`;
  }
  for (const s of series) {
    const pts = points.map((p, i) => [x(i), p[s.key]]).filter(([, v]) => v != null);
    if (!pts.length) continue;
    g += `<polyline fill="none" stroke="${s.color}" stroke-width="3" points="${pts.map(([a, v]) => `${a},${y(v)}`).join(' ')}"/>`;
    points.forEach((p, i) => {
      if (p[s.key] == null) return;
      g += `<circle cx="${x(i)}" cy="${y(p[s.key])}" r="5" fill="#fff" stroke="${s.color}" stroke-width="3" data-tip="${esc(`${p.label} · ${s.name}：${p[s.key]}${unit}`)}"/>`;
    });
  }
  const every = Math.ceil(n / 6);
  points.forEach((p, i) => { if (i % every === 0) g += `<text class="ax-x" x="${x(i)}" y="${T + ph + 24}" text-anchor="middle">${esc(p.label)}</text>`; });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMinYMin meet">${g}</svg>`;
}

function donut(segs, { size = 200, center = '', sub = '' } = {}) {
  const total = segs.reduce((a, s) => a + s.value, 0) || 1;
  const r = size / 2 - 16, cx = size / 2, cy = size / 2, sw = 30;
  let a0 = -Math.PI / 2, g = '';
  for (const s of segs) {
    if (!s.value) continue;
    const a1 = a0 + (s.value / total) * Math.PI * 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (a) => `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
    const d = s.value === total ? `M${cx},${cy - r} A${r},${r} 0 1 1 ${cx - 0.01},${cy - r}` : `M${p(a0)} A${r},${r} 0 ${large} 1 ${p(a1)}`;
    g += `<path d="${d}" stroke="${s.color}" stroke-width="${sw}" fill="none" data-tip="${esc(`${s.name}：${s.value}（${((s.value / total) * 100).toFixed(1)}%）`)}"/>`;
    a0 = a1;
  }
  g += `<text x="${cx}" y="${cy + 2}" text-anchor="middle" class="donut-c">${esc(center)}</text><text x="${cx}" y="${cy + 24}" text-anchor="middle" class="ax">${esc(sub)}</text>`;
  return `<svg class="donut" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${g}</svg>`;
}

function hbars(rows, { color = C.on, unit = '' } = {}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return `<div class="hbars">${rows.map((r) => `
    <div class="hbar" data-tip="${esc(r.tip || `${r.label}：${r.value}${unit}`)}">
      <span class="hb-l">${esc(r.label)}</span>
      <span class="hb-track"><span class="hb-fill" style="width:${(r.value / max) * 100}%;background:${r.color || color}"></span></span>
      <b>${r.value}${unit}</b></div>`).join('')}</div>`;
}

const legend = (items) => `<div class="legend">${items.map(([name, color]) => `<span><i style="background:${color}"></i>${esc(name)}</span>`).join('')}</div>`;

// ---------------- router ----------------
const PAGES = {};
const TITLES = {
  overview: ['态势', '态势总览'], scenarios: ['管理', '攻防场景库'], policies: ['管理', '防御策略'],
  arena: ['执行', '攻防竞技场 · 双路对决'], escort: ['执行', '护航模式 · 计划—决策—执行'],
  trace: ['分析', '溯源分析'], runs: ['分析', '运行记录'],
};
const app = { timers: [], job: null };
function clearTimers() { app.timers.forEach(clearTimeout); app.timers = []; }
function later(fn, ms) { app.timers.push(setTimeout(fn, ms)); }

async function route() {
  if (app.routing) { app.routeQueued = true; return; }
  app.routing = true;
  const [name = 'overview', ...rest] = location.hash.replace(/^#\/?/, '').split('/');
  const page = PAGES[name] ? name : 'overview';
  clearTimers(); hideTip(); closeDrawer();
  $$('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.page === page));
  $('#crumb').textContent = TITLES[page][0];
  $('#page-title').textContent = TITLES[page][1];
  const el = $('#page');
  const same = app.lastHash === location.hash;
  app.lastHash = location.hash;
  if (!same) { el.innerHTML = '<div class="loading">正在读取运行证据…</div>'; window.scrollTo(0, 0); }
  try { await PAGES[page](el, rest.map(decodeURIComponent)); } catch (e) { el.innerHTML = `<div class="card error">读取失败：${esc(e.message)}</div>`; }
  finally {
    app.routing = false;
    if (app.routeQueued) { app.routeQueued = false; route(); }
  }
}
window.addEventListener('hashchange', route);
const go = (hash) => { if (location.hash === hash) route(); else location.hash = hash; };

// ---------------- top status & running jobs ----------------
async function topStatus() {
  const j = app.job;
  let jobHtml = '';
  if (j && j.status === 'running') {
    const step = j.steps.find((s) => s.status === 'running') || j.steps[0];
    jobHtml = `<a class="chip live" href="${j.mode === 'arena' ? '#/arena' : step.run_id ? '#/trace/' + step.run_id : '#/runs'}">● 运行中：${esc(j.scenario)} · ${PROTECT_ZH[step.protect]}</a>`;
  }
  $('#top-status').innerHTML = `${jobHtml}<span class="chip">宿主 Pi Agent</span><span class="chip">内核 d2v2</span><span class="chip ok">● 本地 127.0.0.1</span>`;
}
async function launch(body) {
  const j = await send('/api/launch', 'POST', body);
  app.job = j; topStatus(); pollJob();
  return j;
}
async function pollJob() {
  if (!app.job) return;
  try { app.job = await api('/api/jobs/' + app.job.id); } catch { setTimeout(pollJob, 3000); return; }
  topStatus();
  document.dispatchEvent(new CustomEvent('job', { detail: app.job }));
  if (app.job.status === 'running') setTimeout(pollJob, 1500);
}

// Job transitions must recover an execution page even after a transient trace request failed.
let lastJobView = '';
document.addEventListener('job', ({detail: job}) => {
  const signature = JSON.stringify([job.id, job.status, job.steps.map(s => [s.status, s.run_id])]);
  if (signature === lastJobView) return;
  lastJobView = signature;
  if (/^#\/(arena|escort)(\/|$)/.test(location.hash)) route();
});
