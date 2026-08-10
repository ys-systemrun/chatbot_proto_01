import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/ask': { target: 'http://web_backend:8000', changeOrigin: true },
      '/session': { target: 'http://web_backend:8000', changeOrigin: true },
      '/evaluate_response': { target: 'http://web_backend:8000', changeOrigin: true },
      '/evaluated_messages': {
        target: 'http://web_backend:8000',
        changeOrigin: true,
        bypass(req) {
          // ブラウザのページ遷移はフロントエンドに返す
          if (req.headers.accept?.includes('text/html')) return '/index.html';
        },
      },
      // 管理UI（IMPL-202608060837）: /api/* を web_backend へ転送する。
      // /admin 配下のページパスは Vite の SPA フォールバックで index.html が返るため、
      // /evaluated_messages のような bypass 分岐は不要（ADR-0015 / 要件9.2）。
      '/api': { target: 'http://web_backend:8000', changeOrigin: true },
    },
  },
})
