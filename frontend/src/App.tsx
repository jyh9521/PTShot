import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertDialog, Button, ButtonGroup, ButtonGroupItem, Card, Icon, IconButton,
  LinearProgress, LoadingIndicator, Snackbar, Switch, TextField, WideNavigationRail,
} from '@kyralabs/m3e-react';
import type { ImageRecord, Job, Settings, Video, WorkerEvent } from './types';

export const DESIGN_SYSTEM = 'Material 3 Expressive';
const INITIAL: Settings = { mode: 'screenshots', count: 6, cols: 4, rows: 4, width: 3840,
  content_type: 0, thumbnail_size: 350, upload: true, optimization: 4, tools: {} };
const ENGINES = [
  { name: 'mosaic-cli', title: 'Mosaic', description: '原尺寸截图与总览拼图', icon: 'movie_edit' },
  { name: 'oxipng', title: 'oxipng', description: '大于 10 MB 时无损优化', icon: 'compress' },
  { name: 'ffmpeg', title: 'FFmpeg', description: '影片解码引擎', icon: 'video_file' },
  { name: 'ffprobe', title: 'ffprobe', description: '影片轨道与尺寸分析', icon: 'frame_inspect' },
  { name: 'mediainfo', title: 'MediaInfo', description: '影片信息与拼图标题', icon: 'info' },
];
const LABELS: Record<string, string> = { pending: '等待处理', local: '已保存到本地', uploading: '正在上传',
  resolving: '校验高清原图', uploaded: '高清原图已就绪', error: '待重试', oversize: '优化后仍超限' };
const JOB_LABELS: Record<string, string> = { running: '正在处理', completed: '全部完成', partial: '部分完成',
  failed: '任务未完成', cancelled: '已取消' };
const filename = (value: string) => value.split(/[\\/]/).pop() || value;
const bytes = (value: number) => value >= 1_000_000_000 ? `${(value / 1_000_000_000).toFixed(2)} GB` : `${(value / 1_000_000).toFixed(2)} MB`;
const bbcode = (job: Job | null) => job?.records.filter(r => r.status === 'uploaded' && r.direct_url)
  .map(r => `[img]${r.direct_url}[/img]`).join('\n') || '';

function valid(settings: Settings) {
  return [['count', 1, 100], ['cols', 1, 12], ['rows', 1, 12], ['width', 320, 16384],
    ['thumbnail_size', 150, 500], ['optimization', 0, 6]].every(([key, min, max]) => {
    const value = settings[key as keyof Settings];
    return typeof value === 'number' && Number.isInteger(value) && value >= Number(min) && value <= Number(max);
  });
}

function NumberField({ label, value, onChange, min, max, suffix, disabled = false }: {
  label: string; value: number; onChange: (value: number) => void; min: number; max: number; suffix?: string; disabled?: boolean;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => { if (Number.isFinite(value)) setDraft(String(value)); }, [value]);
  const invalid = !/^\d+$/.test(draft) || Number(draft) < min || Number(draft) > max;
  return <TextField variant="outlined" label={label} value={draft} inputMode="numeric" suffix={suffix}
    isDisabled={disabled} isInvalid={invalid} errorMessage={`请输入 ${min}–${max} 之间的整数`}
    onChange={text => { setDraft(text); onChange(/^\d+$/.test(text) ? Number(text) : NaN); }} />;
}

function Brand({ small = false }: { small?: boolean }) {
  return <div className={`brand-mark ${small ? 'small' : ''}`} aria-hidden="true">
    <svg viewBox="0 0 48 48" fill="none"><path d="M24 4C31 0 36 6 36 12C44 12 48 18 44 24C48 31 42 36 36 36C36 44 30 48 24 44C17 48 12 42 12 36C4 36 0 30 4 24C0 17 6 12 12 12C12 4 18 0 24 4Z" fill="currentColor"/><path d="M17 17.5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H17a2 2 0 0 1-2-2v-10a2 2 0 0 1 2-2Z" stroke="var(--m3e-sys-color-on-primary-container)" strokeWidth="2"/><path d="m22 21 6 3.5-6 3.5v-7Z" fill="var(--m3e-sys-color-on-primary-container)"/></svg>
  </div>;
}

