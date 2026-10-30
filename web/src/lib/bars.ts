import type { CSSProperties } from 'react';
import type { Agg } from '../api/types';

/** Fewer cases than this get a sentence, not a bar: a "range" of one case says nothing. */
export const MIN_BAR_N = 5;

/** Days from filing at the bar's left and right edges. */
export interface Scale {
  lo: number;
  hi: number;
}

export const hasBar = (agg: Pick<Agg, 'n'> | null | undefined): boolean => !!agg && agg.n >= MIN_BAR_N;

/**
 * A stage's own scale: from its fastest to its slowest case, widened to take in `extra` days
 * (the person's own day, today) when they fall outside, with a little room at both ends.
 */
export function stageScale(min: number, max: number, extra: number[] = []): Scale {
  const lo = Math.min(min, ...extra);
  const hi = Math.max(max, ...extra);
  const pad = (hi - lo) * 0.06 || 5;
  return { lo: lo - pad, hi: hi + pad };
}

/** One scale for several rows of a stage, so their bars compare; null when none draws a bar. */
export function sharedScale(rows: (Pick<Agg, 'n' | 'min' | 'max'> | null)[]): Scale | null {
  const drawn = rows.filter((r): r is Pick<Agg, 'n' | 'min' | 'max'> => hasBar(r));
  if (!drawn.length) return null;
  return stageScale(Math.min(...drawn.map((r) => r.min)), Math.max(...drawn.map((r) => r.max)));
}

/** Where `days` sits on the bar, in percent, clamped to it. */
export function at(scale: Scale, days: number): number {
  return Math.min(100, Math.max(0, ((days - scale.lo) / (scale.hi - scale.lo)) * 100));
}

/**
 * A label at `pct` percent that never spills past the bar: shifted left by the same share of
 * its own width, so it is centred mid-bar and flush with an end at that end.
 */
export function labelStyle(pct: number): CSSProperties {
  return { left: `${pct}%`, transform: `translateX(-${pct}%)` };
}
