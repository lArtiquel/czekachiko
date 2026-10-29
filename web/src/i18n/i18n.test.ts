import { describe, expect, it } from 'vitest';
import { en } from './en';
import { MONTHS, guessLang, translate } from './index';
import { ru } from './ru';

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe('i18n', () => {
  it('RU and EN have identical keys', () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(ru).sort());
  });

  it('every string is non-empty and uses the same placeholders in both languages', () => {
    for (const key of Object.keys(ru) as (keyof typeof ru)[]) {
      expect(ru[key].trim(), key).not.toBe('');
      expect(en[key].trim(), key).not.toBe('');
      expect(placeholders(en[key]), key).toEqual(placeholders(ru[key]));
    }
  });

  it('has twelve months per language', () => {
    expect(MONTHS.ru).toHaveLength(12);
    expect(MONTHS.en).toHaveLength(12);
  });

  it('fills placeholders and leaves unknown ones visible', () => {
    expect(translate('ru', 'doc_limit', { max: 15 })).toBe('Можно добавить не больше 15 своих документов.');
    expect(translate('en', 'doc_limit')).toContain('{max}');
  });

  it('guesses EN only for English Telegram clients', () => {
    expect(guessLang('en-GB')).toBe('en');
    expect(guessLang('ru')).toBe('ru');
    expect(guessLang('uk')).toBe('ru');
    expect(guessLang(undefined)).toBe('ru');
  });
});
