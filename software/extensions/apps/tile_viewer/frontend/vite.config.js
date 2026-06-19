import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 9230,
    allowedHosts: ['.local'],
    proxy: {
      '/api': {
        target: 'http://localhost:8530',
        changeOrigin: true
      },
      '/socket.io': {
        target: 'http://localhost:8530',
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
