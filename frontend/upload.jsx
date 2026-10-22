import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Alert, Button, Card, ConfigProvider, Empty, Image, InputNumber, Progress, Segmented, Slider, Switch, Tag, Upload } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { buildArchive } from './download.mjs';
import { defaults, PARAMS_STORAGE_KEY, validateParams, parseParamsJson, loadSavedParams } from './params.mjs';
import { ArrowRightOutlined, LeftOutlined, RightOutlined, CheckCircleFilled, CloudUploadOutlined, DownloadOutlined, ExportOutlined, ImportOutlined, FileImageOutlined, FolderOpenOutlined, InfoCircleOutlined, PictureOutlined, ReloadOutlined, SettingOutlined, ThunderboltFilled } from '@ant-design/icons';

const fields = [
  ['brightness', '亮度', -128, 127, 1], ['contrast', '对比度', 0.5, 2, 0.1],
  ['gamma', 'Gamma 校正', 0.1, 3, 0.1], ['threshold', '曝光阈值', 1, 254, 1], ['denoise', '降噪强度', 0, 100, 1],
];
const supported = /\.(png|jpe?g|bmp|gif|webp|tiff)$/i;
const formatSize = bytes => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

function Preview({ src, alt, onOpen }) {
  const [failed, setFailed] = useState(false);
  return failed ? <div className="preview-fallback"><PictureOutlined /><span>浏览器暂时无法预览此图片</span></div> :
    <button type="button" className="preview-trigger" aria-label={`放大查看${alt}`} onClick={onOpen}><Image preview={false} src={src} alt={alt} width="100%" height={220} styles={{ image: { objectFit: 'contain', background: '#f4f6fa', borderRadius: 10 } }} onError={() => setFailed(true)} /></button>;
}

