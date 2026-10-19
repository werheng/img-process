import test from 'node:test';
import assert from 'node:assert/strict';
import { unzipSync } from 'fflate';
import { buildArchive, imageFilename } from './download.mjs';

test('ZIP 保留同名图片，跳过失败和等待项，图片字节不变', async () => {
  const bytes = new Uint8Array([255, 216, 255, 217]);
  const successful = { name: '同名.png', status: 'success', output: 'blob:cached', outputBlob: new Blob([bytes], { type: 'image/jpeg' }) };
  const updates = [];
  const result = await buildArchive([successful, { ...successful }, { name: 'failed.png', status: 'error' }, { name: 'waiting.png', status: 'waiting' }], (...args) => updates.push(args));
  const files = unzipSync(result.bytes);
  assert.deepEqual(Object.keys(files), ['001_同名_processed.jpg', '002_同名_processed.jpg']);
  assert.deepEqual(files['001_同名_processed.jpg'], bytes);
  assert.equal(result.count, 2);
  assert.deepEqual(result.failures, []);
  assert.deepEqual(updates, [[1, 2], [2, 2]]);
});

test('远程下载失败时继续打包其他图片，并报告失败文件', async t => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('bad')) throw new TypeError('Failed to fetch');
    return new Response(new Blob(['image'], { type: 'image/jpeg' }));
  });
  const result = await buildArchive([
    { name: 'bad.png', status: 'success', output: 'https://example.invalid/bad' },
    { name: 'good.png', status: 'success', output: 'https://example.invalid/good' },
  ]);
  assert.equal(fetchMock.mock.callCount(), 2);
  assert.equal(result.count, 1);
  assert.deepEqual(Object.keys(unzipSync(result.bytes)), ['002_good_processed.jpg']);
  assert.deepEqual(result.failures, [{ name: 'bad.png', message: 'Failed to fetch' }]);
});

test('不将错误页面或空文件放进 ZIP，清理路径字符', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>error</html>', { headers: { 'Content-Type': 'text/html' } }));
  const result = await buildArchive([{ name: 'bad.png', status: 'success', output: 'https://example.invalid/bad' }]);
  assert.equal(result.bytes, null);
  assert.equal(result.count, 0);
  assert.equal(result.failures.length, 1);
  const empty = await buildArchive([{ name: 'empty.png', status: 'success', output: 'blob:empty', outputBlob: new Blob([]) }]);
  assert.equal(empty.count, 0);
  assert.equal(imageFilename('../a\\b.png', 0).includes('/'), false);
  assert.equal(imageFilename('../a\\b.png', 0).includes('\\'), false);
});
