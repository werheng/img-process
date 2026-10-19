import { zipSync } from 'fflate';

export function imageFilename(name, index) {
  const stem = name.replace(/\.[^.]+$/, '').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').trim().slice(0, 120) || 'image';
  return `${String(index + 1).padStart(3, '0')}_${stem}_processed.jpg`;
}

export async function buildArchive(results, onProgress = () => {}) {
  const images = results.filter(item => item.status === 'success' && item.output);
  const files = Object.create(null);
  const failures = [];
  for (let index = 0; index < images.length; index++) {
    const item = images[index];
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      let blob = item.outputBlob;
      if (!blob) {
        const response = await fetch(item.output, { signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        blob = await response.blob();
        // MinIO/代理可能返回 HTML 错误页，避免将它当成 JPG 打包。
        if (blob.type && !blob.type.startsWith('image/') && blob.type !== 'application/octet-stream') {
          throw new Error('返回内容不是图片');
        }
      }
      if (!blob.size) throw new Error('图片内容为空');
      files[imageFilename(item.name, index)] = new Uint8Array(await blob.arrayBuffer());
    } catch (error) {
      failures.push({ name: item.name, message: error.name === 'AbortError' ? '下载超时' : error.message });
    } finally {
      clearTimeout(timer);
      onProgress(index + 1, images.length);
    }
  }
  const count = Object.keys(files).length;
  return { bytes: count ? zipSync(files, { level: 0 }) : null, count, failures };
}
