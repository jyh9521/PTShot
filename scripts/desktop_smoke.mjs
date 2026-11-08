import { _electron as electron, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const packaged = process.argv.includes('--packaged');
const live = process.argv.includes('--live');
const directory = path.join(root, 'build', packaged ? (live ? 'packaged-smoke' : 'packaged-local-smoke') : 'desktop-smoke');
await fs.mkdir(directory, { recursive: true });
const env = { ...process.env, PTSHOT_USER_DATA: path.join(directory, 'user-data') };
delete env.ELECTRON_RUN_AS_NODE;
const application = await electron.launch({
  ...(packaged ? { executablePath: path.join(root, 'dist', 'PTShot-M3E', 'PTShot.exe'), args: [] } : { args: [root] }),
  env,
});
const errors = [];
try {
  const page = await application.firstWindow();
  page.on('pageerror', error => errors.push(error.message));
  await expect(page.getByRole('heading', { name: '精彩画面，从这里开始' })).toBeVisible({ timeout: 30000 });
  await expect(page.locator('.app-bar .design-badge')).toHaveCount(0);
  await expect(page.locator('.rail-container .brand-mark')).toHaveCount(0);
  const initialBounds = await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getSize());
  if (initialBounds[0] !== 1120 || initialBounds[1] !== 820) throw new Error(`Unexpected default size: ${initialBounds}`);
  const startBounds = await page.getByRole('button', { name: '开始截图并上传' }).boundingBox();
  const viewport = await page.evaluate(() => innerHeight);
  if (!startBounds || startBounds.y + startBounds.height > viewport) throw new Error('Primary action clipped');
  await page.screenshot({ path: path.join(directory, 'workspace.png'), scale: 'css' });

  const video = path.join(root, 'build', 'test-media', '测试影片 sample.mp4');
  await fs.access(video);
  await application.evaluate(({ dialog }, input) => {
    dialog.showOpenDialog = async (_window, options) => ({ canceled: false,
      filePaths: [options.title === '保存位置' ? input.output : input.video] });
  }, { video, output: path.join(directory, 'output') });
  const uploadSwitch = page.getByRole('switch', { name: '自动上传 Pixhost' });
  if ((await uploadSwitch.isChecked()) !== live) await uploadSwitch.click();
  await page.getByRole('button', { name: '选择保存位置' }).click();
  await page.getByRole('textbox', { name: '每部影片截图张数' }).fill('2');
  await page.getByRole('button', { name: '添加影片', exact: true }).click();
  await page.getByRole('button', { name: live ? '开始截图并上传' : '开始截图', exact: true }).click();
  await expect(page.getByRole('heading', { name: '分享这一刻' })).toBeVisible({ timeout: 120000 });
  await expect(page.locator('.image-card')).toHaveCount(2);
  await expect.poll(() => page.locator('.image-preview img').evaluateAll(images => images.every(img => img.complete && img.naturalWidth === 1280))).toBe(true);
  await page.screenshot({ path: path.join(directory, 'captured-results.png'), scale: 'css' });

  if (!live) {
    const report = JSON.parse(await fs.readFile(path.join(root, 'build', 'integration', 'REPORT.json'), 'utf8'));
    await application.evaluate(({ dialog }, filename) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [filename] });
    }, report.capture_session);
    await page.getByRole('button', { name: '打开历史任务', exact: true }).click();
    await expect(page.locator('.image-card')).toHaveCount(3);
    await expect(page.getByRole('button', { name: '复制全部 BBCode', exact: true })).toBeEnabled();
  }
  await page.getByRole('button', { name: '复制全部 BBCode', exact: true }).click();
  const copied = await application.evaluate(({ clipboard }) => clipboard.readText());
  const links = copied.split('\n').map(line => {
    const match = /^\[img\](https:\/\/img\d+\.pixhost\.to\/images\/[^\[\]]+)\[\/img\]$/.exec(line);
    if (!match) throw new Error(`Not original-image BBCode: ${line}`);
    return match[1];
  });
  if (links.length !== (live ? 2 : 3)) throw new Error('Clipboard batch count mismatch');
  let originalBytes = false;
  if (live) {
    const sessions = await fs.readdir(path.join(directory, 'output'));
    const sessionPath = path.join(directory, 'output', sessions.sort().at(-1), 'session.json');
    const job = JSON.parse(await fs.readFile(sessionPath, 'utf8'));
    for (const record of job.records) {
      const response = await fetch(record.direct_url);
      if (!response.ok) throw new Error(`Image fetch failed: ${response.status}`);
      const remote = Buffer.from(await response.arrayBuffer());
      const local = await fs.readFile(record.upload_path);
      if (!remote.equals(local)) throw new Error('Uploaded image differs from original PNG');
    }
    originalBytes = true;
  }
  await page.screenshot({ path: path.join(directory, 'share-results.png'), scale: 'css' });
  if (errors.length) throw new Error(errors.join('\n'));
  const report = { packaged, live, default_window: initialBounds, removed_badge: true, removed_rail_decoration: true,
    primary_action_visible: true, capture: '2 real Mosaic PNGs', previews: 'original 1280x720 PNGs loaded',
    clipboard_bbcode: copied, clipboard_lines: links.length, remote_bytes_equal: originalBytes,
    renderer_errors: errors, status: 'PASS' };
  await fs.writeFile(path.join(directory, 'REPORT.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  console.log('DESKTOP PASS');
} finally {
  await application.close();
}
