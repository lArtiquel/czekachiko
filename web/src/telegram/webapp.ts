import type { PopupParams, WebApp } from '@twa-dev/types';

export type { WebApp };

export const BOT_URL = 'https://t.me/czekachiko_bot';
export const SHARE_BOT_URL = 'https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fczekachiko_bot';
export const SHARE_CHAT_TYPES: Array<'users' | 'groups' | 'channels'> = ['users', 'groups', 'channels'];

export function getWebApp(): WebApp | undefined {
  return typeof window === 'undefined' ? undefined : window.Telegram?.WebApp;
}

export function supports(tg: WebApp, version: string): boolean {
  try {
    return tg.isVersionAtLeast(version);
  } catch {
    return false;
  }
}

/** Telegram's script prepares the app; call once the first screen is on its way. */
export function boot(tg: WebApp): void {
  tg.ready();
  tg.expand();
  if (supports(tg, '7.7')) tg.disableVerticalSwipes();
}

export function haptic(tg: WebApp, type: 'success' | 'error' | 'warning'): void {
  if (!supports(tg, '6.1')) return;
  try {
    tg.HapticFeedback.notificationOccurred(type);
  } catch {
    // Haptics are a nicety; never fail an action over them.
  }
}

export function selectionHaptic(tg: WebApp): void {
  if (!supports(tg, '6.1')) return;
  try {
    tg.HapticFeedback.selectionChanged();
  } catch {
    // ignore
  }
}

/** Telegram limits popup text to 256 characters. */
const clip = (s: string, max: number) => (s.length > max ? `${s.slice(0, max - 1)}…` : s);

export function confirmDialog(tg: WebApp, message: string): Promise<boolean> {
  if (!supports(tg, '6.2')) return Promise.resolve(window.confirm(message));
  return new Promise((resolve) => tg.showConfirm(clip(message, 256), (ok) => resolve(!!ok)));
}

export function alertDialog(tg: WebApp, message: string): Promise<void> {
  if (!supports(tg, '6.2')) {
    window.alert(message);
    return Promise.resolve();
  }
  return new Promise((resolve) => tg.showAlert(clip(message, 256), () => resolve()));
}

/** Resolves with the id of the pressed button, or null if the popup was dismissed. */
export function popupDialog(tg: WebApp, params: PopupParams): Promise<string | null> {
  const safe: PopupParams = {
    ...params,
    title: params.title === undefined ? undefined : clip(params.title, 64),
    message: clip(params.message, 256),
  };
  return new Promise((resolve) => tg.showPopup(safe, (id) => resolve(id || null)));
}

/**
 * Puts `@czekachiko_bot <query>` into a chat's input field. Normally Telegram first shows its
 * chat picker. When the app was opened from inline mode (`backToChat`), the query goes straight
 * back into the chat the person came from. False if the client can't.
 */
export function shareInline(tg: WebApp, query: string, backToChat = false): boolean {
  if (!supports(tg, '6.7')) return false;
  try {
    if (backToChat) tg.switchInlineQuery(query);
    else tg.switchInlineQuery(query, SHARE_CHAT_TYPES);
    return true;
  } catch {
    return false;
  }
}

export function openTelegramLink(tg: WebApp, url: string): void {
  tg.openTelegramLink(url);
}

/** «Написать нам»: the bot asks for the message in its chat; the app gets out of the way. */
export function openFeedback(tg: WebApp): void {
  tg.openTelegramLink(`${BOT_URL}?start=feedback`);
  tg.close();
}

/** Native controls (date inputs) follow Telegram's light/dark theme. */
export function applyColorScheme(scheme: 'light' | 'dark'): void {
  document.documentElement.style.colorScheme = scheme;
}

/** External links only over https. */
export function openExternal(tg: WebApp, url: string): void {
  if (/^https:\/\//i.test(url)) tg.openLink(url);
}
