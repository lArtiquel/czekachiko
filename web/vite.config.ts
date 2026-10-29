import react from '@vitejs/plugin-react';
import { loadEnv, type Plugin } from 'vite';
import { defineConfig } from 'vitest/config';
import { apiBase } from './src/api/base';

/** Production-only CSP: dev needs inline scripts and websockets for hot reload. */
function contentSecurityPolicy(apiOrigin: string): Plugin {
  const policy = [
    "default-src 'none'",
    "script-src 'self' https://telegram.org",
    // Telegram's script and the UI kit set styles at runtime.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src ${apiOrigin}`,
    "base-uri 'none'",
    "form-action 'none'",
    "object-src 'none'",
  ].join('; ');
  return {
    name: 'czekachiko-csp',
    apply: 'build',
    transformIndexHtml: (html) =>
      html.replace(
        '<!-- csp -->',
        `<meta http-equiv="Content-Security-Policy" content="${policy}" />`,
      ),
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_');
  const apiOrigin = new URL(apiBase(env.VITE_API_URL)).origin;
  return {
    base: '/czekachiko/',
    plugins: [react(), contentSecurityPolicy(apiOrigin)],
    build: { outDir: 'dist', target: 'es2020', sourcemap: false },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
      unstubGlobals: true,
    },
  };
});
