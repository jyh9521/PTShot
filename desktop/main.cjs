const { app, BrowserWindow, ipcMain, dialog, clipboard, shell, protocol, net, session } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { createHash } = require('node:crypto');
const readline = require('node:readline');

app.setName('PTShot');
if (process.env.PTSHOT_USER_DATA) app.setPath('userData', path.resolve(process.env.PTSHOT_USER_DATA));
protocol.registerSchemesAsPrivileged([
  { scheme: 'ptshot', privileges: { standard: true, secure: true, supportFetchAPI: true } },
  { scheme: 'ptshot-media', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
]);
const ROOT = app.isPackaged ? path.dirname(app.getAppPath()) : path.resolve(__dirname, '..');
const UI = path.join(app.getAppPath(), 'frontend-dist');
const EXTENSIONS = new Set(['.mkv', '.mp4', '.avi', '.mov', '.m4v', '.webm', '.ts', '.m2ts', '.mpg', '.mpeg', '.wmv', '.flv', '.vob', '.mts', '.mxf', '.ogv']);
const TOOL_NAMES = new Set(['mosaic-cli', 'oxipng', 'ffmpeg', 'ffprobe', 'mediainfo']);
const images = new Map();
let window, active, lastJob, lastResult, quitting = false;
const DEFAULTS = { mode: 'screenshots', count: 6, cols: 4, rows: 4, width: 3840, content_type: 0,
  thumbnail_size: 350, upload: true, optimization: 4, tools: {} };

function mediaJob(job) {
  lastJob = job;
  return { ...job, records: job.records.map((record) => {
    const filename = record.upload_path || record.original_path;
    const token = createHash('sha256').update(filename).digest('hex');
    images.set(token, filename);
    return { ...record, preview_url: `ptshot-media://image/${token}` };
  }) };
}

function send(event) {
  if (event.job) event = { ...event, job: mediaJob(event.job) };
  if (window && !window.isDestroyed()) window.webContents.send('ptshot:event', event);
  return event;
}

function runWorker(request) {
  if (active) throw new Error('当前任务仍在运行');
  const frozen = path.join(ROOT, 'worker', 'PTShotWorker.exe');
  const command = fsSync.existsSync(frozen) ? frozen : (process.env.PTSHOT_PYTHON || 'python');
  const args = fsSync.existsSync(frozen) ? [] : ['-u', '-m', 'ptshot.bridge'];
  const child = spawn(command, args, { cwd: ROOT, windowsHide: true,
    env: { ...process.env, PYTHONUTF8: '1', PTSHOT_ROOT: ROOT }, stdio: ['pipe', 'pipe', 'pipe'] });
  active = child;
  send({ type: 'busy', busy: true });
  let result, error = '', stderr = '';
  const lines = readline.createInterface({ input: child.stdout });
  lines.on('line', (line) => {
    try {
      const message = JSON.parse(line);
      if (message.type === 'result') result = send(message);
      else if (message.type === 'error') { error = message.message; send(message); }
      else send(message);
    } catch { stderr += `Malformed worker output: ${line.slice(0, 200)}\n`; }
  });
  child.stderr.on('data', (data) => { stderr = (stderr + data.toString('utf8')).slice(-16000); });
  return new Promise((resolve, reject) => {
    let settled = false;
    function finish(code, spawnError) {
      if (settled) return;
      settled = true;
      lines.close();
      active = null;
      send({ type: 'busy', busy: false });
      if (quitting) { window?.destroy(); app.quit(); }
      if (spawnError || code !== 0 || error || !result) {
        reject(new Error(error || spawnError?.message || stderr || `Worker exited: ${code}`));
      } else { lastResult = result; resolve(result); }
    }
    child.once('error', (error) => finish(1, error));
    child.once('close', (code) => finish(code));
    child.stdin.on('error', () => {});
    child.stdin.write(JSON.stringify(request) + '\n');
  });
}

async function videoInfo(filenames) {
  const results = [];
  for (const filename of [...new Set(filenames)]) {
    if (typeof filename !== 'string' || !EXTENSIONS.has(path.extname(filename).toLowerCase())) continue;
    const full = path.resolve(filename);
    try {
      const stat = await fs.stat(full);
      if (stat.isFile()) results.push({ path: full, name: path.basename(full), size: stat.size });
    } catch {}
  }
  return results;
}

async function scanFolder(directory) {
  const files = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) continue;
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await scanFolder(filename));
    else if (EXTENSIONS.has(path.extname(filename).toLowerCase())) files.push(filename);
  }
  return files;
}

async function preferences() {
  try { return JSON.parse(await fs.readFile(path.join(app.getPath('userData'), 'preferences.json'), 'utf8')); }
  catch { return {}; }
}

function handle(name, operation) {
  ipcMain.handle(`ptshot:${name}`, async (event, ...args) => {
    if (!event.senderFrame || !event.senderFrame.url.startsWith('ptshot://app/')) throw new Error('Unknown UI origin');
    return operation(...args);
  });
}

