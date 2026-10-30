import { createContext, useContext } from 'react';
import type { Lang } from '../api/types';
import { en } from './en';
import { ru, type Key } from './ru';

export type { Key };
export type Params = Record<string, string | number>;
export type TFn = (key: Key, params?: Params) => string;

export const DICTS: Record<Lang, Record<Key, string>> = { ru, en };

/** Nominative month names, lowercased in text like the bot does. */
export const MONTHS: Record<Lang, readonly string[]> = {
  ru: [
    'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
    'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
  ],
  en: [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ],
};

export const LANG_NAMES: Record<Lang, string> = { ru: 'Русский', en: 'English' };

export function translate(lang: Lang, key: Key, params?: Params): string {
  const text = DICTS[lang][key] ?? DICTS.ru[key];
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}

export function isKey(key: string): key is Key {
  return Object.prototype.hasOwnProperty.call(ru, key);
}

/** RU unless Telegram says the person uses English. The server's saved choice wins later. */
export function guessLang(languageCode: string | undefined): Lang {
  return languageCode?.toLowerCase().startsWith('en') ? 'en' : 'ru';
}

export const LangContext = createContext<Lang>('ru');

export function useT(): TFn {
  const lang = useContext(LangContext);
  return (key, params) => translate(lang, key, params);
}

export type PluralForm = 'one' | 'few' | 'many';

/** Which plural form a count takes: Russian 1 дело · 2 дела · 5 дел; English one and many. */
export function pluralForm(lang: Lang, n: number): PluralForm {
  if (lang === 'en') return n === 1 ? 'one' : 'many';
  const ones = n % 10;
  const tens = n % 100;
  if (ones === 1 && tens !== 11) return 'one';
  if (ones >= 2 && ones <= 4 && (tens < 12 || tens > 14)) return 'few';
  return 'many';
}
