import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Разрешить Cloudflare Tunnel (trycloudflare.com) и любые внешние Host при демо
    allowedHosts: true,
    proxy: {
      // Docker: backend:8000 (см. VITE_DEV_PROXY_TARGET в docker-compose)
      // Локально без Docker: http://127.0.0.1:8000
      '/api': {
        target: process.env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // IoT-сервер ЛР №2–4 (порт 8001, т.к. 8000 занят бэкендом WMS)
      '/iot-api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: p => p.replace(/^\/iot-api/, ''),
      },
    },
  },
})