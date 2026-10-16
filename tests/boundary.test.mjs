import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { workspacePath, networkTarget } from '../src/boundary.mjs';

test('workspace tool rejects traversal, absolute paths and Windows alternate streams', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'd2-boundary-'));
  t.after(() => fs.rm(root, {recursive:true, force:true}));
  for (const input of ['../outside', 'a/../../outside', '/etc/passwd', 'C:/Windows/a', 'file:secret', '..\\outside']) {
    await assert.rejects(workspacePath(root, input));
  }
  assert.equal(await workspacePath(root, 'notes/result.md'), path.join(root, 'notes', 'result.md'));
});

test('junction cannot redirect the workspace tool into another directory', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'd2-links-'));
  await fs.mkdir(path.join(root, 'workspace'));
  await fs.mkdir(path.join(root, 'outside'));
  t.after(() => fs.rm(root, {recursive:true, force:true}));
  await fs.symlink(path.join(root, 'outside'), path.join(root, 'workspace', 'link'), 'junction');
  await assert.rejects(workspacePath(path.join(root, 'workspace'), 'link/file.txt'));
});

test('model network tool cannot reach control endpoints or arbitrary hosts', () => {
  const base = 'http://127.0.0.1:1234';
  assert.equal(networkTarget('http://lab.test/collect', 'POST', base), base + '/collect');
  for (const url of ['http://127.0.0.1:1234/decision', 'http://lab.test/decision',
    'http://lab.test.evil/collect', 'http://x@lab.test/collect', 'http://lab.test/collect?x=1', 'file:///etc/passwd']) {
    assert.throws(() => networkTarget(url, 'POST', base));
  }
});
