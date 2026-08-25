import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Proxying in dev keeps the browser same-origin, so CORS and the SSE
      // stream both work without any special configuration.
      //
      // 127.0.0.1, never "localhost": on Windows, localhost resolves to ::1
      // first, uvicorn binds IPv4 only, and every proxied call eats a ~2s
      // connection-refused retry before falling back. Measured 2043ms vs 3ms.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
