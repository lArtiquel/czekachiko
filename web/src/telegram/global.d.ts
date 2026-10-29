import type { Telegram } from '@twa-dev/types';

// Same declaration as @telegram-apps/telegram-ui's, so the two agree.
declare global {
  interface Window {
    Telegram?: Telegram;
  }
}

export {};
