import { defineConfig } from 'vite';
export default defineConfig({
  root: 'frontend',
  base: './',
  build: { outDir: '../frontend-dist', emptyOutDir: true, chunkSizeWarningLimit: 1000 },
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
});
