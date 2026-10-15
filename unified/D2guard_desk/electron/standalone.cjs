const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
let core, window, quitting = false;
app.setName('D2Guard');
app.setAppUserModelId('art.li33.d2guard');
const single = app.requestSingleInstanceLock();
if (!single) app.quit();
app.on('second-instance', () => { if (window) { window.restore(); window.focus(); } });
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => { quitting = true; if (core) core.kill(); });
async function start() {
  // Refuse an occupied port: never stop or silently attach to another service.
  await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', () => reject(new Error('端口 8765 已被占用。请关闭已有的 D2Guard 开发服务后重试。')));
    probe.listen(8765, '127.0.0.1', () => probe.close(resolve));
  });
  const data = app.getPath('userData');
  fs.mkdirSync(path.join(data, 'workspace'), { recursive: true });
  const log = fs.openSync(path.join(data, 'core.log'), 'a');
  const executable = path.join(process.resourcesPath, 'core', 'D2GuardCore.exe');
  core = spawn(executable, ['--parent-pid', String(process.pid)], {
    windowsHide: true, stdio: ['ignore', log, log], cwd: data,
    env: { ...process.env, D2GUARD_DB: path.join(data, 'd2guard.sqlite3'),
      D2GUARD_EXEC_ROOT: path.join(data, 'workspace'),
      D2GUARD_STATIC: path.join(process.resourcesPath, 'web'), D2GUARD_MANAGED: '0', D2GUARD_PREFIX: '', PYTHONUTF8: '1' },
  });
  fs.closeSync(log);
  let failed;
  core.on('error', e => { failed = e; });
  core.on('exit', () => {
    failed = new Error('双镜内核已退出，请查看应用数据目录的 core.log。');
    if (window && !quitting) { dialog.showErrorBox('内核已停止', failed.message); app.quit(); }
  });
  const deadline = Date.now() + 45000;
  let ready = false;
  while (Date.now() < deadline) {
    if (failed) throw failed;
    try {
      const r = await fetch('http://127.0.0.1:8765/healthz', { signal: AbortSignal.timeout(1000) });
      if (r.ok && (await r.json()).application === 'D2Guard') { ready = true; break; }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  if (!ready) throw new Error('内核启动超时，请查看应用数据目录的 core.log。');
  window = new BrowserWindow({ width: 1440, height: 940, minWidth: 900, minHeight: 650,
    title: '双镜 D²Guard', backgroundColor: '#F4F5F0', autoHideMenuBar: true,
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => {
    if (new URL(url).origin !== 'http://127.0.0.1:8765') event.preventDefault();
  });
  await window.loadURL('http://127.0.0.1:8765/');
}
if (single) app.whenReady().then(start).catch(e => {
  dialog.showErrorBox('D2Guard 启动失败', e.message); app.quit();
});
