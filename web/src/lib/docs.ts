import type { IsoDate } from '../api/types';
import { addDays } from './dates';

/** Same margin as `czekachiko.documents.MARGIN_DAYS`: documents may predate filing by 30 days. */
export const DOC_MARGIN_DAYS = 30;

export function earliestDocDate(filed: IsoDate): IsoDate {
  return addDays(filed, -DOC_MARGIN_DAYS);
}

/** Mirror of `czekachiko.documents.clean_name`: collapse whitespace, drop control characters. */
export function cleanDocName(text: string, max: number): { name: string } | { error: string } {
  const collapsed = text.split(/\s+/).filter(Boolean).join(' ');
  const name = collapsed.replace(/[\u0000-\u001f\u007f-\u009f]/g, '').trim();
  if (!name) return { error: 'doc_name_empty' };
  if (name.length > max) return { error: 'doc_name_long' };
  return { name };
}

export function docDateError(d: IsoDate, filed: IsoDate, today: IsoDate): string | null {
  if (d > today) return 'future';
  if (d < earliestDocDate(filed)) return 'doc_too_early';
  return null;
}
