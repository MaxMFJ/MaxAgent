import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: ['chowduck.cn', '.chowduck.cn'],
  },
  preview: {
    allowedHosts: true, // 允许 Tunnel 代理的 Host 头
    port: 4180,
  },
})