function Workbench() {
  const [mode, setMode] = useState('single');
  const [fileList, setFileList] = useState([]);
  const [initialSettings] = useState(loadSavedParams);
  const [params, setParams] = useState(initialSettings.params);
  const [paramsNotice, setParamsNotice] = useState(initialSettings.notice);
  const [saveStatus, setSaveStatus] = useState('');
  const [importing, setImporting] = useState(false);
  const paramsFile = useRef(null);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState([]);
  const [notice, setNotice] = useState(null);
  const [current, setCurrent] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const [previewKey, setPreviewKey] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState(null);
  const downloadLock = useRef(false);
  const thumbnailList = useRef(null);
  const urls = useRef([]);
  const running = useRef(false);
  const release = () => { urls.current.forEach(URL.revokeObjectURL); urls.current = []; };
  useEffect(() => () => release(), []);
  useEffect(() => {
    let valid;
    try { valid = validateParams(params); }
    catch { setSaveStatus('参数尚未填写完整，暂未保存'); return; }
    try {
      localStorage.setItem(PARAMS_STORAGE_KEY, JSON.stringify(valid));
      setSaveStatus('参数已自动保存到此浏览器');
    } catch { setSaveStatus('浏览器存储不可用，参数暂未保存；可导出 JSON 备份'); }
  }, [params]);

  function exportParams() {
    try {
      const valid = validateParams(params);
      const url = URL.createObjectURL(new Blob([JSON.stringify(valid, null, 2) + '\n'], { type: 'application/json;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = '增强参数.json';
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      setParamsNotice({ type: 'success', text: '增强参数已导出为 JSON。' });
    } catch (error) { setParamsNotice({ type: 'error', text: error.message }); }
  }

  async function importParams(event) {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file || running.current) return;
    setImporting(true);
    try {
      if (file.size > 64 * 1024) throw new Error('参数文件过大，请选择小于 64 KB 的 JSON 文件。');
      const imported = parseParamsJson(await file.text());
      setParams(imported);
      setParamsNotice({ type: 'success', text: '参数已导入。未提供的参数使用默认值。' });
    } catch (error) { setParamsNotice({ type: 'error', text: `导入失败：${error.message} 当前参数保持不变。` }); }
    finally { setImporting(false); }
  }

  const update = (name, value) => setParams(previous => ({ ...previous, [name]: value }));
  const success = results.filter(item => item.status === 'success').length;
  const failed = results.filter(item => item.status === 'error').length;
  const completed = success + failed;
  const active = results[activeIndex];
  // 使用稳定标识定位大图，避免处理过程中新增增强图时改变当前预览。
  const previewItems = results.flatMap((item, index) => [
    { key: `${index}:original`, src: item.original, label: `${item.name} · 原始图片`, resultIndex: index },
    ...(item.output ? [{ key: `${index}:output`, src: item.output, label: `${item.name} · 增强图片`, resultIndex: index }] : []),
  ]);
  const previewIndex = Math.max(0, previewItems.findIndex(item => item.key === previewKey));
  useEffect(() => {
    thumbnailList.current?.querySelector(`[data-index="${activeIndex}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [activeIndex]);
  const createUrl = blob => { const url = URL.createObjectURL(blob); urls.current.push(url); return url; };
  const patch = (index, changes) => setResults(previous => previous.map((item, i) => i === index ? { ...item, ...changes } : item));

  async function downloadAll() {
    if (downloadLock.current || busy || !success) return;
    downloadLock.current = true;
    setDownloading(true);
    setDownloadStatus({ type: 'info', text: '正在准备图片…' });
    try {
      const archive = await buildArchive(results, (done, total) => {
        setDownloadStatus({ type: 'info', text: `正在打包图片 ${done} / ${total}…` });
      });
      if (!archive.count) {
        throw new Error('未能打包任何图片，请重新处理后重试。');
      }
      const url = URL.createObjectURL(new Blob([archive.bytes], { type: 'application/zip' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `增强图片_${new Date().toISOString().replace(/[:.]/g, '-')}.zip`;
      document.body.append(link);
      link.click();
      link.remove();
      // 给浏览器足够时间接管下载；此 URL 不与结果列表共用生命周期。
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      const skipped = archive.failures.map(item => item.name).join('、');
      setDownloadStatus({ type: archive.failures.length ? 'warning' : 'success', text: archive.failures.length
        ? `已打包 ${archive.count} 张，以下图片下载失败：${skipped}。请重新处理这些图片后重试。`
        : `已打包 ${archive.count} 张图片，ZIP 下载已开始。` });
    } catch (error) {
      setDownloadStatus({ type: 'error', text: error.message });
    } finally { downloadLock.current = false; setDownloading(false); }
  }

  async function start(event) {
    event.preventDefault();
    if (running.current || downloadLock.current || importing) return;
    if (!fileList.length) return setNotice({ type: 'warning', text: '请先选择需要处理的图片。' });
    if (params.mode !== 'auto' && fields.some(([name, , min, max]) => params[name] == null || !Number.isFinite(params[name]) || params[name] < min || params[name] > max)) {
      return setNotice({ type: 'warning', text: '请填写有效的处理参数。' });
    }
    running.current = true;
    setBusy(true);
    setNotice(null);
    setCurrent(0);
    setActiveIndex(0);
    setPreviewKey(null);
    setDownloadStatus(null);
    release();
    const queue = fileList.map(item => ({ name: item.name, file: item.originFileObj || item, original: createUrl(item.originFileObj || item), status: 'waiting' }));
    setResults(queue);
    try {
      for (let i = 0; i < queue.length; i++) {
        setCurrent(i + 1);
        patch(i, { status: 'processing' });
        const body = new FormData();
        body.append('file', queue[i].file);
        Object.entries(params).forEach(([key, value]) => body.append(key, String(value)));
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 300000);
        try {
          const response = await fetch('/api/img-adjust/upload', { method: 'POST', body, signal: controller.signal });
          let payload;
          try { payload = await response.json(); }
          catch { throw new Error(`接口返回非 JSON 数据（HTTP ${response.status}），请检查服务配置。`); }
          const data = payload.data || {};
          const display = { ...payload, data: { ...data } };
          if (data.image_base64) display.data.image_base64 = `[图片数据，${data.image_base64.length} 字符]`;
          patch(i, { response: display });
          if (!response.ok || !payload.success) throw new Error(payload.message || `请求失败（HTTP ${response.status}）`);
          if (!data.image_base64) throw new Error('接口未返回图片数据');
          const binary = atob(data.image_base64);
          const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
          const outputBlob = new Blob([bytes], { type: 'image/jpeg' });
          const output = createUrl(outputBlob);
          patch(i, { status: 'success', output, outputBlob, size: data.size_bytes || 0, processing: data.processing });
        } catch (error) {
          patch(i, { status: 'error', message: error.name === 'AbortError' ? '请求超过 5 分钟，请稍后重试。' : error.message });
        } finally { clearTimeout(timer); }
      }
    } finally { running.current = false; setBusy(false); }
  }

  return <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#2563eb', borderRadius: 10, colorText: '#17243b', colorTextSecondary: '#7b8799', colorBorderSecondary: '#e9edf4', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif' }, components: { Card: { headerFontSize: 15 }, Button: { controlHeightLG: 46 }, Segmented: { trackBg: '#f0f3f9' } } }}>
    <Image.PreviewGroup items={previewItems.map(item => ({ src: item.src, alt: item.label }))} preview={{
      open: previewKey !== null,
      current: previewIndex,
      onOpenChange: open => { if (!open) setPreviewKey(null); },
      onChange: index => {
        const item = previewItems[index];
        if (item) { setPreviewKey(item.key); setActiveIndex(item.resultIndex); }
      },
      countRender: (position, total) => <div className="large-preview-caption" aria-live="polite"><span>{previewItems[position - 1]?.label}</span><span>{position} / {total}</span></div>,
    }} />
    <nav className="topbar"><div className="nav-inner"><a href="/upload" className="brand"><span className="brand-icon"><PictureOutlined /></span><span>图像处理<span className="brand-divider">/</span><span className="brand-secondary">增强工作台</span></span></a><Tag color="blue">IMAGE STUDIO</Tag></div></nav>
    <main className="workspace">
      <header className="page-header"><div><div className="eyebrow">让每一处细节，更清晰</div><h1>图片增强工作台 <span className="title-spark"><ThunderboltFilled /></span></h1><p>上传图片，自由调整增强参数，轻松获取更好的图像效果。</p></div><div className="header-note"><CheckCircleFilled /> 本地选择 · 即时处理</div></header>
      <div className="workspace-grid">
        <div className="main-column">
          <Card className="surface upload-card" title={<span className="card-title"><span className="step-number">01</span> 上传图片</span>} extra={<Tag>每张 ≤ 10 MB</Tag>}>
            <div className="upload-mode"><Segmented aria-label="上传模式" disabled={busy} value={mode} onChange={value => { setMode(value); setFileList([]); setNotice(null); }} options={[{ label: '单文件上传', value: 'single', icon: <FileImageOutlined /> }, { label: '多文件上传', value: 'multiple', icon: <FolderOpenOutlined /> }]} /><span className="muted mode-hint">{mode === 'single' ? '一次处理一张图片' : '最多支持 100 张图片'}</span></div>
            <Upload.Dragger key={mode} name="file" accept=".png,.jpg,.jpeg,.bmp,.gif,.webp,.tiff" disabled={busy} multiple={mode === 'multiple'} maxCount={mode === 'single' ? 1 : 100} fileList={fileList} listType="text" beforeUpload={(file, batch) => {
              if (!supported.test(file.name) || !file.size || file.size > 10 * 1024 * 1024) {
                setNotice({ type: 'error', text: `${file.name}：请选择支持的图片格式，大小须大于 0 且不超过 10 MB。` });
                return Upload.LIST_IGNORE;
              }
              if (mode === 'multiple' && fileList.length + batch.length > 100) {
                setNotice({ type: 'warning', text: '最多选择 100 张图片，请减少选择数量。' });
                return Upload.LIST_IGNORE;
              }
              return false;
            }} onChange={({ fileList: next }) => setFileList(next)}>
              <div className="drop-content"><span className="upload-symbol"><CloudUploadOutlined /></span><h2>点击选择，或拖拽图片到这里</h2><p>支持 PNG、JPG、JPEG、BMP、GIF、WEBP、TIFF</p><span className="choose-button">选择图片 <ArrowRightOutlined /></span></div>
            </Upload.Dragger>
            <div className="upload-footnote"><InfoCircleOutlined /><span>{fileList.length ? `已选择 ${fileList.length} 张 · ${formatSize(fileList.reduce((sum, file) => sum + file.size, 0))}` : '图片处理完成后，服务端临时文件会自动清理。'}</span>{fileList.length > 0 && <Button type="text" size="small" disabled={busy} onClick={() => setFileList([])}>清空列表</Button>}</div>
            {notice && <Alert showIcon type={notice.type} title={notice.text} className="notice" />}
          </Card>
          <section className="results-area" aria-labelledby="results-title">
            <div className="results-heading"><h2 id="results-title">处理结果 <span>{results.length ? `${completed} / ${results.length}` : 'RESULTS'}</span></h2><div className="result-tools">{success > 0 && <Tag color="success">成功 {success}</Tag>}{failed > 0 && <Tag color="error">失败 {failed}</Tag>}<Button id="download-all" icon={<DownloadOutlined />} disabled={busy || !success} loading={downloading} onClick={downloadAll}>批量下载{success ? ` · ${success} 张` : ''}</Button></div></div>
            {downloadStatus && <div role="status" aria-live="polite" className="download-status"><Alert showIcon type={downloadStatus.type} title={downloadStatus.text} /></div>}
            {results.length === 0 ? <Card className="surface empty-card"><Empty image={<span className="empty-symbol"><PictureOutlined /></span>} description={<div><strong>等待你的第一张图片</strong><p>上传并开始处理后，在这里查看原图对比与增强结果。</p></div>} /></Card> : <>
              <div role="status" aria-live="polite" className="progress-summary"><span>{busy ? `正在处理第 ${current} / ${results.length} 张` : `处理完成：成功 ${success} 张，失败 ${failed} 张`}</span><Progress percent={Math.round(completed / results.length * 100)} status={busy ? 'active' : failed ? 'exception' : 'success'} size="small" /></div>
              <div className="gallery" role="region" aria-label="图片切换浏览器" tabIndex={0} onKeyDown={event => {
                if (event.target !== event.currentTarget) return;
                if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                  event.preventDefault();
                  setActiveIndex(index => Math.max(0, Math.min(results.length - 1, index + (event.key === 'ArrowRight' ? 1 : -1))));
                }
              }}>
                <div className="gallery-navigation">
                  <Button id="previous-image" icon={<LeftOutlined />} disabled={activeIndex === 0} onClick={() => setActiveIndex(index => index - 1)}>上一张</Button>
                  <span className="gallery-counter" aria-live="polite">第 <strong>{activeIndex + 1}</strong> / {results.length} 张</span>
                  <Button id="next-image" disabled={activeIndex === results.length - 1} onClick={() => setActiveIndex(index => index + 1)}>下一张 <RightOutlined /></Button>
                </div>
                {active && <Card key={activeIndex} className="surface result-card" title={<span className="result-name"><FileImageOutlined /> {active.name}</span>} extra={<Tag color={{ waiting: 'default', processing: 'processing', success: 'success', error: 'error' }[active.status]}>{ { waiting: '等待处理', processing: '处理中', success: '处理成功', error: '处理失败' }[active.status]}</Tag>}>
                  <div className="comparison"><figure><figcaption>原始图片</figcaption><Preview src={active.original} alt={`${active.name} 原图`} onOpen={() => setPreviewKey(`${activeIndex}:original`)} /></figure><figure><figcaption><ThunderboltFilled /> 增强结果</figcaption>{active.output ? <Preview src={active.output} alt={`${active.name} 处理后`} onOpen={() => setPreviewKey(`${activeIndex}:output`)} /> : <div className="preview-fallback"><PictureOutlined /><span>{active.message || (active.status === 'processing' ? '正在增强图片，请稍候…' : '等待处理')}</span></div>}</figure></div>
                  {active.output && <div className="result-footer"><span className="muted">JPG · {formatSize(active.size)} · 点击图片可放大预览</span><Button icon={<DownloadOutlined />} href={active.output} download={`${active.name.replace(/\.[^.]+$/, '')}_processed.jpg`}>下载图片</Button></div>}
                  {active.processing?.mode === 'auto' && <div className="processing-report" role="status">
                    <strong>{active.processing.label}</strong>
                    <p>{active.processing.reason}</p>
                    <p>参考区域亮度：{active.processing.metrics.median_lightness} · 暗部比例：{(active.processing.metrics.dark_ratio * 100).toFixed(1)}% · Gamma 上限：{active.processing.selected_params.gamma}</p>
                    {active.processing.region_summary && <p>局部提亮：{active.processing.region_summary.shadow_cells} 区 · 对比增强：{active.processing.region_summary.contrast_cells} 区 · 对比系数上限：{active.processing.selected_params.local_contrast_gain_max}</p>}
                    {active.processing.warnings.map(warning => <p key={warning}>{warning}</p>)}
                    <details><summary>查看分析指标和实际参数</summary><pre>{JSON.stringify(active.processing, null, 2)}</pre></details>
                  </div>}
                  {active.response && <details className="response-details"><summary>查看接口响应</summary><pre>{JSON.stringify(active.response, null, 2)}</pre></details>}
                </Card>}
                <div className="thumbnail-heading"><span>全部图片 · {results.length} 张</span><span>点击切换 · 聚焦浏览器后可用 ← → 切换</span></div>
                <div ref={thumbnailList} className="thumbnail-list" aria-label="全部图片列表">
                  {results.map((item, index) => <button type="button" key={index} data-index={index} className={`thumbnail ${index === activeIndex ? 'selected' : ''}`} aria-current={index === activeIndex ? 'true' : undefined} aria-label={`查看第 ${index + 1} 张：${item.name}`} title={item.name} onClick={() => setActiveIndex(index)}>
                    <div className="thumbnail-image"><img key={item.output || item.original} src={item.output || item.original} alt="" loading="lazy" onError={event => { event.currentTarget.hidden = true; }} /><span className="thumbnail-number">{index + 1}</span><span className={`thumbnail-status ${item.status}`}>{ { waiting: '等待', processing: '处理中', success: '成功', error: '失败' }[item.status]}</span></div>
                    <span className="thumbnail-name">{item.name}</span>
                  </button>)}
                </div>
              </div>
            </>}

          </section>
        </div>
        <aside className="settings-column"><Card className="surface settings-card" title={<span className="card-title"><SettingOutlined /> 增强参数</span>} extra={<Button type="text" size="small" icon={<ReloadOutlined />} disabled={busy} onClick={() => { setParams({ ...defaults }); setParamsNotice({ type: 'success', text: '已恢复默认参数。' }); }}>重置</Button>}>
          <div className="params-actions">
            <Button id="import-params" icon={<ImportOutlined />} disabled={busy} loading={importing} onClick={() => paramsFile.current?.click()}>导入 JSON</Button>
            <Button id="export-params" icon={<ExportOutlined />} disabled={importing} onClick={exportParams}>导出 JSON</Button>
            <input id="params-file" ref={paramsFile} type="file" accept=".json,application/json" hidden disabled={busy || importing} onChange={importParams} />
          </div>
          <p className="params-save-status" role="status" aria-live="polite">{saveStatus}</p>
          {paramsNotice && <div className="params-notice" role="status"><Alert showIcon type={paramsNotice.type} title={paramsNotice.text} /></div>}
          <form onSubmit={start}>
            <div className="processing-mode">
              <label>处理方式</label>
              <Segmented block aria-label="处理方式" disabled={busy} value={params.mode} onChange={value => update('mode', value)} options={[{ label: '手动参数', value: 'manual' }, { label: '自动分析', value: 'auto' }]} />
              {params.mode === 'auto' && <p>逐张分区分析，按需提亮暗部、增强低对比区域，保护高亮。无明确问题时中性处理。下方手动参数不参与处理。</p>}
            </div>
            {fields.map(([name, label, min, max, step]) => <div className="parameter" key={name}><div className="parameter-heading"><label htmlFor={name}>{label}</label><InputNumber id={name} aria-label={label} min={min} max={max} step={step} value={params[name]} disabled={busy || params.mode === 'auto'} onChange={value => update(name, value)} size="small" style={{ width: 76 }} /></div><Slider aria-label={`${label}滑块`} min={min} max={max} step={step} value={params[name] ?? min} disabled={busy || params.mode === 'auto'} onChange={value => update(name, value)} /><div className="range-labels"><span>{name === 'denoise' ? '0 · 关闭' : min}</span><span>{max}</span></div></div>)}
            <div className="settings-divider" />
            <div className="switch-row"><div><label htmlFor="reduce-overexpose">抑制过曝</label><p>压低高亮区域，无法恢复反光遮挡细节</p></div><Switch id="reduce-overexpose" checked={params.reduce_overexpose} disabled={busy || params.mode === 'auto'} onChange={value => update('reduce_overexpose', value)} /></div>
            <div className="switch-row"><div><label htmlFor="use-clahe">CLAHE 增强</label><p>自适应提升局部对比度</p></div><Switch id="use-clahe" checked={params.use_clahe} disabled={busy || params.mode === 'auto'} onChange={value => update('use_clahe', value)} /></div>
            <Button id="start-upload" type="primary" htmlType="submit" size="large" block loading={busy} disabled={!fileList.length || downloading || importing} icon={<ThunderboltFilled />}>{busy ? '正在处理图片' : `开始增强${fileList.length ? ` · ${fileList.length} 张` : ''}`}</Button>
            <p className="submit-hint">{mode === 'multiple' ? '逐张处理，单张失败不影响其余图片' : '调整参数后，点击开始增强'}</p>
          </form>
        </Card><div className="tips"><InfoCircleOutlined /><p>{params.mode === 'auto' ? '自动模式为每张图片选择方案，结果中可查看原因；批量下载附处理记录。识别效果需送测验证。' : '手动模式使用相同参数，也可切换自动分析逐张选择方案。'}</p></div></aside>
      </div>
      <footer className="page-footer"><span>IMAGE STUDIO</span><span>更清晰的图片，从这里开始</span></footer>
    </main>
  </ConfigProvider>;
}

createRoot(document.getElementById('root')).render(<Workbench />);
