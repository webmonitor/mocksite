import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Admin bundle only. Target pages (React/Vue lists) are vendored UMD assets
// served by the site process, not part of this build.
export default defineConfig({
  root: 'admin',
  base: '/',
  plugins: [react()],
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    target: 'es2022',
  },
  server: {
    strictPort: true,
  },
})