export default function App() {
  const [page, setPage] = useState('workspace');
  const [settings, setSettings] = useState<Settings>(INITIAL);
  const [videos, setVideos] = useState<Video[]>([]);
  const [output, setOutput] = useState('');
  const [theme, setTheme] = useState('light');
  const [tools, setTools] = useState<Record<string, string>>({});
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [booting, setBooting] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [showLogs, setShowLogs] = useState(false);
  const [resultView, setResultView] = useState('images');
  const logRef = useRef<HTMLPreElement>(null);
  const logBuffer = useRef<string[]>([]);
  const notify = useCallback((value: string) => setMessage(value), []);
  const guard = async <T,>(operation: () => Promise<T>): Promise<T | undefined> => {
    try { return await operation(); }
    catch (error) { setError(error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': Error: /, '') : String(error)); }
  };

  useEffect(() => {
    if (!window.ptshot) { setError('请从 PTShot 桌面程序打开工作台。'); setBooting(false); return; }
    const stop = window.ptshot.onEvent((event: WorkerEvent) => {
      if (event.type === 'busy') setBusy(Boolean(event.busy));
      if (event.job) setJob(event.job);
      if (event.tools) setTools(event.tools);
      if (event.type === 'log' && event.message) {
        const text = `${new Date().toLocaleTimeString('zh-CN', { hour12: false })}  ${event.message}`;
        logBuffer.current = [...logBuffer.current.slice(-999), text];
        setLogs(logBuffer.current);
      }
    });
    window.ptshot.bootstrap().then(value => {
      setSettings(value.settings); setOutput(value.output); setTheme(value.theme); setTools(value.tools);
    }).catch(error => setError(String(error))).finally(() => setBooting(false));
    return stop;
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    if (booting || !valid(settings) || !window.ptshot) return;
    const timer = setTimeout(() => { window.ptshot.savePreferences({ settings, output, theme }).catch(error => setError(String(error))); }, 350);
    return () => clearTimeout(timer);
  }, [settings, output, theme, booting]);
  useEffect(() => { if (!message) return; const timer = setTimeout(() => setMessage(''), 5000); return () => clearTimeout(timer); }, [message]);
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [logs, showLogs]);

  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => setSettings(s => ({ ...s, [key]: value }));
  const add = (items: Video[]) => setVideos(previous => [...previous, ...items.filter(v => !previous.some(p => p.path === v.path))]);
  const chooseVideos = () => guard(async () => { add(await window.ptshot.chooseVideos()); });
  const chooseFolder = () => guard(async () => { add(await window.ptshot.chooseFolder()); });
  const missing = ENGINES.filter(engine => !tools[engine.name]);
  const captureMissing = missing.filter(engine => engine.name !== 'oxipng');
  const successes = job?.records.filter(record => record.status === 'uploaded') || [];
  const failures = job?.records.filter(record => record.status === 'error' || record.status === 'oversize') || [];
  const done = job?.records.filter(record => ['uploaded', 'error', 'oversize', 'local'].includes(record.status)).length || 0;
  const canStart = videos.length > 0 && !busy && !booting && valid(settings) && Boolean(output);

  async function start() {
    if (captureMissing.length) { setPage('settings'); notify('请先配置截图引擎，或一键安装缺少的依赖'); return; }
    setJob(null); logBuffer.current = []; setLogs([]);
    const result = await guard(() => window.ptshot.start({ videos: videos.map(v => v.path), output, settings }));
    if (result?.job) {
      setJob(result.job); setPage('results');
      notify(`${JOB_LABELS[result.job.state] || result.job.state} · ${result.job.records.length} 张图片`);
    }
  }

  async function copyAll(code = true) {
    const text = code ? bbcode(job) : successes.map(record => record.direct_url).join('\n');
    if (!text) return;
    const copied = await guard(() => window.ptshot.copy(text));
    if (copied) notify(`已复制 ${successes.length} 张图片的${code ? ' BBCode' : '高清直链'}`);
  }

  async function openHistory() {
    const result = await guard(() => window.ptshot.openSession());
    if (result?.job) { setJob(result.job); setPage('results'); notify('历史任务已打开'); }
  }

  async function configureTool(name: string, reset = false) {
    const chosen = reset ? null : await guard(() => window.ptshot.chooseTool(name));
    if (chosen === undefined || (!reset && !chosen)) return;
    const custom = { ...settings.tools };
    if (chosen) custom[name] = chosen; else delete custom[name];
    const next = { ...settings, tools: custom };
    setSettings(next);
    const result = await guard(() => window.ptshot.inspect(next));
    if (result?.tools) setTools(result.tools);
  }

  const header = page === 'workspace' ? { title: '影片截图', subtitle: '保留原始画质，让分享更简单。' }
    : page === 'results' ? { title: '分享这一刻', subtitle: '高清原图直链与 BBCode，一次整理好。' }
    : { title: '工具设置', subtitle: '准备好引擎，剩下的交给 PTShot。' };

  return <div className="app-shell" data-design-system={DESIGN_SYSTEM}>
    <aside className="rail-container">
      <WideNavigationRail aria-label="主导航" selectedKey={page}
        onSelectionChange={setPage} items={[
          { key: 'workspace', label: '截图', icon: 'movie_edit' },
          { key: 'results', label: '结果', icon: 'photo_library', badge: successes.length || false, badgeLabel: `${successes.length} 张已上传` },
          { key: 'settings', label: '设置', icon: 'tune' },
        ]} />
    </aside>

    <div className="main-shell">
      <header className="app-bar">
        <div className="wordmark">PTShot<span>截图 · 优化 · 分享</span></div>
        <div className="app-bar-actions">
          <IconButton aria-label={theme === 'light' ? '切换深色主题' : '切换浅色主题'} onPress={() => setTheme(theme === 'light' ? 'dark' : 'light')}>
            <Icon name={theme === 'light' ? 'dark_mode' : 'light_mode'} />
          </IconButton>
          <IconButton aria-label="查看运行日志" onPress={() => setShowLogs(true)}><Icon name="terminal" /></IconButton>
        </div>
      </header>

      <main className="page-scroll" id="main-content">
        <div className="content-container">
          <div className="page-heading">
            <div><h1>{header.title}</h1><p>{header.subtitle}</p></div>
            {page === 'results' && <Button variant="outlined" icon={<Icon name="history" />} onPress={openHistory} isDisabled={busy}>打开历史任务</Button>}
          </div>

          {booting ? <div className="boot-state"><LoadingIndicator contained aria-label="正在连接截图引擎" /><p>正在连接截图引擎</p></div> : <>
            {page === 'workspace' && <>
              <div className="workspace-grid">
                <div className="queue-column">
                  <Card variant="filled" className={`queue-card ${dragging ? 'is-dragging' : ''}`}
                    onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true); }}
                    onDragLeave={() => setDragging(false)} onDrop={event => {
                      event.preventDefault(); setDragging(false); if (busy) return;
                      guard(async () => { const paths = [...event.dataTransfer.files].map(file => window.ptshot.pathForFile(file)); add(await window.ptshot.importPaths(paths)); });
                    }}>
                    <div className="card-heading"><div className="section-title">影片队列 <span className="count-badge">{videos.length}</span></div>
                      <Button variant="text" icon={<Icon name="folder_open" />} onPress={chooseFolder} isDisabled={busy}>添加文件夹</Button></div>
                    {videos.length === 0 ? <div className="queue-empty">
                      <div className="empty-art" aria-hidden="true"><div className="art-orbit" /><div className="art-frame back"><Icon name="image" /></div><div className="art-frame front"><Icon name="play_arrow" fill /></div><span className="art-spark">✦</span></div>
                      <h2>精彩画面，从这里开始</h2><p>拖入影片，或选择本地文件<br />截图与分享，一步完成。</p>
                      <Button size="s" variant="tonal" icon={<Icon name="add" />} onPress={chooseVideos}>添加影片</Button>
                      <span className="format-note">MKV · MP4 · MOV · AVI · 更多格式</span>
                    </div> : <>
                      <div className="video-list" aria-label="影片队列">
                        {videos.map((video, index) => <div className="video-row" key={video.path}>
                          <div className="video-symbol"><Icon name="video_file" /></div>
                          <div className="video-info"><strong title={video.name}>{video.name}</strong><span title={video.path}>{bytes(video.size)}<i>·</i>{video.path}</span></div>
                          <IconButton aria-label={`移除 ${video.name}`} isDisabled={busy} onPress={() => setVideos(items => items.filter((_, i) => i !== index))}><Icon name="close" /></IconButton>
                        </div>)}
                      </div>
                      <div className="queue-actions"><Button variant="tonal" icon={<Icon name="add" />} onPress={chooseVideos} isDisabled={busy}>继续添加</Button><Button variant="text" onPress={() => setVideos([])} isDisabled={busy}>清空队列</Button></div>
                    </>}
                  </Card>
                  <div className="workflow-strip" aria-label="处理流程">
                    {[['movie_edit', 'Mosaic 截图', '原尺寸画面'], ['compress', '智能无损优化', '仅大于 10 MB'], ['cloud_upload', 'Pixhost 分享', '高清原图直链']].map(([icon, title, description], index) =>
                      <div className="workflow-step" key={title}><span className={`step-icon step-${index}`}><Icon name={icon} /></span><span><strong>{title}</strong><small>{description}</small></span>{index < 2 && <Icon name="chevron_right" className="step-arrow" />}</div>)}
                  </div>
                </div>

                <Card variant="filled" className="settings-card">
                  <div className="section-title">截图配置<Icon name="photo_camera" /></div>
                  <div className="field-section"><span className="field-caption">输出类型</span>
                    <ButtonGroup aria-label="输出类型" variant="connected" selectionMode="single" disallowEmptySelection buttonVariant="tonal"
                      selectedKeys={[settings.mode]} onSelectionChange={keys => update('mode', [...keys][0] as Settings['mode'])} isDisabled={busy}>
                      <ButtonGroupItem id="screenshots" icon="crop_original">原图</ButtonGroupItem>
                      <ButtonGroupItem id="sheet" icon="grid_view">拼图</ButtonGroupItem>
                      <ButtonGroupItem id="both" icon="stacks">两者</ButtonGroupItem>
                    </ButtonGroup>
                  </div>
                  {settings.mode !== 'sheet' && <div className="field-section"><NumberField label="每部影片截图张数" value={settings.count} min={1} max={100} suffix="张" onChange={value => update('count', value)} disabled={busy} /><p className="field-help">均匀截取整部影片，保留原始分辨率。</p></div>}
                  {settings.mode !== 'screenshots' && <div className="field-section grid-fields">
                    <NumberField label="拼图列数" value={settings.cols} min={1} max={12} onChange={v => update('cols', v)} disabled={busy} />
                    <NumberField label="拼图行数" value={settings.rows} min={1} max={12} onChange={v => update('rows', v)} disabled={busy} />
                    <div className="span-two"><NumberField label="拼图目标宽度" value={settings.width} min={320} max={16384} suffix="px" onChange={v => update('width', v)} disabled={busy} /></div>
                    <p className="field-help span-two">含时间戳和影片信息，网格取整可能相差数像素。</p>
                  </div>}
                  <div className="section-divider" />
                  <div className="switch-row"><span><strong>自动上传</strong><small>截图后上传至 Pixhost</small></span><Switch aria-label="自动上传 Pixhost" isSelected={settings.upload} onChange={v => update('upload', v)} checkedIcon="check" isDisabled={busy} /></div>
                  <div className="field-section output-field"><TextField label="保存位置" variant="outlined" value={output} isReadOnly
                    trailingIcon={<IconButton aria-label="选择保存位置" onPress={async () => { const path = await guard(() => window.ptshot.chooseOutput()); if (path) setOutput(path); }} isDisabled={busy}><Icon name="folder_open" /></IconButton>} /></div>
                  <div className="lossless-note"><Icon name="shield" /><p>超过 <strong>10 MB</strong> 才调用 oxipng。<br />不缩小分辨率，不转为有损格式。</p></div>
                </Card>
              </div>

            </>}

            {page === 'results' && <>
              <Card className="results-toolbar" variant="filled"><div className="result-summary"><span className="summary-icon"><Icon name={job?.state === 'completed' ? 'check_circle' : 'photo_library'} /></span><span><strong>{job ? JOB_LABELS[job.state] || job.state : '还没有任务结果'}</strong><small>{job ? `${job.records.length} 张图片 · ${successes.length} 张已上传${failures.length ? ` · ${failures.length} 张待处理` : ''}` : '完成截图后，高清分享链接会出现在这里'}</small></span></div>
                <div className="toolbar-actions"><Button variant="text" icon={<Icon name="folder_open" />} isDisabled={!job} onPress={() => guard(() => window.ptshot.openOutput())}>打开文件夹</Button><Button variant="tonal" icon={<Icon name="refresh" />} isDisabled={busy || !job?.records.some(r => r.status !== 'uploaded')} onPress={async () => { const result = await guard(() => window.ptshot.retry(settings)); if (result?.job) setJob(result.job); }}>上传 / 重试</Button></div>
              </Card>
              {job?.errors.length ? <div className="error-banner"><Icon name="error" /><span>{job.errors.join('；')}</span></div> : null}
              <div className="share-toolbar"><ButtonGroup aria-label="结果视图" variant="connected" selectionMode="single" disallowEmptySelection buttonVariant="tonal" selectedKeys={[resultView]} onSelectionChange={keys => setResultView(String([...keys][0]))}>
                <ButtonGroupItem id="images" icon="grid_view">图片</ButtonGroupItem><ButtonGroupItem id="code" icon="code">BBCode</ButtonGroupItem></ButtonGroup>
                <div className="share-actions"><Button variant="outlined" icon={<Icon name="link" />} isDisabled={!successes.length} onPress={() => copyAll(false)}>复制全部直链</Button><Button variant="filled" icon={<Icon name="content_copy" />} isDisabled={!successes.length} onPress={() => copyAll(true)}>复制全部 BBCode</Button></div>
              </div>
              {!job?.records.length ? <Card variant="filled" className="results-empty"><Brand /><h2>下一帧，值得期待</h2><p>先添加影片。图片、高清直链和分享代码都会保存在同一次任务中。</p><Button variant="tonal" icon={<Icon name="arrow_back" />} onPress={() => setPage('workspace')}>前往截图</Button></Card>
                : resultView === 'code' ? <Card variant="filled" className="code-card"><div className="section-title">本次全部 BBCode<span>{successes.length} 张</span></div><TextField variant="outlined" label="[img] 高清原图直链 [/img]" multiline isReadOnly value={bbcode(job)} className="bbcode-field" /><p className="field-help">仅包含成功上传并通过原图尺寸校验的图片。结果也已自动保存为 bbcode.txt。</p></Card>
                  : <div className="image-grid">{job.records.map((record: ImageRecord, index: number) => <Card as="article" variant="filled" className="image-card" key={record.original_path}>
                    <div className="image-preview">{record.preview_url ? <img src={record.preview_url} alt={`第 ${index + 1} 张截图`} loading="lazy" /> : <Icon name="image" />}<span className="image-index">{String(index + 1).padStart(2, '0')}</span><IconButton aria-label={`打开第 ${index + 1} 张本地图片`} variant="tonal" onPress={() => guard(() => window.ptshot.openImage(index))}><Icon name="open_in_full" /></IconButton></div>
                    <div className="image-body"><strong className="image-name" title={filename(record.original_path)}>{filename(record.original_path)}</strong><span className="image-metadata">{record.width} × {record.height}<i>·</i>{bytes(record.upload_bytes || record.original_bytes)}</span>
                      <div className={`image-status ${record.error ? 'error' : ''}`}><Icon name={record.status === 'uploaded' ? 'check_circle' : record.error ? 'error' : 'image'} /><span>{LABELS[record.status] || record.status}</span></div>
                      {record.error && <p className="record-error">{record.error}</p>}
                      <div className="image-link"><span title={record.direct_url || record.show_url}>{record.direct_url || record.show_url || '完成上传后显示高清直链'}</span><IconButton aria-label={`复制第 ${index + 1} 张高清直链`} isDisabled={record.status !== 'uploaded'} onPress={async () => { if (await guard(() => window.ptshot.copy(record.direct_url))) notify('高清原图直链已复制'); }}><Icon name="content_copy" /></IconButton></div>
                    </div>
                  </Card>)}</div>}
              {job && <p className="saved-note"><Icon name="save" />图片和分享代码已自动保存至 <span title={job.directory}>{job.directory}</span></p>}
            </>}

            {page === 'settings' && <div className="preferences-grid">
              <Card variant="filled" className="engines-card"><div className="card-heading"><div><div className="section-title">引擎与依赖</div><p className="field-help">{5 - missing.length} / 5 项已就绪</p></div><Button variant="tonal" icon={<Icon name="download" />} isDisabled={busy || !missing.length} onPress={async () => { const result = await guard(() => window.ptshot.install(settings)); if (result?.tools) { setTools(result.tools); notify('依赖安装完成'); } }}>安装缺少的依赖</Button></div>
                <div className="engine-list">{ENGINES.map(engine => <div className="engine-row" key={engine.name}><span className="engine-icon"><Icon name={engine.icon} /></span><div className="engine-copy"><strong>{engine.title}<span className={tools[engine.name] ? 'engine-ready' : 'engine-missing'}>{tools[engine.name] ? '已就绪' : '待安装'}</span></strong><small>{engine.description}</small><code title={tools[engine.name] || ''}>{tools[engine.name] || '未发现程序，请选择路径或自动安装'}</code></div><div className="engine-actions"><Button variant="text" isDisabled={busy} onPress={() => configureTool(engine.name)}>选择</Button><IconButton aria-label={`自动检测 ${engine.title}`} isDisabled={busy} onPress={() => configureTool(engine.name, true)}><Icon name="restart_alt" /></IconButton></div></div>)}</div>
                <div className="settings-footer"><Icon name="verified_user" /><p>锁定版本 · SHA-256 校验<br /><span>只安装到工具目录，不修改系统 PATH。</span></p><Button variant="text" icon={<Icon name="refresh" />} isDisabled={busy} onPress={async () => { const result = await guard(() => window.ptshot.inspect(settings)); if (result?.tools) setTools(result.tools); }}>重新检测</Button></div>
              </Card>
              <div className="advanced-column"><Card variant="filled" className="advanced-card"><div className="section-title">上传与优化<Icon name="cloud_upload" /></div><div className="field-section"><span className="field-caption">Pixhost 内容分类</span><ButtonGroup aria-label="内容分类" variant="connected" selectionMode="single" disallowEmptySelection buttonVariant="tonal" selectedKeys={[String(settings.content_type)]} onSelectionChange={keys => update('content_type', Number([...keys][0]))} isDisabled={busy}><ButtonGroupItem id="0">普通内容</ButtonGroupItem><ButtonGroupItem id="1">成人内容</ButtonGroupItem></ButtonGroup></div><NumberField label="oxipng 优化等级" value={settings.optimization} min={0} max={6} onChange={v => update('optimization', v)} disabled={busy} /><p className="field-help">0–6，等级越高，耗时通常越长。</p><NumberField label="图床缩略图尺寸" value={settings.thumbnail_size} min={150} max={500} suffix="px" onChange={v => update('thumbnail_size', v)} disabled={busy} /><p className="field-help">只改变图床缩略图，不影响高清原图。</p></Card>
                <Card variant="filled" className="about-card"><Brand small /><h2>少一点步骤。<br />多一些好画面。</h2><p>Mosaic × oxipng × Pixhost<br />PTShot 0.2.0 · Material 3 Expressive</p><Button variant="text" trailingIcon={<Icon name="arrow_outward" />} onPress={() => guard(() => window.ptshot.openProject())}>查看项目</Button></Card></div>
            </div>}
          </>}
        </div>
      </main>
      {page === 'workspace' && !booting && <div className="persistent-dock"><Card className="action-dock" variant="filled">
        <div className="dock-status"><div className={`status-dot ${busy ? 'active' : ''}`} /><span><strong>{busy ? '正在处理影片' : videos.length ? `已准备 ${videos.length} 部影片` : '等待添加影片'}</strong><small>{busy ? '过程与结果会自动保存' : '本地处理影片，仅上传生成的图片'}</small></span></div>
        <div className="dock-buttons"><Button variant="text" icon={<Icon name="history" />} onPress={openHistory} isDisabled={busy}>历史任务</Button>
          {busy ? <Button size="m" variant="outlined" icon={<Icon name="stop" />} onPress={() => guard(() => window.ptshot.cancel())}>取消任务</Button>
            : <Button size="m" variant="filled" icon={<Icon name={settings.upload ? 'auto_awesome' : 'photo_camera'} />} isDisabled={!canStart} onPress={start}>{settings.upload ? '开始截图并上传' : '开始截图'}</Button>}
        </div>
        {busy && <div className="dock-progress"><LinearProgress shape="wavy" thickness="thick" aria-label="任务处理进度" value={job?.records.length ? done / job.records.length : undefined} /></div>}
      </Card></div>}
      {busy && page !== 'workspace' && <div className="global-progress"><LinearProgress shape="wavy" aria-label="后台任务处理中" /><Button variant="text" onPress={() => guard(() => window.ptshot.cancel())}>取消任务</Button></div>}
      <footer className="app-footer"><span><span className={`tiny-dot ${busy ? 'busy' : ''}`} />{busy ? '正在处理 · 结果自动保存' : '本地处理，原图分享'}</span><span>Mosaic <i>×</i> oxipng <i>×</i> Pixhost</span></footer>
    </div>

    {message && <div className="snackbar-position"><Snackbar dismissAction={<IconButton aria-label="关闭提示" onPress={() => setMessage('')}><Icon name="close" /></IconButton>}>{message}</Snackbar></div>}
    <AlertDialog isOpen={Boolean(error)} onOpenChange={open => { if (!open) setError(''); }} icon="info" headline="请检查一下" confirmButton={<Button variant="text" onPress={() => setError('')}>知道了</Button>}><p>{error}</p></AlertDialog>
    <AlertDialog isOpen={showLogs} onOpenChange={setShowLogs} headline="运行日志" icon="terminal"
      confirmButton={<Button variant="text" onPress={() => setShowLogs(false)}>关闭</Button>}
      dismissButton={<Button variant="text" isDisabled={!logs.length} onPress={async () => { await guard(() => window.ptshot.copy(logs.join('\n'))); notify('运行日志已复制'); }}>复制日志</Button>}>
      <pre className="log-content" ref={logRef}>{logs.join('\n') || '暂无运行日志。添加影片并开始处理后，这里会显示每一步的记录。'}</pre>
    </AlertDialog>
  </div>;
}
