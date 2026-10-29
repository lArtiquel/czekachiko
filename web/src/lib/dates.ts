import type { IsoDate, Lang, Milestone } from '../api/types';
import { MONTHS } from '../i18n';

export const EARLIEST: IsoDate = '2015-01-01';
const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;
const DAY_MS = 86_400_000;

const pad = (n: number) => String(n).padStart(2, '0');

/** Today on the person's device, as YYYY-MM-DD. */
export function todayIso(now: Date = new Date()): IsoDate {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function isIsoDate(s: string): boolean {
  const m = ISO.exec(s);
  if (!m) return false;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const dt = new Date(Date.UTC(y, mo - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d;
}

function utc(iso: IsoDate): number {
  const [y, m, d] = iso.split('-').map(Number);
  return Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

export function daysBetween(from: IsoDate, to: IsoDate): number {
  return Math.round((utc(to) - utc(from)) / DAY_MS);
}

export function addDays(iso: IsoDate, days: number): IsoDate {
  const dt = new Date(utc(iso) + days * DAY_MS);
  return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
}

/** DD.MM.YYYY, as the bot writes dates. */
export function formatDate(iso: IsoDate): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

export function monthSpan(lang: Lang, [from, to]: [IsoDate, IsoDate]): string {
  const name = (iso: IsoDate) => {
    const [y, m] = iso.split('-').map(Number);
    return `${MONTHS[lang][(m ?? 1) - 1]} ${y}`;
  };
  const a = name(from);
  const b = name(to);
  return a === b ? a : `${a} – ${b}`;
}

const ORDERED: readonly Milestone[] = ['fingerprints', 'decision', 'card'];

/** Mirror of `czekachiko.dates.validate_milestones`: error codes, empty when valid. */
export function validateMilestones(
  dates: Partial<Record<Milestone, IsoDate>>,
  today: IsoDate,
): string[] {
  const filed = dates.filed;
  if (!filed) return ['filed_missing'];
  const entries = Object.entries(dates) as [Milestone, IsoDate][];
  const errors: string[] = [];
  if (entries.some(([, d]) => d > today)) errors.push('future');
  if (filed < EARLIEST) errors.push('before_2015');
  if (entries.some(([m, d]) => m !== 'filed' && d < filed)) errors.push('before_filed');
  const chain = ORDERED.map((m) => dates[m]).filter((d): d is IsoDate => !!d);
  if (chain.some((d, i) => i > 0 && chain[i - 1]! > d)) errors.push('order');
  return errors;
}
