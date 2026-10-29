import { useEffect, useState } from 'react';
import { MILESTONES, type CaseDetail, type CaseSummary } from '../api/types';
import { useApp, type Labels } from '../app/context';
import { LoadError, Loading } from '../components/common';
import { Icon } from '../components/icons';
import { Button, Group, Page, Progress, RowButton } from '../components/ui';
import type { TFn } from '../i18n';
import { daysBetween, formatDate, todayIso } from '../lib/dates';
import { useLoad } from '../lib/useLoad';
import { navigate } from '../router';
import { SHARE_BOT_URL, openFeedback, openTelegramLink } from '../telegram/webapp';

export function forecastLine(t: TFn, labels: Labels, detail: CaseDetail | undefined): string | null {
  if (!detail) return null;
  const f = detail.forecast;
  if (!f) return t('fc_all_done');
  const target = labels.milestone(f.target);
  if (f.kind === 'window' && f.likely) return t('fc_short_window', { target, likely: formatDate(f.likely) });
  if (f.kind === 'waited_longer') return t('fc_short_waited', { target });
  return t('fc_short_no_data', { target });
}

export function Home() {
  const { api, tg, t, labels, meta, cache } = useApp();
  const cases = useLoad(() => api.cases(), [api]);
  const [details, setDetails] = useState<Map<number, CaseDetail>>(() => new Map(cache.details));

  // Forecast lines need each case's detail. Fetch the ones not cached yet (at most five).
  useEffect(() => {
    const list = cases.data;
    if (!list) return;
    cache.list = list;
    let live = true;
    const missing = list.filter((c) => !cache.details.has(c.id));
    void Promise.allSettled(missing.map((c) => api.caseDetail(c.id))).then((results) => {
      results.forEach((r) => {
        if (r.status === 'fulfilled') cache.put(r.value);
      });
      if (live) setDetails(new Map(cache.details));
    });
    return () => {
      live = false;
    };
  }, [cases.data, api, cache]);

  const list = cases.data;
  const atLimit = !!list && list.length >= meta.limits.max_cases;

  return (
    <Page>
      <header className="brand">
        <div className="brand-mark" aria-hidden="true">
          🐕
        </div>
        <div className="brand-text">
          <h1 className="brand-name">Czekachiko</h1>
          <p className="brand-sub">{t('menu_title')}</p>
        </div>
      </header>

      <Group title={t('cases_title')} plain footer={atLimit ? t('case_limit', { max: meta.limits.max_cases }) : undefined}>
        {cases.loading && !list ? <Loading /> : null}
        {cases.error && !list ? <LoadError error={cases.error} onRetry={cases.reload} /> : null}
        {list && list.length === 0 ? <p className="card card-pad empty-note">{t('cases_empty')}</p> : null}
        {list && list.length > 0 ? (
          <div className="stack">
            {list.map((c) => (
              <CaseCard key={c.id} c={c} detail={details.get(c.id)} t={t} labels={labels} />
            ))}
          </div>
        ) : null}
        {list && !atLimit ? (
          <Button variant={list.length === 0 ? 'primary' : 'tinted'} icon="plus" wide onClick={() => navigate('/add')}>
            {t('btn_add')}
          </Button>
        ) : null}
      </Group>

      <Group>
        <RowButton icon="chart" onClick={() => navigate('/stats')}>
          {t('btn_stats')}
        </RowButton>
        <RowButton icon="calendar" onClick={() => navigate('/calendars')}>
          {t('btn_calendars')}
        </RowButton>
        <RowButton icon="sliders" onClick={() => navigate('/settings')}>
          {t('btn_settings')}
        </RowButton>
      </Group>

      <Group>
        <RowButton icon="mail" onClick={() => openFeedback(tg)}>
          {t('btn_feedback')}
        </RowButton>
        <RowButton icon="share" onClick={() => openTelegramLink(tg, SHARE_BOT_URL)}>
          {t('btn_share')}
        </RowButton>
      </Group>
    </Page>
  );
}

function CaseCard({ c, detail, t, labels }: { c: CaseSummary; detail: CaseDetail | undefined; t: TFn; labels: Labels }) {
  const filed = c.dates.filed;
  const line = forecastLine(t, labels, detail);
  const done = detail ? detail.forecast === null : false;
  return (
    <button type="button" className="case-card" onClick={() => navigate(`/case/${c.id}`)}>
      <span className="case-card-head">
        <span className="case-card-title">
          {labels.voiv(c.voivodeship)} · {labels.purpose(c.purpose)}
        </span>
        <Icon name="chevronRight" size={18} className="row-trailing" />
      </span>
      {filed ? (
        <span className="case-card-meta">
          <span className="cap">{t('filed_line', { label: labels.milestone('filed'), date: formatDate(filed) })}</span>
          <span className="pill">{t('case_day', { n: Math.max(0, daysBetween(filed, todayIso())) })}</span>
        </span>
      ) : null}
      <MilestoneTrack dates={c.dates} />
      {line ? (
        <span className={`case-card-line${done ? ' is-done' : ''}`}>
          <Icon name={done ? 'check' : 'clock'} size={16} />
          <span>{line}</span>
        </span>
      ) : null}
      <span className="case-card-docs">
        <Icon name="doc" size={16} />
        <span>{t('docs_progress', { done: c.docs_done, total: c.docs_total })}</span>
        <Progress value={c.docs_done} max={c.docs_total} />
      </span>
    </button>
  );
}

/** Six dots, one per milestone, filled once its date is set. The case screen spells them out. */
function MilestoneTrack({ dates }: { dates: CaseSummary['dates'] }) {
  return (
    <span className="mini-track" aria-hidden="true">
      {MILESTONES.map((m) => (
        <span key={m} className={`mini-dot${dates[m] ? ' is-done' : ''}`} />
      ))}
    </span>
  );
}
