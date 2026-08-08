import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 중에는 FastAPI(8000)로 API와 WebSocket을 그대로 넘긴다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  build: { outDir: 'dist', sourcemap: true },
})
