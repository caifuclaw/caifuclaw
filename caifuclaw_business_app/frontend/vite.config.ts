import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { mkdirSync, writeFileSync } from 'node:fs'
import { isAbsolute, resolve } from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || 'http://127.0.0.1:9999'
  const builtAt = new Date().toISOString()
  const appVersion = env.VITE_APP_VERSION || `${builtAt}-${Math.random().toString(36).slice(2, 10)}`
  let buildOutDir = fileURLToPath(new URL('./dist', import.meta.url))

  return {
    plugins: [
      react(),
      {
        name: 'write-app-version',
        apply: 'build',
        configResolved(config) {
          buildOutDir = isAbsolute(config.build.outDir)
            ? config.build.outDir
            : resolve(config.root, config.build.outDir)
        },
        closeBundle() {
          mkdirSync(buildOutDir, { recursive: true })
          writeFileSync(
            resolve(buildOutDir, 'version.json'),
            `${JSON.stringify({ version: appVersion, builtAt }, null, 2)}\n`,
            'utf-8'
          )
        }
      }
    ],
    define: {
      __APP_VERSION__: JSON.stringify(appVersion)
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': { target: apiTarget, ws: true, changeOrigin: true },
        '/health': apiTarget
      }
    },
    build: {
      target: 'es2022',
      sourcemap: false,
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom', 'zustand'],
            'vendor-antd': ['antd', '@ant-design/icons', '@ant-design/pro-components'],
            'vendor-pdf': ['pdfjs-dist']
          }
        }
      }
    },
    optimizeDeps: {
      include: ['react', 'react-dom', 'wouter', 'antd', 'axios', 'dayjs', 'zustand']
    }
  }
})
