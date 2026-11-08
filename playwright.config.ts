import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests-ui',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:5173', viewport: { width: 1120, height: 820 }, screenshot: 'only-on-failure' },
  reporter: [['list']],
  webServer: { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: !process.env.CI },
});
