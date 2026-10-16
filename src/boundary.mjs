import fs from 'node:fs/promises';
import path from 'node:path';

export async function workspacePath(root, value) {
  if (typeof value !== 'string' || !value || value.includes('\0') || /[:\\]/.test(value) ||
      value.startsWith('/') || value.split('/').some(p => p === '..' || !p)) {
    throw new Error('Experiment boundary: only workspace-relative paths are allowed');
  }
  const base = await fs.realpath(root);
  const target = path.resolve(base, value);
  if (!isInside(base, target)) throw new Error('Experiment boundary: path outside workspace');
  let current = base;
  for (const part of value.split('/')) {
    if (part === '.') continue;
    current = path.join(current, part);
    try {
      const stat = await fs.lstat(current);
      if (stat.isSymbolicLink()) throw new Error('Experiment boundary: links are not allowed');
      const real = await fs.realpath(current);
      if (!isInside(base, real)) throw new Error('Experiment boundary: resolved path outside workspace');
    } catch (e) { if (e.code !== 'ENOENT') throw e; }
  }
  return target;
}

function isInside(base, target) {
  const rel = path.relative(base, target);
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
}

export function networkTarget(input, method, serviceOrigin) {
  const url = new URL(input);
  const allowed = (url.pathname === '/docs/project' && method === 'GET') ||
    (url.pathname === '/collect' && method === 'POST');
  if (url.origin !== 'http://lab.test' || url.username || url.password || url.search || url.hash || !allowed)
    throw new Error('Experiment boundary: only lab document GET and collector POST are available');
  return serviceOrigin + url.pathname;
}
