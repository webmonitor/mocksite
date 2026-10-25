import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Admin bundle only. Target pages (React/Vue lists) are vendored UMD assets
// served by the site process, not part of this build.
export default defineConfig({
  root: 'admin',
  base: '/',
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./admin/src', import.meta.url)) },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    target: 'es2022',
  },
  server: {
    strictPort: true,
    // Dev server talks to the admin listener; keep both origins distinct so the
    // token is never sent to the site port.
    proxy: {
      '/_admin': {
        target: process.env.MOCKSITE_ADMIN_ORIGIN ?? 'http://127.0.0.1:9001',
        changeOrigin: false,
      },
    },
  },
})
