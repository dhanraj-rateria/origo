import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
            '@shared': path.resolve(__dirname, './src/shared'),
            '@entities': path.resolve(__dirname, './src/entities'),
            '@features': path.resolve(__dirname, './src/features'),
        },
    },
    server: {
        port: 5173,
        proxy: {
            '/v1': { target: 'http://localhost:8000', changeOrigin: true },
        },
    },
    build: { sourcemap: true, target: 'es2022' },
});
