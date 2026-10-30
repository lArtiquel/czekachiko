import type { Agg } from '../api/types';
import { useApp } from '../app/context';
import { pluralForm } from '../i18n';
import { at, hasBar, labelStyle, stageScale, type Scale } from '../lib/bars';

/** The person's own day on a done stage, or today on the stage the forecast waits for. */
export interface Marker {
  kind: 'you' | 'today';
  days: number;
}

/**
 * One stage's days from filing across cases: a bar from the fastest to the slowest case with
 * the median marked, or a sentence when there are too few cases for a bar. Spans only, so it
 * can sit inside a button. `scale` defaults to the stage's own, widened to take in the marker.
 */
export function StageStats({ agg, marker, scale }: { agg: Agg | null | undefined; marker?: Marker; scale?: Scale | null }) {
  const { t } = useApp();
  if (!agg) return <span className="bar-note">{t('chain_none')}</span>;
  if (!hasBar(agg)) {
    return (
      <span className="bar-note">{agg.n === 1 ? t('bar_few_one', { days: agg.min }) : t('bar_few', { n: agg.n })}</span>
    );
  }
  return <StageBar agg={agg} marker={marker} scale={scale ?? stageScale(agg.min, agg.max, marker ? [marker.days] : [])} />;
}

function StageBar({ agg, marker, scale }: { agg: Agg; marker?: Marker; scale: Scale }) {
  const { t, lang } = useApp();
  const left = at(scale, agg.min);
  const median = agg.median !== undefined ? at(scale, agg.median) : null;
  const mark = marker ? at(scale, marker.days) : null;
  return (
    <span className="bar">
      <span className="bar-top">
        {median !== null ? (
          <span className="bar-label bar-median-label" style={labelStyle(median)}>
            {t('bar_median', { n: agg.median! })}
          </span>
        ) : null}
      </span>
      <span className="bar-track" aria-hidden="true">
        <span className="bar-range" style={{ left: `${left}%`, width: `${at(scale, agg.max) - left}%` }} />
        {median !== null ? <span className="bar-median" style={{ left: `${median}%` }} /> : null}
        {marker && mark !== null ? <span className={`bar-${marker.kind}`} style={{ left: `${mark}%` }} /> : null}
      </span>
      {marker && mark !== null ? (
        <span className="bar-under">
          <span className="bar-label bar-marker-label" style={labelStyle(mark)}>
            {t(marker.kind === 'you' ? 'bar_you' : 'bar_today', { n: marker.days })}
          </span>
        </span>
      ) : null}
      <span className="bar-ends">
        <span>{t('days_n', { n: agg.min })}</span>
        <span>{t(`cases_${pluralForm(lang, agg.n)}`, { n: agg.n })}</span>
        <span>{t('days_n', { n: agg.max })}</span>
      </span>
    </span>
  );
}

/** What the bar's parts mean; `you` adds the person's dot (the case screen). */
export function BarLegend({ you = false }: { you?: boolean }) {
  const { t } = useApp();
  return (
    <ul className="bar-legend" aria-label={t('legend')}>
      <li>
        <span className="legend-range" aria-hidden="true" />
        {t('legend_range')}
      </li>
      <li>
        <span className="legend-median" aria-hidden="true" />
        {t('legend_median')}
      </li>
      {you ? (
        <li>
          <span className="legend-you" aria-hidden="true" />
          {t('legend_you')}
        </li>
      ) : null}
    </ul>
  );
}
