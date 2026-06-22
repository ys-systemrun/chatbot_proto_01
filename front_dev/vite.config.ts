import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
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
