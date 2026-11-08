import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const state = { copied: '', saved: null as unknown, started: null as unknown, callbacks: [] as ((event: unknown) => void)[] };
    Object.assign(window, { __test: state });
    const settings = { mode: 'screenshots' as const, count: 6, cols: 4, rows: 4, width: 3840, content_type: 0,
      thumbnail_size: 350, upload: true, optimization: 4, tools: {} };
    const tools = Object.fromEntries(['mosaic-cli', 'oxipng', 'ffmpeg', 'ffprobe', 'mediainfo'].map(n => [n, `C:\\PTShot\\${n}.exe`]));
    const records = [1, 2].map((n) => ({ source_video: '影片.mkv', original_path: `C:\\out\\截图_${n}.png`,
      upload_path: `C:\\out\\截图_${n}.png`, original_bytes: 500000, upload_bytes: 500000, width: 1920, height: 1080,
      status: 'uploaded', show_url: `https://pixhost.to/show/1/${n}_sample.png`,
      direct_url: `https://img3.pixhost.to/images/1/${n}_sample.png`, thumbnail_url: '', error: '',
      preview_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1kAAAAASUVORK5CYII=' }));
    const job = { directory: 'C:\\out\\PTShot-test', settings, videos: ['影片.mkv'], records, errors: [],
      state: 'completed', successful_urls: records.map(r => r.direct_url) };
    const result = { type: 'result', job };
    window.ptshot = {
      bootstrap: async () => ({ version: '0.2.0', settings, output: 'D:\\我的截图', theme: 'light', tools }),
      chooseVideos: async () => [{ name: '测试影片.mkv', path: 'D:\\电影\\测试影片.mkv', size: 24_500_000_000 }],
      chooseFolder: async () => [{ name: '第二部影片.mp4', path: 'D:\\电影\\第二部影片.mp4', size: 1_500_000_000 }],
      importPaths: async () => [], pathForFile: () => '', chooseOutput: async () => 'D:\\新截图目录',
      chooseTool: async () => 'C:\\custom\\tool.exe',
      start: async (request) => { state.started = request; return result; },
      openSession: async () => result, retry: async () => result,
      cancel: async () => true, inspect: async () => ({ type: 'result', tools }), install: async () => ({ type: 'result', tools }),
      savePreferences: async (value) => { state.saved = value; return true; },
      copy: async text => { state.copied = text; return true; }, openOutput: async () => '', openImage: async () => '',
      openProject: async () => {}, onEvent: callback => { state.callbacks.push(callback as (event: unknown) => void); return () => {}; },
    };
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '精彩画面，从这里开始' })).toBeVisible();
});

test('actual Expressive library, controls, theme and no remote UI assets', async ({ page }) => {
  await expect(page.locator('[data-design-system="Material 3 Expressive"]')).toBeVisible();
  await expect(page.locator('.m3e-button-group')).toBeVisible();
  await expect(page.locator('.m3e-navigation-item[aria-current="page"]')).toHaveText(/截图/);
  await expect(page.getByRole('button', { name: '开始截图并上传' })).toBeDisabled();
  await expect(page.getByRole('switch', { name: '自动上传 Pixhost' })).toBeChecked();
  await expect(page.locator('.app-bar .design-badge')).toHaveCount(0);
  await expect(page.locator('.rail-container .brand-mark')).toHaveCount(0);
  const faces = await page.evaluate(async () => { await document.fonts.ready; return document.fonts.check('16px "Google Sans Flex"') && document.fonts.check('24px "Material Symbols Rounded"'); });
  expect(faces).toBe(true);
  await page.screenshot({ path: 'build/evidence-ui/workspace-light.png', fullPage: true });
});

test('video add, deduplication, folder and remove', async ({ page }) => {
  await page.getByRole('button', { name: '添加影片', exact: true }).click();
  await expect(page.getByText('测试影片.mkv', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '开始截图并上传' })).toBeEnabled();
  await page.getByRole('button', { name: '继续添加' }).click();
  await expect(page.locator('.video-row')).toHaveCount(1);
  await page.getByRole('button', { name: '添加文件夹' }).click();
  await expect(page.locator('.video-row')).toHaveCount(2);
  await page.getByRole('button', { name: '移除 测试影片.mkv' }).click();
  await expect(page.locator('.video-row')).toHaveCount(1);
});

