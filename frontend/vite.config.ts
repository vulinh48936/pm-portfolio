import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Cổng FE + đích proxy đổi được qua env → chạy song song nhiều instance:
//   PORT=5174 API_TARGET=http://127.0.0.1:8766 npm run dev
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: Number(process.env.PORT) || 5173,
    fs: {
      // Repo root không phải git repo → Vite dò workspace root lên tận '/',
      // thành ra serve được file bất kỳ trên máy (vd /root/.profile) cho client ngoài.
      strict: true,
      allow: ['.'],
    },
    proxy: {
      '/api': {
        // 127.0.0.1 chứ KHÔNG phải 'localhost': Node 17+ resolve localhost ra ::1 (IPv6)
        // trước, trong khi uvicorn mặc định chỉ listen IPv4 → ECONNREFUSED ::1:8765.
        target: process.env.API_TARGET || 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
})
