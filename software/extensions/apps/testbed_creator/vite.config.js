import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  publicDir: 'public',
  server: {
    host: true,
    port: 9202,
    allowedHosts: ['.local']
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
