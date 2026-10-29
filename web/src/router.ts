import { useSyncExternalStore } from 'react';

export type Route =
  | { name: 'home' }
  | { name: 'add' }
  | { name: 'case'; id: number }
  | { name: 'stats' }
  | { name: 'calendars' }
  | { name: 'settings' };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, '');
  const caseMatch = /^\/case\/(\d{1,12})$/.exec(path);
  if (caseMatch) return { name: 'case', id: Number(caseMatch[1]) };
  switch (path) {
    case '/add':
      return { name: 'add' };
    case '/stats':
      return { name: 'stats' };
    case '/calendars':
      return { name: 'calendars' };
    case '/settings':
      return { name: 'settings' };
    default:
      // Includes Telegram's launch fragment (#tgWebAppData=...) before it is scrubbed.
      return { name: 'home' };
  }
}

const listeners = new Set<() => void>();

function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener('hashchange', cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener('hashchange', cb);
  };
}

/**
 * Replace, never push: Telegram has its own back button, and a growing browser history
 * would make the desktop clients' iframe navigate in odd ways.
 */
export function navigate(path: string): void {
  const url = `${window.location.pathname}${window.location.search}#${path}`;
  window.history.replaceState(null, '', url);
  listeners.forEach((cb) => cb());
}

/**
 * Telegram passes launch parameters (including the signed initData) in the URL fragment.
 * telegram-web-app.js has already read them by the time our code runs, so drop them from
 * the address to keep initData out of the URL.
 */
export function scrubLaunchHash(): void {
  if (window.location.hash.includes('tgWebApp')) navigate('/');
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return parseHash(hash);
}
