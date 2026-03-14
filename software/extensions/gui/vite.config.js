import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import * as path from 'node:path'
import { resolve } from 'path'
import { readFileSync } from 'node:fs'

export default defineConfig({
  root: './',
  publicDir: './src/lib/assets',
  plugins: [
    vue(),
    {
      name: 'serve-experiment-designer-public',
      configureServer(server) {
        const publicDir = resolve(__dirname, '../apps/experiment_designer/public')
        server.middlewares.use((req, res, next) => {
          // Serve /actions/* and /templates/* from experiment_designer/public/
          for (const prefix of ['/actions/', '/templates/']) {
            if (req.url && req.url.startsWith(prefix)) {
              const filePath = resolve(publicDir, req.url.slice(1))
              try {
                const content = readFileSync(filePath, 'utf-8')
                const isJson = filePath.endsWith('.json')
                res.writeHead(200, { 'Content-Type': isJson ? 'application/json' : 'text/yaml' })
                res.end(content)
                return
              } catch { /* file not found, fall through */ }
            }
          }
          next()
        })
      }
    }
  ],
  resolve: {
    alias: {
      '@babylon_vis': path.resolve(__dirname, '../libs/babylon/src/'),
      '@experiment_designer': path.resolve(__dirname, '../apps/experiment_designer/src/'),
      '@experiment_viewer': path.resolve(__dirname, '../apps/experiment_viewer/src/'),
      'uplot': path.resolve(__dirname, 'node_modules/uplot'),
      'vue': 'vue/dist/vue.esm-bundler.js',
      'events': 'events/'
    },
    // helps when using pnpm / workspaces / symlinked deps
    preserveSymlinks: true
  },
  server: {
    host: true,
    port: 9200,
    allowedHosts: ['.local', 'dale'],
    fs: {
      allow: [
        './',
        '../lib/',
        // ✅ explicitly allow the external source folders
        resolve(__dirname, '../libs/babylon/src/'),
        resolve(__dirname, '../apps/experiment_designer/src/'),
        resolve(__dirname, '../apps/experiment_viewer/src/')
      ]
    }
  },
  optimizeDeps: {
    // ✅ make Vite pre-bundle these (Babylon is large/esm and benefits from this)
    include: [
      '@babylonjs/core',
      '@babylonjs/gui',
      'chart.js/auto',
      'chartjs-adapter-moment',
      'chartjs-plugin-streaming',
      'events',
      'uplot'
    ],
    // ✅ tell Vite to scan the external code too
    entries: [
      resolve(__dirname, './index.html'),
      resolve(__dirname, './app.html'),
      resolve(__dirname, './gui.html'),
      // scan all your babylon source files
      resolve(__dirname, '../libs/babylon/src/**/*.js')
    ]
  },
  build: {
    outDir: '../dist',
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, './index.html'),
        gui: path.resolve(__dirname, './gui.html'),
        app: path.resolve(__dirname, './app.html'),
        'babylon-popup': path.resolve(__dirname, './babylon-popup.html'),
        'camera-popup': path.resolve(__dirname, './camera-popup.html'),
        'map-popup': path.resolve(__dirname, './map-popup.html'),
        'chart-popup': path.resolve(__dirname, './chart-popup.html'),
        'network-popup': path.resolve(__dirname, './network-popup.html'),
        'experiment-designer-popup': path.resolve(__dirname, './experiment-designer-popup.html'),
        'experiment-viewer-popup': path.resolve(__dirname, './experiment-viewer-popup.html'),
      },
      output: {
        dir: path.resolve(__dirname, 'dist')
      }
    }
  }
})