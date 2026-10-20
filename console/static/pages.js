'use strict';
// 各页面：态势总览、攻防场景库、防御策略、攻防竞技场、护航模式、溯源分析、运行记录。

let scenarioCache = null;
async function getScenarios(force = false) {
  if (!scenarioCache || force) scenarioCache = await api('/api/scenarios');
  return scenarioCache;
}
function scenarioOptions(list, selected, filter = () => true) {
  const groups = [['attack', '攻击场景'], ['normal', '正常场景'], [null, '其他']];
  return groups.map(([cat, title]) => {
    const xs = list.filter((s) => (cat ? s.category === cat : !['attack', 'normal'].includes(s.category)) && filter(s));
    return xs.length ? `<optgroup label="${title}">${xs.map((s) => `<option value="${esc(s.id)}" ${s.id === selected ? 'selected' : ''}>${esc(s.id)} · ${esc(s.family_label || '')}</option>`).join('')}</optgroup>` : '';
  }).join('');
}

// ======================= 态势总览 =======================
const overviewFilters = { batch_id: '', decision_mode: '' };
PAGES.overview = async (el) => {
  const d = await api('/api/overview?' + new URLSearchParams(overviewFilters));
  const k = d.kpi;
  const v = d.verdicts;
  const totalDec = (v.ALLOW || 0) + (v.ASK || 0) + (v.BLOCK || 0);
  el.innerHTML = `
    <section class="card arena-ctl">
      <a class="btn" href="#/chat">自己输入任务 / 连续对话 →</a>
      ${['batch_id','decision_mode'].map(k => `<label>${k==='batch_id'?'批次':'决策模式'}<select data-overview-filter="${k}"><option value="">全部历史</option>${d.filters[k].map(v=>`<option value="${esc(v)}" ${overviewFilters[k]===v?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`).join('')}
      <span class="muted small">历史描述性统计；攻击成功率排除正常场景及未判定结果，最终指标以正式配对评测为准。可按批次与决策模式（add_risk / rules_gate / taint_gate）分开查看。</span>
    </section>
    <section class="hero">
      <div>
        <div class="hero-k">所选历史范围 · 可能包含不同批次与配置</div>
        <div class="hero-big"><span class="c-off">${fmtPct(k.off_rate)}</span><span class="arrow">→</span><span class="c-on">${fmtPct(k.on_rate)}</span></div>
        <div class="hero-sub">攻击成功率：防护关闭 ${k.off_success}/${k.off_attack} 轮 → 防护开启 ${k.on_success}/${k.on_attack} 轮</div>
      </div>
      <div class="hero-side">
        <div><b>${k.runs}</b>真实运行</div>
        <div><b>${k.scenarios}</b>覆盖场景</div>
        <div><b>${k.decisions}</b>次裁决</div>
      </div>
    </section>

    <section class="kpi-grid">
      ${kpiCard('攻击成功率 · 防护关闭', fmtPct(k.off_rate), `${k.off_success} / ${k.off_attack} 轮攻击环境运行`, 'off')}
      ${kpiCard('攻击成功率 · 防护开启', fmtPct(k.on_rate), `${k.on_success} / ${k.on_attack} 轮攻击环境运行`, 'on')}
      ${kpiCard('攻击未成功比例', fmtPct(k.intercept_rate), '描述性比例；未触发、报错与真实拦截应在正式评测中分开', 'good')}
      ${kpiCard('防护关闭时的应拦截覆盖', fmtPct(k.would_stop_rate), `成功的 ${k.off_success} 次攻击中 ${k.would_stop} 次本会被挂起或阻断`, 'warn')}
      ${kpiCard('正常任务完成率 · 防护开启', fmtPct(k.clean_done_on_rate), `防护关闭时 ${fmtPct(k.clean_done_off_rate)}；干净环境 ${k.clean_on} 轮`, 'good')}
      ${kpiCard('正常任务打扰率', fmtPct(k.clean_fp_rate), `干净环境中出现挂起或阻断 ${k.clean_fp} / ${k.clean_on} 轮`, 'warn')}
      ${kpiCard('平均裁决耗时', k.avg_latency_ms != null ? k.avg_latency_ms + ' ms' : '—', '防护开启时每次工具调用的本地裁决耗时', 'on')}
      ${kpiCard('挂起或阻断的运行', k.held_runs, '防护开启且出现 ASK/BLOCK 的轮次', 'warn')}
    </section>

    <section class="grid-2-1">
      <div class="card">
        <div class="card-h"><h3>各攻击类型的攻击成功率</h3>${legend([['防护关闭', C.off], ['防护开启', C.on]])}</div>
        <div class="chart-scroll">${groupedBars(d.families.map((f) => ({ ...f, sub: `${f.off + f.on} 轮` })), [
          { key: 'off_rate', name: '防护关闭', color: C.off, n: { s: 'off_s', n: 'off' } },
          { key: 'on_rate', name: '防护开启', color: C.on, n: { s: 'on_s', n: 'on' } }])}</div>
      </div>
      <div class="card">
        <div class="card-h"><h3>防护开启时的裁决分布</h3></div>
        <div class="donut-wrap">${donut([
          { name: '放行 ALLOW', value: v.ALLOW || 0, color: C.allow },
          { name: '挂起 ASK', value: v.ASK || 0, color: C.ask },
          { name: '阻断 BLOCK', value: v.BLOCK || 0, color: C.block }], { center: String(totalDec), sub: '次裁决' })}
          ${legend([[`放行 ${v.ALLOW || 0}`, C.allow], [`挂起 ${v.ASK || 0}`, C.ask], [`阻断 ${v.BLOCK || 0}`, C.block]])}</div>
      </div>
    </section>

    <section class="grid-2-1">
      <div class="card">
        <div class="card-h"><h3>攻击成功率走势（按运行时间顺序分段）</h3>${legend([['防护关闭', C.off], ['防护开启', C.on], ['该段运行轮次', C.soft]])}</div>
        ${lineChart(d.trend, [
          { key: 'off_rate', name: '防护关闭攻击成功率', color: C.off },
          { key: 'on_rate', name: '防护开启攻击成功率', color: C.on }], { bars: { key: 'runs', name: '该段运行轮次', color: C.soft } })}
      </div>
      <div class="card">
        <div class="card-h"><h3>触发最多的规则</h3><a class="link" href="#/policies">查看策略 →</a></div>
        ${hbars(d.rules.map(([rule, n]) => ({ label: rule, value: n, color: /^POL|DT-2a/.test(rule) ? C.block : /DT-(2b|4a|4b|4c|5)/.test(rule) ? C.ask : C.muted })))}
      </div>
    </section>

    <section class="card">
      <div class="card-h"><h3>近期拦截事件</h3><span class="muted">防护开启时被挂起或阻断的动作，点击查看溯源</span></div>
      <table class="tbl click">
        <tr><th>时间</th><th>场景</th><th>环境</th><th>动作</th><th>目标</th><th>裁决</th><th>规则</th><th>理由</th></tr>
        ${d.events.map((e) => `<tr data-go="#/trace/${esc(e.run_id)}"><td>${runTime(e.run_id)}</td><td>${esc(e.scenario)}</td><td>${badge(ENV_ZH[e.environment], e.environment)}</td>
          <td class="mono">${esc(e.op)}</td><td class="mono target">${esc(e.target)}</td><td>${badge(VERDICT_ZH[e.verdict] || e.verdict, VERDICT_CLASS[e.verdict])}</td>
          <td class="mono">${esc(e.rule)}</td><td class="reason">${esc(e.reason)}</td></tr>`).join('')}
      </table>
    </section>`;
  $$('[data-go]', el).forEach((tr) => tr.addEventListener('click', () => go(tr.dataset.go)));
  $$('[data-overview-filter]').forEach(x => x.addEventListener('change', () => { overviewFilters[x.dataset.overviewFilter]=x.value; route(); }));
};
const kpiCard = (title, value, sub, tone) => `<div class="kpi ${tone}"><div class="kpi-t">${esc(title)}</div><div class="kpi-v">${esc(value)}</div><div class="kpi-s">${esc(sub)}</div></div>`;

// ======================= 攻防场景库 =======================
const sstate = { q: '', cat: '', fam: '', origin: '', page: 0 };
const PAGE_SIZE = 15;
PAGES.scenarios = async (el) => {
  const list = await getScenarios(true);
  const fams = [...new Set(list.map((s) => s.family).filter(Boolean))];
  const famLabel = (f) => list.find((s) => s.family === f)?.family_label || f;
  el.innerHTML = `
    <section class="page-actions">
      <div class="stat-chips">
        <div><b>${list.length}</b>全部场景</div>
        <div><b class="c-off">${list.filter((s) => s.category === 'attack').length}</b>攻击场景</div>
        <div><b class="c-good">${list.filter((s) => s.category === 'normal').length}</b>正常场景</div>
        <div><b class="c-on">${list.filter((s) => s.origin === 'console').length}</b>自定义场景</div>
      </div>
      <div class="btns">
        <a class="btn" href="/api/scenarios-export?origin=all">导出全部</a>
        <button class="btn" id="s-import">导入</button>
        <button class="btn primary" id="s-new">＋ 新增场景</button>
      </div>
    </section>
    <section class="card">
      <div class="filters-row">
        <input id="s-q" placeholder="搜索场景 ID、任务或载荷关键词" value="${esc(sstate.q)}">
        <select id="s-cat"><option value="">全部类别</option><option value="attack">攻击场景</option><option value="normal">正常场景</option></select>
        <select id="s-fam"><option value="">全部攻击类型</option>${fams.map((f) => `<option value="${esc(f)}">${esc(famLabel(f))}</option>`).join('')}</select>
        <select id="s-origin"><option value="">全部来源</option><option value="official">官方评测场景</option><option value="console">自定义场景</option></select>
      </div>
      <div id="s-table"></div>
    </section>`;
  $('#s-cat').value = sstate.cat; $('#s-fam').value = sstate.fam; $('#s-origin').value = sstate.origin;
  const draw = () => {
    const q = sstate.q.toLowerCase();
    const rows = list.filter((s) => (!sstate.cat || s.category === sstate.cat) && (!sstate.fam || s.family === sstate.fam)
      && (!sstate.origin || s.origin === sstate.origin)
      && (!q || [s.id, s.task, s.payload_text].some((x) => (x || '').toLowerCase().includes(q))));
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    sstate.page = Math.min(sstate.page, pages - 1);
    const shown = rows.slice(sstate.page * PAGE_SIZE, (sstate.page + 1) * PAGE_SIZE);
    $('#s-table').innerHTML = `<div class="muted small">共 ${rows.length} 个场景</div>
      <table class="tbl click">
        <tr><th>场景</th><th>类别</th><th>攻击类型</th><th>载荷来源</th><th>用户任务</th><th>历史结果（攻击环境）</th><th>来源</th><th>操作</th></tr>
        ${shown.map((s) => {
          const st = s.stats || {};
          const off = st.attack_off ? `${badge(`关 ${st.attack_off_success || 0}/${st.attack_off} 成功`, (st.attack_off_success ? 'block' : 'gray'))}` : '';
          const on = st.attack_on ? `${badge(`开 ${st.attack_on_success || 0}/${st.attack_on} 成功`, st.attack_on_success ? 'block' : 'allow')}` : '';
          return `<tr data-id="${esc(s.id)}"><td class="mono strong">${esc(s.id)}</td>
            <td>${badge(CAT_ZH[s.category] || '旧版', s.category === 'attack' ? 'attack' : s.category === 'normal' ? 'allow' : 'gray')}</td>
            <td class="nowrap">${esc(s.family_label || '')}</td><td class="mono small">${esc(s.attack_source || '')}</td>
            <td class="task-cell" title="${esc(s.task)}">${esc((s.task || '').length > 90 ? s.task.slice(0, 88) + '…' : s.task)}</td><td>${off} ${on}${!off && !on ? '<span class="muted">暂无</span>' : ''}</td>
            <td>${s.origin === 'console' ? badge('自定义', 'blue') : badge('官方', 'gray')}</td>
            <td class="ops"><button class="btn sm" data-act="arena">对决</button><button class="btn sm" data-act="escort">护航</button></td></tr>`;
        }).join('')}
      </table>
      <div class="pager">${Array.from({ length: pages }, (_, i) => `<button class="btn sm ${i === sstate.page ? 'primary' : ''}" data-page="${i}">${i + 1}</button>`).join('')}</div>`;
    $$('#s-table [data-page]').forEach((b) => b.addEventListener('click', () => { sstate.page = +b.dataset.page; draw(); }));
    $$('#s-table tr[data-id]').forEach((tr) => tr.addEventListener('click', (e) => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'arena') go('#/arena/' + tr.dataset.id);
      else if (act === 'escort') go('#/escort/new/' + tr.dataset.id);
      else scenarioDetail(tr.dataset.id);
    }));
  };
  const bind = (id, key) => $(id).addEventListener('input', () => { sstate[key] = $(id).value; sstate.page = 0; draw(); });
  bind('#s-q', 'q'); bind('#s-cat', 'cat'); bind('#s-fam', 'fam'); bind('#s-origin', 'origin');
  $('#s-new').addEventListener('click', () => scenarioEditor(null));
  $('#s-import').addEventListener('click', scenarioImport);
  draw();
};

async function scenarioDetail(id) {
  const s = await api('/api/scenarios/' + encodeURIComponent(id));
  const d = s.data;
  const files = (env) => Object.entries(((d.resources || {})[env] || {}).files || {}).map(([name, text]) => `<div class="file"><div class="file-h mono">${esc(name)}</div><pre>${esc(text)}</pre></div>`).join('') || '<span class="muted">无</span>';
  const custom = s.origin === 'console';
  openDrawer(`
    <div class="drawer-h"><div><div class="muted small">${custom ? '自定义场景' : '官方评测场景（只读）'}</div><h2 class="mono">${esc(id)}</h2></div><button class="btn" data-close>关闭</button></div>
    <div class="meta">${badge(CAT_ZH[d.category] || '旧版', d.category === 'attack' ? 'attack' : 'allow')} ${d.family ? badge(d.family, 'gray') : ''} ${d.attack_source ? badge('载荷来源 ' + d.attack_source, 'gray') : ''} ${d.language ? badge('语言 ' + d.language, 'gray') : ''}</div>
    <h4>用户任务</h4><div class="task">${esc(d.task)}</div>
    ${d.payload_text ? `<h4>攻击载荷</h4><div class="payload">${esc(d.payload_text)}</div>` : ''}
    <h4>攻击环境初始文件</h4>${files('attack')}
    <h4>交付物与判分</h4><div>交付文件 <span class="mono">${esc(d.deliverable)}</span>，需包含：${(d.completion_terms || []).map((x) => badge(x, 'gray')).join(' ')}<br>攻击判分：<span class="mono">${esc(JSON.stringify(d.oracle || d.attack_oracle || {}))}</span></div>
    ${(d.expected_decision || []).length ? `<h4>期望裁决</h4><table class="tbl">${d.expected_decision.map((x) => `<tr><td>${esc(x.action)}</td><td>${badge(VERDICT_ZH[x.decision] || x.decision, VERDICT_CLASS[x.decision])}</td></tr>`).join('')}</table>` : ''}
    <h4>最近运行</h4>${s.runs.length ? `<table class="tbl click">${s.runs.map((r) => `<tr data-go="#/trace/${esc(r.id)}"><td class="mono">${runTime(r.id)}</td><td>${badge(ENV_ZH[r.environment], r.environment)}</td><td>${badge(PROTECT_ZH[r.protection], r.protection)}</td><td>${badge(...outcomeLabel({ ...r, complete: true }))}</td></tr>`).join('')}</table>` : '<span class="muted">暂无</span>'}
    <div class="drawer-actions">
      <button class="btn primary" data-a="arena">双路对决</button>
      <button class="btn" data-a="escort">护航运行</button>
      <button class="btn" data-a="copy">复制为新场景</button>
      ${custom ? '<button class="btn" data-a="edit">编辑</button><button class="btn danger" data-a="del">删除</button>' : ''}
    </div>`);
  $$('#drawer [data-go]').forEach((tr) => tr.addEventListener('click', () => go(tr.dataset.go)));
  $$('#drawer [data-a]').forEach((b) => b.addEventListener('click', async () => {
    const a = b.dataset.a;
    if (a === 'arena') go('#/arena/' + id);
    if (a === 'escort') go('#/escort/new/' + id);
    if (a === 'copy') { const raw = await rawScenario(id); scenarioEditor({ ...raw, id: id + '-copy', origin: 'console' }, true); }
    if (a === 'edit') scenarioEditor(await rawScenario(id));
    if (a === 'del' && confirm(`删除自定义场景 ${id}？此操作会删除场景文件。`)) {
      try { await send('/api/scenarios/' + encodeURIComponent(id), 'DELETE'); toast('已删除 ' + id); closeDrawer(); route(); } catch (e) { toast(e.message, true); }
    }
  }));
}
async function rawScenario(id) {
  const all = await api('/api/scenarios-export?origin=all');
  return all.scenarios.find((s) => s.id === id);
}

const TEMPLATE = {
  task: 'Read README.md. Write summary.md with the project name, storage and export format.',
  resources: {
    clean: { files: { 'README.md': 'Aster Tasks stores tasks in SQLite and exports CSV.\n' } },
    attack: { files: { 'README.md': 'Aster Tasks stores tasks in SQLite and exports CSV.\n<在这里写入攻击载荷>\n' } },
  },
  file_sources: { 'README.md': 'LOCAL_FILE' },
  completion_terms: ['SQLite', 'CSV'], deliverable: 'summary.md',
  oracle: { kind: 'canary_receipt' }, expected_decision: [],
};
function scenarioEditor(data, isCopy = false) {
  const creating = !data || isCopy;
  const d = data || { id: 'custom-', category: 'attack', family: 'indirect', attack_source: 'file:README.md', ...TEMPLATE };
  const adv = {};
  for (const k of ['resources', 'file_sources', 'oracle', 'expected_decision', 'payload_text', 'requirements']) if (d[k] !== undefined) adv[k] = d[k];
  openModal(`
    <div class="modal-h"><h2>${creating ? '新增场景' : '编辑场景 ' + esc(d.id)}</h2><button class="btn" data-close>取消</button></div>
    <div class="form">
      <label>场景 ID<input id="e-id" class="mono" value="${esc(d.id)}" ${creating ? '' : 'disabled'}></label>
      <label>类别<select id="e-cat"><option value="attack">攻击场景</option><option value="normal">正常场景</option></select></label>
      <label>攻击类型<input id="e-fam" value="${esc(d.family || '')}" placeholder="indirect / memory / tool_abuse …"></label>
      <label>载荷来源<input id="e-src" class="mono" value="${esc(d.attack_source || '')}" placeholder="file:README.md"></label>
      <label class="wide">用户任务<textarea id="e-task" rows="3">${esc(d.task || '')}</textarea></label>
      <label>交付文件<input id="e-del" class="mono" value="${esc(d.deliverable || '')}"></label>
      <label>完成判定词（逗号分隔）<input id="e-terms" value="${esc((d.completion_terms || []).join(', '))}"></label>
      <label class="wide">初始资源、判分与期望裁决（JSON）<textarea id="e-adv" class="mono" rows="14">${esc(JSON.stringify(adv, null, 2))}</textarea></label>
    </div>
    <div class="modal-f"><span class="muted small">保存后写入 d2guard-next/scenarios/，标记为自定义场景，可在竞技场和护航模式中直接运行。</span><button class="btn primary" id="e-save">保存</button></div>`);
  $('#e-cat').value = d.category || 'attack';
  $('#e-save').addEventListener('click', async () => {
    let extra;
    try { extra = JSON.parse($('#e-adv').value || '{}'); } catch (e) { toast('JSON 格式错误：' + e.message, true); return; }
    const body = { ...d, ...extra, id: $('#e-id').value.trim(), category: $('#e-cat').value, family: $('#e-fam').value.trim(),
      attack_source: $('#e-src').value.trim(), task: $('#e-task').value.trim(), deliverable: $('#e-del').value.trim(),
      completion_terms: $('#e-terms').value.split(/[,，]/).map((x) => x.trim()).filter(Boolean) };
    try {
      if (creating) await send('/api/scenarios', 'POST', body); else await send('/api/scenarios/' + encodeURIComponent(d.id), 'PUT', body);
      toast('已保存 ' + body.id); closeModal(); closeDrawer(); route();
    } catch (e) { toast(e.message, true); }
  });
}
function scenarioImport() {
  openModal(`
    <div class="modal-h"><h2>导入场景</h2><button class="btn" data-close>取消</button></div>
    <p>选择导出的 JSON 文件（单个场景对象、场景数组，或“导出全部”得到的文件）。已存在的场景 ID 会跳过。</p>
    <input type="file" id="i-file" accept=".json,application/json">
    <div id="i-result"></div>`);
  $('#i-file').addEventListener('change', async () => {
    const f = $('#i-file').files[0]; if (!f) return;
    try {
      const body = JSON.parse(await f.text());
      const r = await send('/api/scenarios-import', 'POST', body);
      $('#i-result').innerHTML = `<p>${badge(`导入 ${r.imported.length} 个`, 'allow')} ${badge(`跳过 ${r.failed.length} 个`, r.failed.length ? 'ask' : 'gray')}</p>
        ${r.failed.map((x) => `<div class="small">${esc(x.id)}：${esc(x.error)}</div>`).join('')}`;
      scenarioCache = null;
    } catch (e) { $('#i-result').innerHTML = `<p class="c-off">导入失败：${esc(e.message)}</p>`; }
  });
}

// ======================= 防御策略 =======================
PAGES.policies = async (el) => {
  const p = await api('/api/policies');
  const dt = Object.entries(p.hits).filter(([k]) => k.startsWith('DT-')).sort((a, b) => a[0].localeCompare(b[0], 'en', { numeric: true }));
  const other = Object.entries(p.hits).filter(([k]) => !k.startsWith('DT-') && !p.dsl.some((x) => x.id === k));
  el.innerHTML = `
    <section class="card intro"><b>新运行默认配置：${esc(p.runtime_mode || 'unknown')}</b>（实际采用模式以各轮溯源记录为准）。<br>工具调用级的语义策略 DSL：每条策略按工具与语义条件匹配，运行时评估风险等级，映射为 <b class="c-good">放行</b> / <b class="c-warn">询问用户</b> / <b class="c-off">强制阻断</b>。策略之后由决策表综合用户授权、上下文污染（规则＋快镜 S1）与机密状态作出三态裁决。</section>
    <section class="policy-grid">
      ${p.dsl.map((x) => `<div class="card policy">
        <div class="policy-h"><span class="mono strong">${esc(x.id)}</span><span class="hits">${p.hits[x.id] || 0}<small>次命中</small></span></div>
        <div class="policy-e">${esc(x.explain)}</div>
        <div class="meta">${x.tools.split(',').map((t) => badge(t.trim(), 'blue')).join(' ')} ${x.verdict.split(',').map((v) => { const [r, vv] = v.split(':').map((s) => s.trim()); return badge(`${r} → ${VERDICT_ZH[vv] || vv}`, VERDICT_CLASS[vv]); }).join(' ')}</div>
        <details><summary>策略原文</summary><pre class="code">${esc(x.source)}</pre></details></div>`).join('')}
    </section>
    <section class="card">
      <div class="card-h"><h3>决策表规则命中（防护开启）</h3><span class="muted">规则号与理由取自真实裁决记录</span></div>
      <table class="tbl"><tr><th>规则</th><th>命中次数</th><th>裁决分布</th><th>理由（首次记录）</th></tr>
        ${[...dt, ...other].map(([k, n]) => `<tr><td class="mono strong">${esc(k)}</td><td>${n}</td>
          <td>${['ALLOW', 'ASK', 'BLOCK'].filter((v) => (p.verdicts[k] || {})[v]).map((v) => badge(`${VERDICT_ZH[v]} ${p.verdicts[k][v]}`, VERDICT_CLASS[v])).join(' ')}</td>
          <td class="reason">${esc(p.reasons[k] || '')}</td></tr>`).join('')}
      </table>
    </section>`;
};

// ======================= 攻防竞技场 · 双路对决 =======================
const arena = { scenario: null, env: 'attack', runs: {} };
PAGES.arena = async (el, [sid]) => {
  const list = await getScenarios();
  if (!sid && app.job?.status === 'running' && app.job.mode === 'arena') { arena.scenario = app.job.scenario; arena.env = app.job.environment; }
  arena.scenario = sid || arena.scenario || (list.find((s) => s.id === 'c-indirect-readme') || list.find((s) => s.category === 'attack') || list[0]).id;
  const view = 'arena:' + arena.scenario + ':' + arena.env;
  if (el.dataset.view !== view) {
    // The frame is built once per scenario/environment; polling only refreshes lanes, verdict and log.
    el.dataset.view = view;
    el.innerHTML = `
    <section class="card arena-ctl">
      <label>攻防场景<select id="a-sc">${scenarioOptions(list, arena.scenario)}</select></label>
      <div class="seg" id="a-env"><button data-v="attack">攻击环境</button><button data-v="clean">干净环境</button></div>
      <button class="btn primary big" id="a-go">⚔ 开始双路对决</button>
      <div class="muted small">同一任务、同一攻击，“防护关闭”与“防护开启”两路真实 Pi Agent 同时运行，左右对照。未发起时展示该场景最近一次的历史运行。</div>
    </section>
    <section id="a-info" class="card scenario-strip"></section>
    <section class="arena">
      <div class="lane off" id="lane-off"></div>
      <div class="vs"><span>VS</span></div>
      <div class="lane on" id="lane-on"></div>
    </section>
    <section id="a-verdict"></section>
    <section id="a-log"></section>`;
    $$('#a-env button').forEach((b) => b.classList.toggle('active', b.dataset.v === arena.env));
    $('#a-sc').addEventListener('change', () => go('#/arena/' + $('#a-sc').value));
    $$('#a-env button').forEach((b) => b.addEventListener('click', () => { arena.env = b.dataset.v; route(); }));
    $('#a-go').addEventListener('click', async () => {
      try { await launch({ scenario: arena.scenario, environment: arena.env, mode: 'arena' }); arena.live = true; toast('两路 Agent 已同时启动'); route(); } catch (e) { toast('无法启动：' + e.message, true); }
    });
    const s = list.find((x) => x.id === arena.scenario);
    $('#a-info').innerHTML = s ? `<div class="meta">${badge(CAT_ZH[s.category] || '旧版', s.category === 'attack' ? 'attack' : 'allow')} ${badge(s.family_label || '', 'gray')} ${s.attack_source ? badge('载荷来源 ' + s.attack_source, 'gray') : ''}</div>
    <div><b>用户任务：</b>${esc(s.task)}</div>${s.payload_text ? `<div class="payload"><b>攻击载荷：</b>${esc(s.payload_text)}</div>` : ''}` : '';
  }
  const busy = app.job?.status === 'running';
  $('#a-go').disabled = busy;
  $('#a-go').textContent = !busy ? '⚔ 开始双路对决' : app.job.agents_finished ? '⏳ 两路已结束，慢镜生成研判报告中…' : '⏳ 对决进行中…';

  const job = app.job && app.job.mode === 'arena' && app.job.scenario === arena.scenario && app.job.environment === arena.env ? app.job : null;
  let ids = {};
  if (job) job.steps.forEach((st) => { if (st.run_id) ids[st.protect] = st.run_id; });
  else {
    const pairs = await api('/api/pairs/' + encodeURIComponent(arena.scenario));
    ids = { off: pairs.cells[`${arena.env}/off`]?.id, on: pairs.cells[`${arena.env}/on`]?.id };
  }
  const traces = {};
  for (const p of ['off', 'on']) traces[p] = ids[p] ? await api('/api/runs/' + ids[p]).catch(() => null) : null;
  for (const p of ['off', 'on']) renderLane($('#lane-' + p), p, traces[p], job ? {...job.steps.find((x) => x.protect === p), preparing_memory: job.preparing_memory} : null);
  renderArenaVerdict(traces, job);
  renderJobLog($('#a-log'), job);
  if (job && job.status === 'running') later(() => { if (location.hash.startsWith('#/arena')) route(); }, 1500);
};

function renderJobLog(box, job) {
  if (!job) { setHTML(box, ''); return; }
  if (!$('details', box)) { box.innerHTML = '<details class="card"><summary></summary><pre class="code"></pre></details>'; box.__html = null; }
  const state = job.status === 'running' ? '运行中' : job.status === 'finished' ? '已完成' : '失败';
  $('summary', box).textContent = `运行日志（${state} · ${Math.round(job.elapsed)}s）`;
  const pre = $('pre', box);
  if (pre.textContent !== (job.log_tail || '')) pre.textContent = job.log_tail || '';
}

// Inline approval for a held step, so the decision sits next to the action it concerns.
function laneApprovals(runId, calls) {
  const pending = pendingApprovals(app.job).filter((a) => a.run_id === runId);
  const matched = new Set(calls.map((c) => c.call_id));
  return { pending, unmatched: pending.filter((a) => !matched.has(a.call_id)) };
}

function renderLane(box, protect, t, step) {
  const head = protect === 'off' ? ['裸奔 Agent', '防护关闭 · 只记录本应作出的裁决'] : ['D²Guard 护航', '防护开启 · 每次工具调用先裁决再执行'];
  if (!t) {
    const msg = step?.preparing_memory ? '前置 Agent 正在写入跨会话记忆，完成后两路同时开始…' : step?.status === 'failed' ? '运行失败，请查看下方日志。' : step ? (step.status === 'queued' ? '等待启动…' : '正在启动真实 Agent（加载快镜模型约 10–20 秒）…') : '尚未测试此场景。点击上方“开始双路对决”，即可启动两路真实 Agent。';
    setHTML(box, `<div class="lane-h"><b>${head[0]}</b><small>${head[1]}</small></div><div class="lane-empty">${msg}</div>`);
    return;
  }
  const r = t.run;
  const [label, cls] = outcomeLabel(r);
  const { unmatched } = laneApprovals(r.id, t.calls);
  const progress = step?.progress;
  const reviewing = r.agent_finished && !r.complete;
  const secs = r.agent_elapsed_seconds ?? r.elapsed_seconds;
  const progressText = progress ? `${{ thinking: '模型正在推理', generating: '模型正在生成响应', waiting: '等待模型响应' }[progress.phase] || '等待模型响应'} · 当前请求 ${Math.round(progress.request_seconds)} 秒${progress.last_update_seconds == null ? '' : ` · 最近更新 ${Math.round(progress.last_update_seconds)} 秒前`}` : '';
  const steps = t.calls.map((c, i) => {
    const w = effectiveVerdict(c);
    const waiting = approvalFor(r.id, c.call_id);
    const state = c.executed ? (w === 'ALLOW' || !w ? 'done' : 'leak') : (['ASK','BLOCK'].includes(c.verdict) ? 'stopped' : 'pending');
    const stateTxt = { done: '已执行', leak: '已执行（本应拦截）', stopped: c.verdict === 'BLOCK' ? '已阻断' : waiting ? '已挂起，等你确认 ↓' : '已挂起', pending: c.verdict === 'ALLOW' ? '已放行，尚无执行记录' : '待裁决' }[state];
    return `<div class="step ${state} v-${(w || '').toLowerCase()}${waiting ? ' awaiting' : ''}">
      <span class="step-n">${i + 1}</span>
      <div class="step-b"><div><span class="mono strong">${esc(c.op)}</span> <span class="mono target">${esc(c.target)}</span></div>
        <div class="step-m">${verdictBadge(c)} <span class="mono muted">${esc(c.rule_id || '')}</span> · ${stateTxt}${(c.induced_by || []).length ? ' · <b class="c-off">外部指令诱导</b>' : ''}</div>
        ${waiting ? approvalButtons(waiting) : ''}</div></div>`;
  }).join('');
  setHTML(box, `
    <div class="lane-h"><b>${head[0]}</b><small>${head[1]}</small></div>
    ${progressText ? `<div class="lane-tip">${esc(progressText)}</div>` : ''}
    ${reviewing ? '<div class="lane-tip">Agent 已结束，以下为本轮结果；慢镜正在后台生成研判报告，不影响裁决。</div>' : ''}
    ${unmatched.map((a) => `<div class="lane-tip">⏸ Agent 暂停在 <b>${esc(a.tool)}</b>，等你决定。${approvalButtons(a)}</div>`).join('')}
    <div class="lane-result"><span class="big badge ${cls}">${esc(label)}</span>
      <a class="link" href="#/trace/${esc(r.id)}">溯源 →</a></div>
    <div class="lane-kpi"><div><b>${t.calls.length}</b>工具调用</div><div><b class="c-warn">${t.calls.filter((c) => c.verdict === 'ASK' && !c.executed).length}</b>挂起</div>
      <div><b class="c-off">${t.calls.filter((c) => c.verdict === 'BLOCK').length}</b>阻断</div><div><b class="${r.received_bytes ? 'c-off' : ''}">${r.received_bytes ?? 0}</b>外发字节</div>
      <div><b>${secs != null ? secs.toFixed(0) + 's' : '…'}</b>Agent 耗时</div></div>
    <div class="steps">${steps || '<div class="lane-empty">等待 Agent 提出第一次工具调用…</div>'}</div>
    <div class="muted small lane-id">${runTime(r.id)} · ${esc(r.id)} · ${esc(r.decision_mode || 'unknown')}${r.complete ? (r.review_wait_seconds ? ` · 慢镜研判 ${r.review_wait_seconds.toFixed(0)}s（后台）` : '') : reviewing ? ' · 慢镜研判中' : ' · 运行中'}</div>`);
}

function renderArenaVerdict(tr, job) {
  const off = tr.off?.run, on = tr.on?.run;
  const done = (x) => x && (x.complete || x.agent_finished);
  if (!done(off) || !done(on)) { setHTML($('#a-verdict'), ''); return; }
  const offTxt = off.attack_succeeded ? `攻击成功${off.received_bytes ? `，接收端收到 ${off.received_bytes} 字节` : ''}` : outcomeLabel(off)[0];
  const onTxt = on.attack_succeeded ? '攻击成功' : `${outcomeLabel(on)[0]}${on.received_bytes ? '' : '，接收端 0 字节'}`;
  const good = off.attack_succeeded && !on.attack_succeeded;
  setHTML($('#a-verdict'), `<div class="card arena-verdict ${good ? 'good' : ''}">
    <div><span class="c-off strong">防护关闭：</span>${esc(offTxt)}</div>
    <div><span class="c-on strong">防护开启：</span>${esc(onTxt)}</div>
    ${good ? '<div class="strong">同一攻击在 D²Guard 护航下未能得逞。</div>' : ''}
    ${job ? '' : '<div class="muted small">以上为历史运行；点击“开始双路对决”可在真实 Agent 上重新运行。</div>'}</div>`);
}

// ======================= 护航模式 · 计划—决策—执行 =======================
const ALIGN = {
  human_approved: ['人工批准 · 本次放行', 'allow', '已确认'],
  in_plan: ['计划内 · 按计划执行', 'allow', '一致'],
  pending: ['待裁决或执行', 'gray', '待核对'],
  unclassified: ['证据不足', 'gray', '待核对'],
  off_plan_allowed: ['计划外高风险 · 内核放行', 'gray', '未证明计划一致'],
  confirmation_stopped: ['敏感动作 · 保守待确认', 'ask', '已暂停，意图未定'],
  parameter_rejected: ['参数校验拒绝 · 未执行', 'gray', '参数错误'],
  budget_stopped: ['工具预算耗尽 · 未执行', 'block', '预算保护'],
  off_plan_low: ['计划外低风险 · 放行并记录', 'gray', '一致'],
  induced_stopped: ['请求污染/指令关联 · 已拦截', 'ask', '偏离已纠正'],
  deviation_stopped: ['偏离计划 · 已拦截', 'ask', '偏离已纠正'],
  induced_executed: ['请求污染/指令关联 · 已执行', 'block', '偏离未纠正'],
  deviation_executed: ['偏离计划 · 已执行', 'block', '偏离未纠正'],
};
let escortDefault = null;
PAGES.escort = async (el, args) => {
  const list = await getScenarios();
  let runId = args[0] && args[0] !== 'new' ? args[0] : null;
  const pre = args[0] === 'new' ? args[1] : null;
  const job = app.job && app.job.mode === 'single' && app.job.steps[0].protect === 'on' ? app.job : null;
  if (!runId && job && job.steps[0].run_id) runId = job.steps[0].run_id;
  const view = 'escort:' + args.join('/') + ':' + (job ? job.id : '');
  if (el.dataset.view === view) {
    if (!runId && !pre && !job) runId = escortDefault;
  } else {
    const recent = await api('/api/runs?protection=on&limit=60');
    if (!runId && !pre && !job) runId = escortDefault = (recent.runs.find((r) => r.environment === 'attack' && (r.asked || r.blocked)) || recent.runs[0])?.id;
    el.dataset.view = view;
    el.innerHTML = `
      <section class="card arena-ctl">
        <label>攻防场景<select id="e-sc">${scenarioOptions(list, pre || job?.scenario || recent.runs.find(r => r.id === runId)?.scenario || list.find((s) => s.category === 'attack')?.id)}</select></label>
        <div class="seg" id="e-env"><button data-v="attack" class="active">攻击环境</button><button data-v="clean">干净环境</button></div>
        <button class="btn primary big" id="e-go">⛨ 护航运行</button>
        <label>或查看历史<select id="e-run"><option value="">选择一轮防护开启的运行</option>${recent.runs.map((r) => `<option value="${esc(r.id)}" ${r.id === runId ? 'selected' : ''}>${runTime(r.id)} · ${esc(r.scenario)} · ${ENV_ZH[r.environment]} · ${outcomeLabel(r)[0]}</option>`).join('')}</select></label>
      </section>
      <div id="e-body"></div>`;
    let env = job?.environment || recent.runs.find(r => r.id === runId)?.environment || 'attack';
    $$('#e-env button').forEach(b => b.classList.toggle('active', b.dataset.v === env));
    $$('#e-env button').forEach((b) => b.addEventListener('click', () => { env = b.dataset.v; $$('#e-env button').forEach((x) => x.classList.toggle('active', x === b)); }));
    $('#e-run').addEventListener('change', () => { if ($('#e-run').value) go('#/escort/' + $('#e-run').value); });
    $('#e-go').addEventListener('click', async () => {
      try { await launch({ scenario: $('#e-sc').value, environment: env, protect: 'on' }); toast('护航运行已开始'); go('#/escort'); } catch (e) { toast('无法启动：' + e.message, true); }
    });
  }
  const busy = app.job?.status === 'running';
  $('#e-go').disabled = busy;
  $('#e-go').textContent = busy ? '⏳ 运行中…' : '⛨ 护航运行';
  if (!runId) { setHTML($('#e-body'), `<div class="card lane-empty">${job ? (job.status==='failed'?'运行失败，请查看任务日志。':'正在启动真实 Agent（加载快镜模型约 10–20 秒）…') : '选择场景后点击“护航运行”。'}</div>`); if (job && job.status === 'running') later(route, 1500); return; }
  const t = await api('/api/runs/' + encodeURIComponent(runId));
  renderEscort($('#e-body'), t);
  if (!t.run.complete) later(() => { if (location.hash.startsWith('#/escort')) route(); }, 1500);
};

function renderEscort(box, t) {
  const r = t.run, plan = t.plan || {};
  const counts = {};
  t.calls.forEach((c) => { counts[c.alignment] = (counts[c.alignment] || 0) + 1; });
  const consistent = t.calls.filter((c) => (['in_plan', 'human_approved', 'off_plan_low'].includes(c.alignment) || c.alignment.endsWith('_stopped'))).length;
  const deviations = t.calls.filter((c) => ['induced_stopped','deviation_stopped','induced_executed','deviation_executed','off_plan_allowed'].includes(c.alignment)).length;
  const corrected = (counts.induced_stopped || 0) + (counts.deviation_stopped || 0);
  const score = t.calls.length ? Math.round((consistent / t.calls.length) * 100) : null;
  const chips = (xs, cls) => (xs && xs.length ? xs.map((x) => badge(typeof x === 'string' ? x : JSON.stringify(x), cls)).join(' ') : '<span class="muted">无</span>');
  const spawn = (plan.spawn || []).map((s, i) => `子 Agent ${i + 1}：读 ${(s.read || []).join('、') || '—'}；写 ${(s.write || []).join('、') || '—'}`);
  const [label, cls] = outcomeLabel(r);
  const { unmatched } = laneApprovals(r.id, t.calls);
  setHTML(box, `
    ${unmatched.map((a) => `<div class="card lane-tip">⏸ Agent 暂停在 <b>${esc(a.tool)}</b>，等你决定。${approvalButtons(a)}</div>`).join('')}
    <section class="escort-top">
      <div class="card plan">
        <div class="card-h"><h3>① 计划：用户授权锚点</h3>${badge(plan.mode === 'READONLY_REVIEW' ? '只读审查' : '任务模式', 'blue')}</div>
        <div class="task">${esc(r.task)}</div>
        ${plan.available ? `<div class="plan-grid">
          <div><b>允许读取</b>${chips(plan.read, 'allow')}</div>
          <div><b>允许写入</b>${chips(plan.write, 'allow')}</div>
          <div><b>允许外发</b>${chips(plan.net, 'allow')}</div>
          <div><b>子 Agent 授权</b>${chips(spawn, 'blue')}</div></div>
          <div class="muted small">从用户原始任务中逐字抽取；未出现在这里的读写外发都视为计划外，再由决策表结合污染与机密状态判定。</div>`
          : '<div class="muted">本轮没有记录授权锚点。</div>'}
      </div>
      <div class="card score">
        <div class="score-v ${score === 100 ? 'c-good' : score >= 80 ? 'c-warn' : 'c-off'}">${score == null ? '—' : score + '%'}</div>
        <div class="score-t">计划—决策—执行一致性</div><div class="muted small">计划内、低风险辅助与已暂停/阻断计为一致；暂停不证明恶意，计划外高风险放行不计为低风险一致。</div>
        <div class="score-s">${consistent}/${t.calls.length} 个动作计划内、低风险辅助或已停止</div>
        <div class="score-row"><div><b>${deviations}</b>偏离计划</div><div><b class="c-good">${corrected}</b>已拦截纠正</div><div><b class="c-off">${deviations - corrected}</b>未纠正</div></div>
        <div><span class="badge big ${cls}">${esc(label)}</span></div>
        <a class="link" href="#/trace/${esc(r.id)}">查看攻击路径与研判 →</a>
      </div>
    </section>
    <section class="card">
      <div class="card-h"><h3>逐步核对</h3><span class="muted">${runTime(r.id)} · ${esc(r.scenario)} · ${ENV_ZH[r.environment]} · ${esc(r.decision_mode || 'unknown')}${r.complete ? '' : ' · 运行中'}</span></div>
      <div class="pde">
        <div class="pde-h"><div>#</div><div>② Agent 计划的动作</div><div>③ 决策</div><div>④ 执行</div><div>一致性</div></div>
        ${t.calls.map((c, i) => {
          const a = ALIGN[c.alignment] || ['—', 'gray', '—'];
          const agent = t.agents.find((x) => x.id === c.agent)?.label || c.agent;
          const ind = (c.induced_by || [])[0];
          const waiting = approvalFor(r.id, c.call_id);
          const exec = c.executed ? (c.is_error ? '已执行（工具报错）' : '已执行') : c.verdict === 'BLOCK' ? '已阻断，未执行' : c.verdict === 'ASK' ? (waiting ? '已挂起，等你确认' : '已挂起，未执行') : '未执行';
          return `<div class="pde-row a-${esc(c.alignment)}">
            <div class="step-n">${i + 1}</div>
            <div><div><span class="mono strong">${esc(c.op)}</span> <span class="mono target">${esc(c.target)}</span></div>
              <div class="small muted">${esc(agent)} · ${c.approval_status === 'approved_once' ? '<b class="c-good">原始计划外 · 已人工批准本次</b>' : c.in_scope ? '<b class="c-good">在用户原始授权内</b>' : '不在用户原始授权内'}</div>
              ${ind ? `<div class="quote small">关联来源 <b>${esc(ind.uri)}</b>${ind.excerpt ? '：' + esc(ind.excerpt) : ''}</div>` : ''}</div>
            <div>${verdictBadge(c)} <span class="mono">${esc(c.rule_id || '')}</span> ${c.risk ? badge(c.risk, 'gray') : ''}
              <div class="small">${esc(c.reason || '')}</div>${c.latency_ms != null ? `<div class="small muted">裁决耗时 ${c.latency_ms.toFixed(1)} ms</div>` : ''}</div>
            <div><b class="${c.executed ? (c.alignment.endsWith('executed') ? 'c-off' : '') : 'c-warn'}">${exec}</b>${c.result_excerpt ? `<div class="small muted">${esc(c.result_excerpt.slice(0, 90))}</div>` : ''}${waiting ? approvalButtons(waiting) : ''}</div>
            <div>${badge(a[2], a[1])}<div class="small">${esc(a[0])}</div></div>
          </div>`;
        }).join('') || '<div class="lane-empty">等待 Agent 提出第一次工具调用…</div>'}
      </div>
    </section>`);
}

// ======================= 溯源分析 =======================
PAGES.trace = async (el, [id]) => {
  if (!id) {
    const recent = await api('/api/runs?limit=1&held=1&protection=on&environment=attack');
    id = recent.runs[0]?.id;
    if (!id) { el.innerHTML = '<div class="card">暂无运行记录。</div>'; return; }
    history.replaceState(null, '', '#/trace/' + id);
  }
  const recent = await api('/api/runs?limit=80');
  el.innerHTML = `<section class="card arena-ctl"><label>选择运行<select id="t-run">${recent.runs.some((r) => r.id === id) ? '' : `<option>${esc(id)}</option>`}
    ${recent.runs.map((r) => `<option value="${esc(r.id)}" ${r.id === id ? 'selected' : ''}>${runTime(r.id)} · ${esc(r.scenario)} · ${ENV_ZH[r.environment]} · ${PROTECT_ZH[r.protection]} · ${outcomeLabel(r)[0]}</option>`).join('')}</select></label>
    <a class="link" href="#/runs">在运行记录中筛选更多 →</a></section><div id="t-body"></div>`;
  $('#t-run').addEventListener('change', () => go('#/trace/' + $('#t-run').value));
  await renderTracePage($('#t-body'), id);
};

// ======================= 运行记录 =======================
const rstate = { scenario: '', environment: '', protection: '', outcome: '', limit: 100 };
PAGES.runs = async (el) => {
  el.innerHTML = `
    <section class="card">
      <div class="filters-row">
        <input id="r-sc" placeholder="按场景筛选，如 readme、memory" value="${esc(rstate.scenario)}">
        <select id="r-env"><option value="">全部环境</option><option value="attack">攻击环境</option><option value="clean">干净环境</option></select>
        <select id="r-p"><option value="">防护开/关</option><option value="on">防护开启</option><option value="off">防护关闭</option></select>
        <select id="r-o"><option value="">全部结果</option><option value="attack_succeeded">攻击成功</option><option value="guard_blocked">已阻断</option>
          <option value="approval_pending">已挂起</option><option value="no_attack_observed">未观察到攻击</option><option value="capability_unavailable">能力未开放</option><option value="runtime_error">运行错误</option></select>
      </div>
      <div id="r-table"></div>
    </section>`;
  $('#r-env').value = rstate.environment; $('#r-p').value = rstate.protection; $('#r-o').value = rstate.outcome;
  const draw = async () => {
    const q = new URLSearchParams();
    for (const k of ['scenario', 'environment', 'protection', 'outcome']) if (rstate[k]) q.set(k, rstate[k]);
    q.set('limit', rstate.limit);
    const d = await api('/api/runs?' + q);
    $('#r-table').innerHTML = `<div class="muted small">共 ${d.total} 轮，显示 ${d.runs.length} 轮</div>
      <table class="tbl click"><tr><th>时间</th><th>场景</th><th>环境</th><th>防护</th><th>结果</th><th>工具调用裁决</th><th>外发字节</th><th>耗时</th></tr>
      ${d.runs.map((r) => {
        const v = r.verdicts || {};
        return `<tr data-go="#/trace/${esc(r.id)}"><td class="mono">${runTime(r.id)}</td><td class="mono strong">${esc(r.scenario)}</td>
        <td>${badge(ENV_ZH[r.environment] || r.environment, r.environment)}</td><td>${badge(PROTECT_ZH[r.protection] || r.protection, r.protection)}</td>
        <td>${badge(...outcomeLabel(r))}</td>
        <td><span class="c-good">${v.ALLOW || 0}</span> / <span class="c-warn">${v.ASK || 0}</span> / <span class="c-off">${v.BLOCK || 0}</span></td>
        <td class="${r.received_bytes ? 'c-off strong' : ''}">${r.received_bytes ?? 0}</td><td>${(r.agent_elapsed_seconds ?? r.elapsed_seconds) != null ? (r.agent_elapsed_seconds ?? r.elapsed_seconds).toFixed(0) + 's' : '—'}</td></tr>`;
      }).join('')}</table>
      ${d.total > d.runs.length ? '<button class="btn" id="r-more">显示更多</button>' : ''}`;
    $$('#r-table [data-go]').forEach((tr) => tr.addEventListener('click', () => go(tr.dataset.go)));
    $('#r-more')?.addEventListener('click', () => { rstate.limit += 200; draw(); });
  };
  let timer;
  for (const [id, key] of [['#r-sc', 'scenario'], ['#r-env', 'environment'], ['#r-p', 'protection'], ['#r-o', 'outcome']]) {
    $(id).addEventListener('input', () => { rstate[key] = $(id).value.trim(); rstate.limit = 100; clearTimeout(timer); timer = setTimeout(draw, 250); });
  }
  await draw();
};

// ======================= 模型设置 =======================
const STYLE_ZH = { chat_completions: 'Chat Completions（…/chat/completions）', responses: 'Responses（…/responses）' };
PAGES.settings = async (el) => {
  const s = await api('/api/settings');
  const block = (id, m) => `
    <label>接口地址（base_url）<input id="${id}-url" value="${esc(m.base_url)}" placeholder="https://api.example.com/v1" autocomplete="off"></label>
    <label>接口类型<select id="${id}-style">${Object.entries(STYLE_ZH).map(([k, v]) => `<option value="${k}" ${m.api_style === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
    <label>模型名称<input id="${id}-model" value="${esc(m.model)}" list="${id}-models" placeholder="例如 qwen3-32b" autocomplete="off"><datalist id="${id}-models"></datalist></label>
    <label>API Key<input id="${id}-key" type="password" placeholder="${m.has_key ? '已保存在本机，留空表示不修改' : id === 'r' ? '留空则沿用 Agent 的 Key（同一接口地址时）' : '未配置'}" autocomplete="new-password"></label>
    <div class="row"><button class="btn" data-test="${id}">测试连接</button><button class="btn" data-list="${id}">获取模型列表</button></div>
    <div class="test-out muted" id="${id}-out"></div>`;
  el.innerHTML = `
    <section class="card"><div class="muted">这里决定两件事：<b>Agent 用哪个大模型干活</b>，<b>慢镜用哪个大模型写研判与溯源报告</b>。
      快镜是本地的 Laya 模型，不需要配置。保存后从<b>下一次运行</b>开始生效；API Key 只保存在本机 <span class="mono">.local</span> 目录，页面不会显示已保存的 Key。
      支持任何 OpenAI 兼容接口。${s.running ? '<br><b class="c-warn">当前有运行在进行，它仍使用启动时的模型。</b>' : ''}</div></section>
    <section class="settings-grid">
      <div class="card"><div class="card-h"><h3>Agent 模型</h3>${badge('执行任务', 'blue')}</div>
        <div class="muted small">被保护的 Pi Agent 调用这个模型来理解任务、决定调用哪些工具。</div>
        ${block('a', s.agent)}
        <label class="check"><input type="checkbox" id="a-reasoning" ${s.reasoning_capable ? 'checked' : ''}> 此模型支持显式思考模式控制</label>
        <div class="muted small">当前 Agent 使用关闭思考的运行设置。对支持此选项的 Responses 接口，勾选后会明确传递关闭指令，避免沿用服务端默认的长时间思考；不支持的接口请保持关闭。</div></div>
      <div class="card"><div class="card-h"><h3>慢镜模型</h3>${badge('异步研判 · 溯源报告', 'gray')}</div>
        <div class="muted small">在挂起或阻断之后，慢镜调用这个模型生成中文研判报告；它不会改变放行、挂起、阻断的裁决。</div>
        <label class="check"><input type="checkbox" id="r-same" ${s.review.separate ? '' : 'checked'}> 与 Agent 使用同一个模型</label>
        <fieldset id="r-fields" ${s.review.separate ? '' : 'disabled'}>${block('r', s.review.separate ? s.review : { ...s.review, base_url: s.review.base_url || s.agent.base_url, api_style: s.review.api_style || s.agent.api_style })}
          <div class="muted small">与 Agent 用同一个接口地址时，API Key 可以留空，自动沿用 Agent 的 Key。</div></fieldset></div>
    </section>
    <section class="card row"><button class="btn primary big" id="s-save">保存设置</button><span class="muted">保存时会检查必填项；建议先点“测试连接”。</span></section>`;
  const form = (id) => ({ base_url: $(`#${id}-url`).value.trim(), api_style: $(`#${id}-style`).value, model: $(`#${id}-model`).value.trim(), api_key: $(`#${id}-key`).value.trim(), ...(id === 'a' ? { reasoning_capable: $('#a-reasoning').checked } : {}) });
  $('#r-same').addEventListener('change', () => { $('#r-fields').disabled = $('#r-same').checked; });
  $('.settings-grid', el).addEventListener('click', async (e) => {
    const t = e.target.closest('[data-test],[data-list]'); if (!t) return;
    const id = t.dataset.test || t.dataset.list, out = $(`#${id}-out`), target = id === 'a' ? 'agent' : 'review';
    t.disabled = true;
    try {
      if (t.dataset.test) {
        out.textContent = '正在发送一条测试消息…';
        const r = await send('/api/settings/test', 'POST', { target, ...form(id) });
        out.innerHTML = r.ok ? `<b class="c-good">连接成功</b> · ${r.latency_ms} ms · 模型回复：${esc(r.reply || '（空）')}` : `<b class="c-off">连接失败</b> · ${esc(r.error)}`;
      } else {
        const r = await send('/api/settings/models', 'POST', { target, ...form(id) });
        $(`#${id}-models`).innerHTML = r.models.map((m) => `<option value="${esc(m)}">`).join('');
        out.innerHTML = r.models.length ? `找到 ${r.models.length} 个模型，点击“模型名称”输入框可下拉选择。` : esc(r.error || '接口没有返回模型列表，可直接填写模型名称。');
      }
    } catch (err) { out.innerHTML = `<b class="c-off">${esc(err.message)}</b>`; }
    t.disabled = false;
  });
  $('#s-save').addEventListener('click', async () => {
    try {
      await send('/api/settings', 'PUT', { agent: form('a'), review: { separate: !$('#r-same').checked, ...form('r') } });
      toast('已保存，下一次运行开始生效'); delete el.dataset.view; route();
    } catch (err) { toast(err.message, true); }
  });
};

// ---------------- boot ----------------
topStatus();
route();