app.whenReady().then(async () => {
  protocol.handle('ptshot', async (request) => {
    const url = new URL(request.url);
    const filename = path.resolve(UI, '.' + decodeURIComponent(url.pathname));
    if (url.hostname !== 'app' || !filename.startsWith(UI + path.sep)) return new Response('', { status: 403 });
    try { return await net.fetch(pathToFileURL(filename).href); }
    catch { return new Response('', { status: 404 }); }
  });
  protocol.handle('ptshot-media', async (request) => {
    const token = new URL(request.url).pathname.slice(1);
    const filename = images.get(token);
    if (!filename || path.extname(filename).toLowerCase() !== '.png') return new Response('', { status: 404 });
    try { return await net.fetch(pathToFileURL(filename).href); }
    catch { return new Response('', { status: 404 }); }
  });
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
  window = new BrowserWindow({ width: 1120, height: 820, minWidth: 860, minHeight: 640, show: false,
    title: 'PTShot', backgroundColor: '#f8f7ff', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true,
      nodeIntegration: false, sandbox: true, spellcheck: false } });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => { if (!url.startsWith('ptshot://app/')) event.preventDefault(); });
  window.once('ready-to-show', () => window.show());
  window.on('close', (event) => {
    if (!active) return;
    event.preventDefault();
    const answer = dialog.showMessageBoxSync(window, { type: 'question', buttons: ['继续任务', '保存结果并退出'],
      defaultId: 0, cancelId: 0, message: '当前任务仍在运行', detail: '退出时会取消当前任务，并保存已经完成的结果。' });
    if (answer === 1) { quitting = true; active.stdin.write('{"action":"cancel"}\n'); }
  });
  handle('bootstrap', async () => {
    const saved = await preferences();
    const settings = { ...DEFAULTS, ...saved.settings };
    const result = await runWorker({ action: 'inspect', settings });
    return { version: '0.2.0', settings, output: saved.output || path.join(app.isPackaged ? path.dirname(ROOT) : ROOT, 'output'),
      theme: saved.theme || 'light', tools: result.tools };
  });
  handle('choose-videos', async () => {
    const selected = await dialog.showOpenDialog(window, { title: '添加影片', properties: ['openFile', 'multiSelections'],
      filters: [{ name: '影片', extensions: [...EXTENSIONS].map(x => x.slice(1)) }] });
    return videoInfo(selected.filePaths);
  });
  handle('choose-folder', async () => {
    const selected = await dialog.showOpenDialog(window, { title: '添加影片文件夹', properties: ['openDirectory'] });
    return selected.canceled ? [] : videoInfo(await scanFolder(selected.filePaths[0]));
  });
  handle('import-paths', (paths) => videoInfo(Array.isArray(paths) ? paths.slice(0, 1000) : []));
  handle('choose-output', async () => {
    const selected = await dialog.showOpenDialog(window, { title: '保存位置', properties: ['openDirectory', 'createDirectory'] });
    return selected.filePaths[0] || null;
  });
  handle('choose-tool', async (name) => {
    if (!TOOL_NAMES.has(name)) throw new Error('Unknown tool');
    const selected = await dialog.showOpenDialog(window, { title: `选择 ${name}`, properties: ['openFile'],
      filters: [{ name: '程序', extensions: ['exe'] }] });
    return selected.filePaths[0] || null;
  });
  handle('open-session', async () => {
    if (active) throw new Error('请等待当前任务结束');
    const selected = await dialog.showOpenDialog(window, { title: '打开历史任务', properties: ['openFile'],
      filters: [{ name: '任务记录 session.json', extensions: ['json'] }] });
    if (selected.canceled) return null;
    return runWorker({ action: 'open', session: selected.filePaths[0] });
  });
  handle('start', async (request) => {
    if (!request || !Array.isArray(request.videos) || request.videos.length > 1000 || typeof request.output !== 'string') throw new Error('任务参数异常');
    const videos = await videoInfo(request.videos);
    if (videos.length !== request.videos.length) throw new Error('请检查影片路径和格式');
    return runWorker({ action: 'run', ...request, videos: videos.map(v => v.path) });
  });
  handle('retry', (settings) => {
    if (!lastJob) throw new Error('请先打开或生成任务');
    return runWorker({ action: 'resume', session: path.join(lastJob.directory, 'session.json'), settings });
  });
  handle('cancel', () => { active?.stdin.write('{"action":"cancel"}\n'); return true; });
  handle('inspect', (settings) => runWorker({ action: 'inspect', settings }));
  handle('install', (settings) => runWorker({ action: 'install', settings }));
  handle('preferences', async (value) => {
    const filename = path.join(app.getPath('userData'), 'preferences.json');
    await fs.mkdir(path.dirname(filename), { recursive: true });
    const temporary = filename + '.tmp';
    await fs.writeFile(temporary, JSON.stringify(value, null, 2), 'utf8');
    await fs.rename(temporary, filename);
    return true;
  });
  handle('copy', (text) => { if (typeof text !== 'string' || text.length > 2_000_000) throw new Error('复制内容异常'); clipboard.writeText(text); return true; });
  handle('open-output', () => lastJob ? shell.openPath(lastJob.directory) : Promise.resolve(''));
  handle('open-image', async (index) => {
    if (!Number.isInteger(index) || !lastJob?.records[index]) throw new Error('请先选择图片');
    const record = lastJob.records[index];
    return shell.openPath(record.upload_path || record.original_path);
  });
  handle('open-project', () => shell.openExternal('https://github.com/jyh9521/PTShot'));
  await window.loadURL('ptshot://app/index.html');
});
app.on('window-all-closed', () => { if (!active) app.quit(); });
