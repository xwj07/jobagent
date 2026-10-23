import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../deploy/cloudflare/_worker.js', import.meta.url), 'utf8');
const {default: worker} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('frontend and evaluation use static assets', async () => {
  const paths = [];
  const env = {ASSETS: {fetch: async request => {
    paths.push(new URL(request.url).pathname);
    return new Response('page');
  }}};
  for (const path of ['/', '/static/workspace.js', '/evaluation']) {
    assert.equal(await (await worker.fetch(new Request(`https://demo.example${path}`), env)).text(), 'page');
  }
  assert.deepEqual(paths, ['/', '/static/workspace.js', '/evaluation.html']);
});

test('proxy preserves request body, method, query and backend response', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async request => {
    assert.equal(request.url, 'https://api.example/jobs/upload?source=manual');
    assert.equal(request.method, 'POST');
    assert.equal(await request.text(), 'uploaded job');
    return new Response('{"detail":"岗位内容为空"}', {status:422});
  };
  try {
    const request = new Request('https://demo.example/jobs/upload?source=manual', {method:'POST', body:'uploaded job'});
    const response = await worker.fetch(request, {BACKEND_URL:'https://api.example'});
    assert.equal(response.status, 422);
    assert.deepEqual(await response.json(), {detail:'岗位内容为空'});
  } finally {
    globalThis.fetch = original;
  }
});

test('missing backend configuration returns a visible reason', async () => {
  const response = await worker.fetch(new Request('https://demo.example/jobs/options'), {});
  assert.equal(response.status, 503);
  assert.match((await response.json()).detail, /BACKEND_URL/);
});

test('offline server returns a visible reason', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError('connection failed'); };
  try {
    const response = await worker.fetch(new Request('https://demo.example/jobs/options'), {BACKEND_URL:'https://api.example'});
    assert.equal(response.status, 502);
    assert.match((await response.json()).detail, /Tunnel/);
  } finally {
    globalThis.fetch = original;
  }
});
