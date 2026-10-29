import type { WebApp } from '@twa-dev/types';
import { act } from '@testing-library/react';
import { vi } from 'vitest';

/** A made-up initData string. Real ones are signed by Telegram and never appear in tests. */
export const FAKE_INIT_DATA = 'query_id=TEST&user=%7B%22id%22%3A42%7D&auth_date=1700000000&hash=deadbeef';

function atLeast(have: string, want: string): boolean {
  const a = have.split('.').map(Number);
  const b = want.split('.').map(Number);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0);
    if (d !== 0) return d > 0;
  }
  return true;
}

export interface TelegramOptions {
  initData?: string;
  languageCode?: string;
  version?: string;
  /** initDataUnsafe.chat_type: set when the app is opened from a chat, absent otherwise. */
  chatType?: 'sender' | 'private' | 'group' | 'supergroup' | 'channel';
  /** Button id the next popups resolve with. */
  popupChoice?: string | null;
  confirm?: boolean;
}

export function installTelegram(opts: TelegramOptions = {}) {
  const mainHandlers = new Set<() => void>();
  const backHandlers = new Set<() => void>();
  const state = { popupChoice: opts.popupChoice === undefined ? 'ok' : opts.popupChoice, confirm: opts.confirm ?? true };
  const version = opts.version ?? '8.0';

  const MainButton = {
    setParams: vi.fn(),
    setText: vi.fn(),
    show: vi.fn(),
    hide: vi.fn(),
    enable: vi.fn(),
    disable: vi.fn(),
    showProgress: vi.fn(),
    hideProgress: vi.fn(),
    onClick: vi.fn((cb: () => void) => void mainHandlers.add(cb)),
    offClick: vi.fn((cb: () => void) => void mainHandlers.delete(cb)),
  };
  const BackButton = {
    show: vi.fn(),
    hide: vi.fn(),
    onClick: vi.fn((cb: () => void) => void backHandlers.add(cb)),
    offClick: vi.fn((cb: () => void) => void backHandlers.delete(cb)),
  };
  const webApp = {
    initData: opts.initData ?? FAKE_INIT_DATA,
    initDataUnsafe: {
      user: { id: 42, first_name: 'Test', language_code: opts.languageCode ?? 'ru' },
      ...(opts.chatType ? { chat_type: opts.chatType } : {}),
    },
    colorScheme: 'light',
    themeParams: {},
    platform: 'android',
    version,
    isVersionAtLeast: (v: string) => atLeast(version, v),
    ready: vi.fn(),
    expand: vi.fn(),
    close: vi.fn(),
    disableVerticalSwipes: vi.fn(),
    onEvent: vi.fn(),
    offEvent: vi.fn(),
    MainButton,
    BackButton,
    HapticFeedback: {
      notificationOccurred: vi.fn(),
      impactOccurred: vi.fn(),
      selectionChanged: vi.fn(),
    },
    showPopup: vi.fn((_p: unknown, cb?: (id?: string) => void) => cb?.(state.popupChoice ?? undefined)),
    showConfirm: vi.fn((_m: string, cb?: (ok: boolean) => void) => cb?.(state.confirm)),
    showAlert: vi.fn((_m: string, cb?: () => void) => cb?.()),
    openLink: vi.fn(),
    openTelegramLink: vi.fn(),
    switchInlineQuery: vi.fn(),
  };
  window.Telegram = { WebApp: webApp as unknown as WebApp };

  return {
    webApp,
    state,
    mainButtonVisible: () => mainHandlers.size > 0,
    /** Press Telegram's main button, as the person would. */
    async clickMain() {
      await act(async () => {
        mainHandlers.forEach((cb) => cb());
      });
    },
    async clickBack() {
      await act(async () => {
        backHandlers.forEach((cb) => cb());
      });
    },
  };
}
