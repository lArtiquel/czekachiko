/** Where the API lives. Shared by the app and vite.config.ts (which builds the CSP from it). */
export const DEFAULT_API_URL = 'https://czekachiko-api.artware.me';

export function apiBase(raw: string | undefined): string {
  const url = (raw ?? '').trim() || DEFAULT_API_URL;
  return url.replace(/\/+$/, '');
}
