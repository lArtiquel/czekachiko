import type { IsoDate } from '../api/types';
import { EARLIEST, isIsoDate } from './dates';

export interface NewCaseDraft {
  voivodeship: string | null;
  purpose: string | null;
  channel: string | null;
  filed: string;
}

/** Field → error code for the add-case form; empty when it can be sent. */
export function validateNewCase(d: NewCaseDraft, today: IsoDate): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!d.voivodeship) errors.voivodeship = 'required_choice';
  if (!d.purpose) errors.purpose = 'required_choice';
  if (!d.channel) errors.channel = 'required_choice';
  if (!d.filed) errors.filed = 'required_date';
  else if (!isIsoDate(d.filed)) errors.filed = 'invalid';
  else if (d.filed > today) errors.filed = 'future';
  else if (d.filed < EARLIEST) errors.filed = 'before_2015';
  return errors;
}

/** A per-form idempotency key, so a double tap or a retry never creates two cases. */
export function newClientToken(): string {
  const c = globalThis.crypto;
  if (typeof c?.randomUUID === 'function') return c.randomUUID();
  const b = new Uint8Array(16);
  c.getRandomValues(b);
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
