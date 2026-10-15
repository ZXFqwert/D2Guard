const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');

let core, window, quitting = false;
app.setName('D2Guard');
app.setAppUserModelId('art.li33.d2guard');

const single = app.requestSingleInstanceLock();
if (!single) {
  app.quit();
}

app.on('second-instance', () => {
  if (window) {
    if (!window.isVisible()) window.show();
    if (window.isMinimized()) window.restore();
    window.setAlwaysOnTop(true);
    window.focus();
    window.setAlwaysOnTop(false);
  }
});

app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => {
  quitting = true;
  if (core) {
    try { core.kill(); } catch {}
  }
});

async function isExistingD2GuardHealthy() {
  try {
    const r = await fetch('http://127.0.0.1:8765/healthz', { signal: AbortSignal.timeout(800) });
    if (r.ok) {
      const body = await r.json();
      return body && body.application === 'D2Guard';
    }
  } catch {}
  return false;
}

async function start() {
  // Show the window immediately on double-click so the user gets instant visual feedback.
  window = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 900,
    minHeight: 650,
    show: true,
    center: true,
    title: '双镜 D²Guard',
    backgroundColor: '#F8FAF7',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('data:') && new URL(url).origin !== 'http://127.0.0.1:8765') {
      event.preventDefault();
    }
  });

  const splashHtml = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#f8faf7;color:#1e293b;font-family:"Segoe UI","Microsoft YaHei",sans-serif;}
    .ring{width:44px;height:44px;border:3px solid #dbeafe;border-top-color:#0284c7;border-radius:50%;animation:s .8s linear infinite;margin-bottom:18px;}
    h2{margin:0 0 8px;font-size:18px;font-weight:600;letter-spacing:-.3px;}
    p{margin:0;font-size:12px;color:#64748b;}
    @keyframes s{to{transform:rotate(360deg)}}
  </style></head><body><div class="ring"></div><h2>双镜 D²Guard 正在启动</h2><p>正在挂载 D¹ 快慢双镜 (Laya) 与 D² 增量安全状态流内核...</p></body></html>`;
  await window.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(splashHtml));
  window.show();
  window.focus();

  const alreadyUp = await isExistingD2GuardHealthy();
  if (!alreadyUp) {
    await new Promise((resolve, reject) => {
      const probe = net.createServer();
      probe.once('error', () => reject(new Error('端口 8765 已被其他非 D2Guard 程序占用，请释放该端口后重试。')));
      probe.listen(8765, '127.0.0.1', () => probe.close(resolve));
    });
    const data = app.getPath('userData');
    fs.mkdirSync(path.join(data, 'workspace'), { recursive: true });
    const log = fs.openSync(path.join(data, 'core.log'), 'a');
    const executable = path.join(process.resourcesPath, 'core', 'D2GuardCore.exe');
    core = spawn(executable, ['--parent-pid', String(process.pid)], {
      windowsHide: true,
      stdio: ['ignore', log, log],
      cwd: data,
      env: {
        ...process.env,
        D2GUARD_DB: path.join(data, 'd2guard.sqlite3'),
        D2GUARD_EXEC_ROOT: path.join(data, 'workspace'),
        D2GUARD_STATIC: path.join(process.resourcesPath, 'web'),
        D2GUARD_MANAGED: '0',
        D2GUARD_PREFIX: '',
        PYTHONUTF8: '1',
      },
    });
    fs.closeSync(log);
    let failed;
    core.on('error', e => { failed = e; });
    core.on('exit', () => {
      failed = new Error('双镜内核已退出，请查看应用数据目录的 core.log。');
      if (window && !quitting) {
        dialog.showErrorBox('内核已停止', failed.message);
        app.quit();
      }
    });
    const deadline = Date.now() + 45000;
    let ready = false;
    while (Date.now() < deadline) {
      if (failed) throw failed;
      if (await isExistingD2GuardHealthy()) {
        ready = true;
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    if (!ready) throw new Error('内核启动超时，请查看应用数据目录的 core.log。');
  }

  await window.loadURL('http://127.0.0.1:8765/');
  window.show();
  window.focus();
}

if (single) {
  app.whenReady().then(start).catch(e => {
    dialog.showErrorBox('D2Guard 启动失败', e.message);
    app.quit();
  });
}
