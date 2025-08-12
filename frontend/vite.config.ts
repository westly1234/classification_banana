import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    dedupe: ['react', 'react-dom'], 
  },
  optimizeDeps: {
    force: true,                 // Vite가 의존성 재번들 강제
    include: ['react', 'react-dom'],
  },
  build: {
    commonjsOptions: { include: [/node_modules/] },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      // 인증
      '/login':           { target: 'http://localhost:10000', changeOrigin: true },
      '/signup':          { target: 'http://localhost:10000', changeOrigin: true },
      // 분석
      '/analyze':         { target: 'http://localhost:10000', changeOrigin: true },
      '/analyze_video':   { target: 'http://localhost:10000', changeOrigin: true },
      // 작업 폴링
      '/tasks':           { target: 'http://localhost:10000', changeOrigin: true },
      // 통계
      '/stats':           { target: 'http://localhost:10000', changeOrigin: true },
      // 결과 파일(동영상)
      '/results':         { target: 'http://localhost:10000', changeOrigin: true },
      // 핑(콜드스타트 웜업용)
      '/ping':            { target: 'http://localhost:10000', changeOrigin: true },
    },
  },
});
