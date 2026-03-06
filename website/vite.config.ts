import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 4180,
    host: true, // 监听 0.0.0.0，支持局域网访问
    strictPort: false, // 4180 被占用时自动换端口
    allowedHosts: ['chowduck.cn', '.chowduck.cn', 'localhost', '.localhost'],
  },
  preview: {
    allowedHosts: true, // 允许 Tunnel 代理的 Host 头
    port: 4180,
  },
})
