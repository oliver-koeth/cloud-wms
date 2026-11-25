import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The proxy keeps ERPNext's session cookies at the browser-facing dev origin.
// Production must serve this UI through the future custom Frappe app/reverse proxy.
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_ERPNEXT_URL ?? 'http://localhost:8080',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
