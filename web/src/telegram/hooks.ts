import { useEffect, useRef, useState } from 'react';
import type { WebApp } from './webapp';

/** Shows Telegram's back button while `onBack` is set. */
export function useBackButton(tg: WebApp, onBack: (() => void) | null): void {
  const ref = useRef(onBack);
  ref.current = onBack;
  const visible = onBack !== null;
  useEffect(() => {
    const bb = tg.BackButton;
    if (!visible) {
      bb.hide();
      return;
    }
    const handler = () => ref.current?.();
    bb.onClick(handler);
    bb.show();
    return () => {
      bb.offClick(handler);
      bb.hide();
    };
  }, [tg, visible]);
}

export interface MainButtonSpec {
  text: string;
  onClick: () => void;
  progress?: boolean;
  disabled?: boolean;
}

/** Telegram's bottom main button for a form's primary action; hidden when `spec` is null. */
export function useMainButton(tg: WebApp, spec: MainButtonSpec | null): void {
  const ref = useRef<() => void>(() => {});
  ref.current = spec?.onClick ?? (() => {});
  const visible = spec !== null;
  const text = spec?.text ?? '';
  const progress = !!spec?.progress;
  const disabled = !!spec?.disabled;

  useEffect(() => {
    if (!visible) return;
    const mb = tg.MainButton;
    const handler = () => ref.current();
    mb.onClick(handler);
    return () => {
      mb.offClick(handler);
      mb.hideProgress();
      mb.hide();
    };
  }, [tg, visible]);

  useEffect(() => {
    if (!visible) return;
    const mb = tg.MainButton;
    mb.setParams({ text, is_visible: true, is_active: !disabled });
    if (progress) mb.showProgress(false);
    else mb.hideProgress();
  }, [tg, visible, text, progress, disabled]);
}

/** Telegram's light/dark scheme, kept in sync with theme changes. */
export function useColorScheme(tg: WebApp): 'light' | 'dark' {
  const [scheme, setScheme] = useState<'light' | 'dark'>(tg.colorScheme === 'dark' ? 'dark' : 'light');
  useEffect(() => {
    const onTheme = () => setScheme(tg.colorScheme === 'dark' ? 'dark' : 'light');
    tg.onEvent('themeChanged', onTheme);
    return () => tg.offEvent('themeChanged', onTheme);
  }, [tg]);
  return scheme;
}
