/* global process */  // Node 에서 도는 설정 파일 — 브라우저 코드가 아니다
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        // 기본은 로컬 백엔드. 다른 API(예: 격리 테스트 컨테이너)로 붙이려면 API_TARGET=http://127.0.0.1:18001
        target: process.env.API_TARGET || 'http://localhost:8001',
        changeOrigin: true,
      }
    }
  }
})
