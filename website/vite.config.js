import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        port: 4180,
        host: true,
        strictPort: false,
        allowedHosts: ['chowduck.cn', '.chowduck.cn', 'localhost', '.localhost'],
    },
    preview: {
        allowedHosts: true,
        port: 4180,
    },
});
