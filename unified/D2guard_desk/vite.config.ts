import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => ({
  base: mode === 'web' ? '/safe/desk/' : './',
  plugins: [react(), {
    name: 'd2guard-deployment-endpoint',
    enforce: 'pre',
    transform(code, id) {
      if (mode === 'web' && id.replaceAll('\\', '/').endsWith('/src/api/d2guardClient.ts')) {
        return code.replace("export const BASE_URL = 'http://127.0.0.1:8765';", "export const BASE_URL = window.location.origin + '/safe/desk';");
      }
    },
  }],
  define: { __D2GUARD_MANAGED__: JSON.stringify(mode === 'web') },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
  },
}));
