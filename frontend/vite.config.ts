import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // Same origin as the API in development, like nginx in production:
    // cookies stay first-party and no CORS is needed.
    proxy: {
      '/api': process.env.API_URL ?? 'http://localhost:8000',
    },
  },
})
