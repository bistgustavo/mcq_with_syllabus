import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the backend, so the browser talks to one
// origin and no CORS setup is needed. In Docker, API_PROXY_TARGET points at
// the backend service.
const target = process.env.API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { '/api': { target, changeOrigin: true } },
  },
  preview: {
    port: 4173,
    proxy: { '/api': { target, changeOrigin: true } },
  },
})
