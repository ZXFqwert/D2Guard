// The server forwards these prompts to one native Pi RPC process.
PAGES.chat = async (el) => {
  if (el.dataset.view !== 'chat') {
    el.dataset.view = 'chat';
    el.innerHTML = `
      <section class="card"><div class="row"><b>与 Pi Agent 对话</b><span id="chat-status" class="muted"></span>
        <button class="btn" id="chat-stop">停止生成</button><button class="btn" id="chat-close">结束会话</button>
        <button class="btn" id="chat-new">新对话</button></div>
        <p class="muted">直接输入任务，完成后可继续追问。Agent 可在本次独立工作区读写文件和执行工具；需要确认的操作会显示审批。</p>
        <div id="chat-runtime" class="small muted"></div></section>
      <section class="card" id="chat-messages" aria-live="polite"><p class="muted">输入你的任务开始对话。</p></section>
      <section class="card"><form id="chat-form">
        <label>你的任务或追问<textarea id="chat-input" rows="4" maxlength="32000" placeholder="例如：请编写一个 Python CSV 统计脚本，并用示例数据验证。"></textarea></label>
        <details><summary>附带文本资料</summary><label>资料内容<textarea id="chat-attachment" rows="5" maxlength="100000" placeholder="粘贴要分析的文档、邮件或其他资料"></textarea></label></details>
        <div class="row"><label>防护<select id="chat-protect"><option value="on">开启 D²Guard</option><option value="off">关闭（对照测试）</option></select></label>
          <button class="btn primary" id="chat-send" type="submit">发送</button><span id="chat-hint" class="muted small"></span></div>
      </form></section>
      <section class="card"><details><summary>本会话工具与防御记录</summary><div id="chat-tools"></div></details><a id="chat-trace" hidden>查看完整证据链 →</a></section>`;
    let sending = false;
    $('#chat-form').addEventListener('submit', async e => {
      e.preventDefault();
      if (sending) return;
      const message = $('#chat-input').value.trim();
      if (!message) return;
      sending = true; $('#chat-send').disabled = true;
      try {
        const body = {message, attachment: $('#chat-attachment').value};
        if (app.job?.mode === 'chat' && app.job.status === 'running') {
          await send('/api/jobs/'+app.job.id+'/chat', 'POST', {type:'prompt', ...body});
        } else {
          app.job = await send('/api/chat', 'POST', {protect:$('#chat-protect').value, ...body});
        }
        $('#chat-input').value = ''; $('#chat-attachment').value = '';
        await pollJob();
      } catch (error) { toast(error.message, true); }
      finally { sending = false; draw(); }
    });
    for (const [id, type] of [['chat-stop','abort'],['chat-close','close']]) {
      $('#'+id).addEventListener('click', async () => {
        if (app.job?.mode !== 'chat') return;
        try { await send('/api/jobs/'+app.job.id+'/chat', 'POST', {type}); await pollJob(); }
        catch (error) { toast(error.message,true); }
      });
    }
    $('#chat-new').addEventListener('click', () => {
      if (app.job?.status === 'running') { toast('请先结束当前会话，再新建对话'); return; }
      app.job = null; draw();
    });
    function draw() {
      if (!$('#chat-input')) return;
      const job = app.job?.mode === 'chat' ? app.job : null, chat = job?.chat;
      const active = job?.status === 'running', busy = active && (chat?.phase !== 'idle' || chat?.command_pending);
      const phase = job?.status === 'failed' ? '启动或运行失败' : job?.status === 'finalizing' ? '会话已结束，研判证据正在后台归档' : !active && job ? '会话已结束' :
        chat?.phase === 'closed' ? '会话已结束，正在保存研判证据…' :
        chat?.phase === 'stopping' ? '正在停止当前操作…' :
        chat?.phase === 'idle' ? '等待你的追问' : chat?.phase === 'running' ? 'Agent 正在执行' : active ? '正在连接 Pi…' : '尚未开始';
      $('#chat-status').textContent = phase;
      $('#chat-send').disabled = sending || busy || (app.job?.status === 'running' && !job);
      $('#chat-protect').disabled = !!active;
      $('#chat-stop').disabled = !active || chat?.phase !== 'running';
      $('#chat-close').disabled = !active;
      $('#chat-new').disabled = !!active;
      $('#chat-hint').textContent = job?.status === 'finalizing' ? '证据在后台保存，你可以开始新对话。' :
        busy ? '生成中可停止；完成后在此继续追问。' : '同一会话保留上下文；闲置 30 分钟后关闭。';
      const messages = chat?.messages || [];
      const fallback = chat?.submitted_messages || [];
      const html = [...fallback, ...messages].map(m => `<article class="chat-message ${m.role}"><b>${m.role === 'user' ? '你' : 'Pi Agent'}</b><pre class="chat-text">${esc(m.text)}</pre></article>`).join('');
      const transcript = $('#chat-messages'), atBottom = transcript.scrollHeight-transcript.scrollTop-transcript.clientHeight < 48;
      setHTML($('#chat-messages'), html + (chat?.partial ? `<article class="chat-message assistant"><b>Pi Agent · 生成中</b><pre class="chat-text">${esc(chat.partial)}</pre></article>` : '') ||
        '<p class="muted">输入你的任务开始对话。</p>');
      if (atBottom) transcript.scrollTop = transcript.scrollHeight;
      setHTML($('#chat-tools'), (chat?.tools || []).map(t => `<p>${badge(t.verdict,VERDICT_CLASS[t.verdict])} <b>${esc(t.tool)}</b> · ${esc(t.rule_id)}<br><small>${esc(t.reason)}</small></p>`).join('') || '<p class="muted">尚无工具调用。</p>');
      const rid = job?.steps?.[0]?.run_id;
      $('#chat-trace').hidden = !rid; $('#chat-trace').href = rid ? '#/trace/'+rid : '#';
      if (job?.status === 'failed') $('#chat-hint').textContent = job.log_tail || '运行失败，请查看服务日志。';
    }
    document.addEventListener('job',draw);
    onLeave(() => document.removeEventListener('job',draw));
    draw();
    api('/api/runtime').then(r => {
      if ($('#chat-runtime')) $('#chat-runtime').textContent = r.phase === 'ready' ? '快镜已就绪，后续任务复用已加载模型。' :
        r.phase === 'loading' ? '服务首次启动正在加载快镜，后续任务无需重复加载。' : r.error || '';
    }).catch(() => {});
  }
};
