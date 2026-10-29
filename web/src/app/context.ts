import { createContext, useContext } from 'react';
import type { ApiClient } from '../api/client';
import type { CaseDetail, CaseSummary, Lang, Meta, Milestone } from '../api/types';
import type { Params, TFn } from '../i18n';
import type { WebApp } from '../telegram/webapp';

/** In-memory, per session. Lets Home show forecast lines without refetching every case. */
export class CaseCache {
  list: CaseSummary[] | null = null;
  readonly details = new Map<number, CaseDetail>();

  put(detail: CaseDetail): void {
    this.details.set(detail.id, detail);
  }
  drop(id: number): void {
    this.details.delete(id);
    if (this.list) this.list = this.list.filter((c) => c.id !== id);
  }
  clear(): void {
    this.list = null;
    this.details.clear();
  }
}

export interface Labels {
  voiv(code: string): string;
  purpose(code: string): string;
  purposeButton(code: string): string;
  channel(code: string): string;
  milestone(code: Milestone): string;
  hint(code: Milestone): string;
}

export function makeLabels(meta: Meta): Labels {
  const find = (list: { code: string; label: string }[], code: string) =>
    list.find((o) => o.code === code)?.label ?? code;
  return {
    voiv: (c) => find(meta.voivodeships, c),
    purpose: (c) => find(meta.purposes, c),
    purposeButton: (c) => meta.purposes.find((p) => p.code === c)?.button ?? find(meta.purposes, c),
    channel: (c) => find(meta.channels, c),
    milestone: (c) => find(meta.milestones, c),
    hint: (c) => meta.milestones.find((m) => m.code === c)?.hint ?? '',
  };
}

export interface AppServices {
  tg: WebApp;
  api: ApiClient;
  lang: Lang;
  meta: Meta;
  labels: Labels;
  t: TFn;
  cache: CaseCache;
  /** Opened from inline mode: shared cards go back into the chat the person came from. */
  inline: boolean;
  /** Route key of the screen Telegram opened the app at; it has no back button. */
  entryKey: string;
  changeLang(lang: Lang): Promise<void>;
  /** Tell the person an action failed: native alert plus error haptic. */
  fail(err: unknown, params?: Params): void;
}

export const AppContext = createContext<AppServices | null>(null);

export function useApp(): AppServices {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp outside AppContext');
  return ctx;
}
