import { describe, expect, it } from 'vitest';
import { meta } from '../test/fixtures';
import { parseHash } from '../router';
import { addDays, daysBetween, formatDate, monthSpan, validateMilestones } from './dates';
import { cleanDocName, docDateError } from './docs';
import { validateNewCase } from './validation';
import { filterVoivodeships } from './voivSearch';

describe('validateMilestones mirrors the bot', () => {
  const today = '2026-10-29';
  it('accepts a valid chain', () => {
    expect(validateMilestones({ filed: '2025-01-10', fingerprints: '2025-05-01', decision: '2025-09-01' }, today)).toEqual([]);
  });
  it('flags each rule', () => {
    expect(validateMilestones({}, today)).toEqual(['filed_missing']);
    expect(validateMilestones({ filed: '2026-11-01' }, today)).toEqual(['future']);
    expect(validateMilestones({ filed: '2014-12-31' }, today)).toEqual(['before_2015']);
    expect(validateMilestones({ filed: '2025-01-10', case_number: '2025-01-01' }, today)).toEqual(['before_filed']);
    expect(validateMilestones({ filed: '2025-01-10', fingerprints: '2025-06-01', decision: '2025-05-01' }, today)).toEqual(['order']);
  });
});

describe('add-case validation', () => {
  const today = '2026-10-29';
  it('requires every field', () => {
    expect(validateNewCase({ voivodeship: null, purpose: null, channel: null, filed: '' }, today)).toEqual({
      voivodeship: 'required_choice',
      purpose: 'required_choice',
      channel: 'required_choice',
      filed: 'required_date',
    });
  });
  it('bounds the filing date', () => {
    const base = { voivodeship: 'slaskie', purpose: 'praca', channel: 'mos' };
    expect(validateNewCase({ ...base, filed: '2026-10-30' }, today)).toEqual({ filed: 'future' });
    expect(validateNewCase({ ...base, filed: '2014-06-01' }, today)).toEqual({ filed: 'before_2015' });
    expect(validateNewCase({ ...base, filed: '2025-02-30' }, today)).toEqual({ filed: 'invalid' });
    expect(validateNewCase({ ...base, filed: '2015-01-01' }, today)).toEqual({});
  });
});

describe('documents', () => {
  it('cleans names like the bot', () => {
    expect(cleanDocName('  Umowa\n\tnajmu  ', 60)).toEqual({ name: 'Umowa najmu' });
    expect(cleanDocName('   ', 60)).toEqual({ error: 'doc_name_empty' });
    expect(cleanDocName('x'.repeat(61), 60)).toEqual({ error: 'doc_name_long' });
  });
  it('allows dates from 30 days before filing until today', () => {
    expect(docDateError('2024-12-11', '2025-01-10', '2026-10-29')).toBeNull();
    expect(docDateError('2024-12-10', '2025-01-10', '2026-10-29')).toBe('doc_too_early');
    expect(docDateError('2026-10-30', '2025-01-10', '2026-10-29')).toBe('future');
  });
});

describe('dates and search', () => {
  it('formats and counts days', () => {
    expect(formatDate('2025-03-01')).toBe('01.03.2025');
    expect(daysBetween('2025-01-10', '2025-03-01')).toBe(50);
    expect(addDays('2025-01-10', -30)).toBe('2024-12-11');
  });
  it('writes month spans like the bot', () => {
    expect(monthSpan('ru', ['2025-03-01', '2025-04-01'])).toBe('март 2025 – апрель 2025');
    expect(monthSpan('en', ['2025-03-01', '2025-03-01'])).toBe('March 2025');
  });
  it('finds voivodeships by label, Russian name or city', () => {
    const codes = (q: string) => filterVoivodeships(meta.voivodeships, q).map((v) => v.code);
    expect(codes('lodz')).toEqual(['lodzkie']);
    expect(codes('Варшава')).toEqual(['mazowieckie']);
    expect(codes('krak')).toEqual(['malopolskie']);
    expect(codes('')).toHaveLength(16);
  });
  it('parses routes and ignores Telegram launch fragments', () => {
    expect(parseHash('#/case/12')).toEqual({ name: 'case', id: 12 });
    expect(parseHash('#/stats')).toEqual({ name: 'stats' });
    expect(parseHash('#tgWebAppData=query_id%3D1&tgWebAppVersion=8.0')).toEqual({ name: 'home' });
    expect(parseHash('#/case/abc')).toEqual({ name: 'home' });
  });
});
