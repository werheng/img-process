import test from 'node:test';
import assert from 'node:assert/strict';
import { defaults, PARAMS_STORAGE_KEY, validateParams, parseParamsJson, loadSavedParams } from './params.mjs';

test('参数 JSON 可往返导入，保留 0 与 false，缺少项补默认值', () => {
  const params = { ...defaults, brightness: 12, gamma: 1.2, denoise: 0, use_clahe: false };
  assert.deepEqual(parseParamsJson(JSON.stringify(params)), params);
  assert.deepEqual(parseParamsJson('\uFEFF{"brightness": 12}'), { ...defaults, brightness: 12 });
});

test('自动模式可导入导出，旧参数文件继续使用手动模式', () => {
  assert.equal(parseParamsJson('{"mode":"auto"}').mode, 'auto');
  assert.equal(parseParamsJson('{"gamma":1}').mode, 'manual');
  assert.throws(() => parseParamsJson('{"mode":"unknown"}'));
});

test('拒绝非法 JSON、字段、类型、越界与非整数，不修改原参数', () => {
  for (const text of ['bad', 'null', '[]', '{}', '{"gamma": 9}', '{"denoise": -1}', '{"threshold": 2.5}', '{"gamma": "1"}', '{"use_clahe": "false"}', '{"unexpected": 1}', '{"__proto__": {}}']) {
    assert.throws(() => parseParamsJson(text), text);
  }
  assert.throws(() => validateParams({ ...defaults, brightness: null }));
  assert.throws(() => validateParams({ ...defaults, gamma: NaN }));
  assert.equal(defaults.brightness, 0);
});

test('恢复 localStorage 参数，存储损坏或不可用时退回默认值', t => {
  const storage = new Map([[PARAMS_STORAGE_KEY, JSON.stringify({ ...defaults, contrast: 1.5 })]]);
  const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: key => storage.get(key) ?? null } });
  t.after(() => { if (original) Object.defineProperty(globalThis, 'localStorage', original); else delete globalThis.localStorage; });
  assert.equal(loadSavedParams().params.contrast, 1.5);
  storage.set(PARAMS_STORAGE_KEY, 'invalid JSON');
  assert.deepEqual(loadSavedParams().params, defaults);
  assert.equal(loadSavedParams().notice.type, 'warning');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('unavailable'); } });
  assert.deepEqual(loadSavedParams().params, defaults);
});
