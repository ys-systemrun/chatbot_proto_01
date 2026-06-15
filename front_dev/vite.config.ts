import { defineConfig } from 'vite'

// Vite dev server がリクエストをバックエンドへ転送する。
// ブラウザから見ると同一オリジンになるため CORS 設定が不要。
export default defineConfig({
  server: {
    host: true,   // Docker コンテナ外からアクセスできるよう 0.0.0.0 でバインド
    port: 5173,
    proxy: {
      // POST /ask, DELETE /session/:id をバックエンドへ転送
      '/ask': {
        target: 'http://app:8000',
        changeOrigin: true,
      },
      '/session': {
        target: 'http://app:8000',
        changeOrigin: true,
      },
    },
  },
})