test('Expressive connected buttons change visible fields and validate numbers', async ({ page }) => {
  await page.getByRole('radio', { name: '拼图', exact: true }).click();
  await expect(page.getByLabel('拼图列数')).toBeVisible();
  await expect(page.getByLabel('每部影片截图张数')).toHaveCount(0);
  await page.getByRole('radio', { name: '两者', exact: true }).click();
  await page.getByLabel('每部影片截图张数').fill('0');
  await expect(page.getByLabel('每部影片截图张数')).toHaveAttribute('aria-invalid', 'true');
  await page.getByLabel('每部影片截图张数').fill('8');
  await expect(page.getByLabel('每部影片截图张数')).not.toHaveAttribute('aria-invalid', 'true');
  await page.screenshot({ path: 'build/evidence-ui/both-settings.png', fullPage: true });
});

test('full batch copy is exact direct-link BBCode and not thumbnails', async ({ page }) => {
  await page.getByRole('button', { name: '添加影片', exact: true }).click();
  await page.getByRole('button', { name: '开始截图并上传' }).click();
  await expect(page.getByRole('heading', { name: '分享这一刻' })).toBeVisible();
  await expect(page.locator('.image-card')).toHaveCount(2);
  await page.getByRole('button', { name: '复制全部 BBCode', exact: true }).click();
  expect(await page.evaluate(() => (window as unknown as { __test: { copied: string } }).__test.copied)).toBe(
    '[img]https://img3.pixhost.to/images/1/1_sample.png[/img]\n[img]https://img3.pixhost.to/images/1/2_sample.png[/img]');
  await page.getByRole('radio', { name: 'BBCode', exact: true }).click();
  await expect(page.getByLabel('[img] 高清原图直链 [/img]')).toHaveValue(/\[img\]https:\/\/img3/);
  await page.screenshot({ path: 'build/evidence-ui/bbcode.png', fullPage: true });
});

test('local-only switch and output picker reach backend', async ({ page }) => {
  await page.getByRole('switch', { name: '自动上传 Pixhost' }).click();
  await page.getByRole('button', { name: '选择保存位置' }).click();
  await expect(page.getByRole('textbox', { name: '保存位置', exact: true })).toHaveValue('D:\\新截图目录');
  await page.getByRole('button', { name: '添加影片', exact: true }).click();
  await page.getByRole('button', { name: '开始截图', exact: true }).click();
  const request = await page.evaluate(() => (window as unknown as { __test: { started: { settings: { upload: boolean }; output: string } } }).__test.started);
  expect(request.settings.upload).toBe(false);
  expect(request.output).toBe('D:\\新截图目录');
});

test('dark theme, dependency settings and accessible icon labels', async ({ page }) => {
  await page.getByRole('button', { name: '切换深色主题' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await expect(page.getByRole('heading', { name: '工具设置' })).toBeVisible();
  await expect(page.getByText('5 / 5 项已就绪', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '安装缺少的依赖' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '自动检测 FFmpeg' })).toBeVisible();
  await page.screenshot({ path: 'build/evidence-ui/settings-dark.png', fullPage: true });
});

test('compact high-DPI layout has no horizontal overflow and actions remain reachable', async ({ page }) => {
  await page.setViewportSize({ width: 860, height: 640 });
  await expect(page.getByRole('button', { name: '开始截图并上传' })).toBeVisible();
  const box = await page.getByRole('button', { name: '开始截图并上传' }).boundingBox();
  expect(box && box.y + box.height <= 640).toBeTruthy();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
  await page.getByRole('button', { name: '开始截图并上传' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'build/evidence-ui/compact.png', fullPage: true });
});

test('keyboard and reduced-motion navigation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: '结果', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: '分享这一刻' })).toBeVisible();
  await page.getByRole('button', { name: '查看运行日志' }).click();
  await expect(page.getByText('暂无运行日志。添加影片并开始处理后，这里会显示每一步的记录。')).toBeVisible();
  await page.getByRole('button', { name: '关闭', exact: true }).click();
});
