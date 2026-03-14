import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  publicDir: 'public',
  server: {
    host: true,
    port: 9201,
    allowedHosts: ['.local'],
    proxy: {
      '/api': {
        target: 'http://localhost:8500',
        changeOrigin: true
      },
      '/socket.io': {
        target: 'http://localhost:8500',
        changeOrigin: true,
        ws: true
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
