import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      // stateless / 管理UI のデータAPIはすべて /api/ 名前空間へ揃えたため、この 1 ルールで
      // /api/ask-sl・/api/evaluate_response・/api/evaluated_messages・/api/qa*・/api/tags* を
      // まとめて web_backend へ転送する。ページURL（/・/evaluated_messages・/admin*）は /api を
      // 含まないので Vite の SPA フォールバックが index.html を返す → 衝突しないため、以前の
      // /evaluated_messages に対する Accept ヘッダ bypass 分岐は不要になった（ADR-0042/ADR-0015）。
      '/api': { target: 'http://web_backend:8000', changeOrigin: true },
      // statefull 版（main.py の /ask・/session）。現状ローカルの web_backend は stateless app を
      // 配信するため実運用はしていないが、参照が残るため転送先だけ維持する。
      '/ask': { target: 'http://web_backend:8000', changeOrigin: true },
      '/session': { target: 'http://web_backend:8000', changeOrigin: true },
    },
  },
})
