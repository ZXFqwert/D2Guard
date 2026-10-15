// Usage: node scripts/verify-desktop.cjs /absolute/path/to/playwright
const { _electron } = require(process.argv[2] || 'playwright');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const executable = path.resolve('release/win-unpacked/D2Guard.exe');
const env = { ...process.env }; delete env.ELECTRON_RUN_AS_NODE;
async function portClosed() {
  for (let i = 0; i < 40; i++) {
    try { await fetch('http://127.0.0.1:8765/healthz', { signal: AbortSignal.timeout(300) }); }
    catch { return; }
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error('Owned core did not stop');
}
(async () => {
  let application;
  try {
    application = await _electron.launch({ executablePath: executable, env, timeout: 60000 });
    const page = await application.firstWindow({ timeout: 60000 });
    await page.getByText('内核在线', { exact: true }).waitFor();
    if (process.env.D2GUARD_TEST_CONFIG) {
      const configured = await fetch('http://127.0.0.1:8765/api/desktop/models/config', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: process.env.D2GUARD_TEST_CONFIG,
      });
      if (!configured.ok) throw new Error('Test model configuration failed');
    }
    await page.getByRole('button', { name: '启动双镜铠甲', exact: true }).waitFor();
    const second = spawn(executable, [], { env, windowsHide: true, stdio: 'ignore' });
    const exit = await new Promise(resolve => second.on('exit', resolve));
    if (exit !== 0) throw new Error('Second instance failed');
    const flow = eval('(' + fs.readFileSync('scripts/ui_redesign_flows.js', 'utf8') + ')');
    const results = await flow(page);
    await page.screenshot({ path: 'output/playwright/desktop-app.png' });
    await application.close(); application = null;
    await portClosed();
    fs.writeFileSync('output/desktop-package-tests.json', JSON.stringify({ ...results, packagedExecutable: true, singleInstance: true, ownedCoreCleanup: true }, null, 2));
    console.log('Packaged desktop: all scenarios, approval/rejection, free input, single instance and cleanup passed.');
  } finally { if (application) await application.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
