export const PARAMS_STORAGE_KEY = 'img-process.enhancement-params.v1';
export const defaults = Object.freeze({ mode: 'manual', brightness: 0, contrast: 0.9, gamma: 0.9, threshold: 250, denoise: 0, reduce_overexpose: false, use_clahe: true });
const ranges = { brightness: [-128, 127], contrast: [0.5, 2], gamma: [0.1, 3], threshold: [1, 254], denoise: [0, 100] };

export function validateParams(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('参数必须是 JSON 对象。');
  const keys = Object.keys(value);
  if (!keys.length) throw new Error('JSON 中没有增强参数。');
  const unknown = keys.find(key => !Object.hasOwn(defaults, key));
  if (unknown) throw new Error(`未知参数：${unknown}`);
  const params = { ...defaults, ...value };
  if (!['manual', 'auto'].includes(params.mode)) throw new Error('mode 必须为 manual 或 auto。');
  for (const [name, [min, max]] of Object.entries(ranges)) {
    const number = params[name];
    if (typeof number !== 'number' || !Number.isFinite(number) || number < min || number > max) {
      throw new Error(`${name} 必须是 ${min} 到 ${max} 之间的数字。`);
    }
    if ((name === 'threshold' || name === 'denoise') && !Number.isInteger(number)) throw new Error(`${name} 必须是整数。`);
  }
  for (const name of ['reduce_overexpose', 'use_clahe']) {
    if (typeof params[name] !== 'boolean') throw new Error(`${name} 必须是 true 或 false。`);
  }
  return params;
}

export function parseParamsJson(text) {
  let value;
  try { value = JSON.parse(text.replace(/^\uFEFF/, '')); }
  catch { throw new Error('JSON 格式无效，请检查文件内容。'); }
  return validateParams(value);
}

export function loadSavedParams() {
  try {
    const text = localStorage.getItem(PARAMS_STORAGE_KEY);
    return { params: text === null ? { ...defaults } : parseParamsJson(text), notice: null };
  } catch {
    return { params: { ...defaults }, notice: { type: 'warning', text: '无法恢复本地参数，已使用默认值。' } };
  }
}
