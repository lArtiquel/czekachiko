import { ButtonCell, List, Section } from '@telegram-apps/telegram-ui';
import { useEffect, useState } from 'react';
import type { CaseDetail, CaseSummary } from '../api/types';
import { useApp, type Labels } from '../app/context';
import { LoadError, Loading, PageTitle, TapCell } from '../components/common';
import type { TFn } from '../i18n';
import { formatDate } from '../lib/dates';
import { useLoad } from '../lib/useLoad';
import { navigate } from '../router';
import { BOT_URL, SHARE_BOT_URL, openTelegramLink } from '../telegram/webapp';

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
    <List className="page">
      <PageTitle sub={t('menu_title')}>🐕 Czekachiko</PageTitle>

      <Section header={t('cases_title')} footer={atLimit ? t('case_limit', { max: meta.limits.max_cases }) : undefined}>
        {cases.loading && !list ? <Loading /> : null}
        {cases.error && !list ? <LoadError error={cases.error} onRetry={cases.reload} /> : null}
        {list && list.length === 0 ? <p className="section-text">{t('cases_empty')}</p> : null}
        {list?.map((c) => (
          <CaseCard key={c.id} c={c} detail={details.get(c.id)} t={t} labels={labels} />
        ))}
        {list && !atLimit ? <ButtonCell onClick={() => navigate('/add')}>{t('btn_add')}</ButtonCell> : null}
      </Section>

      <Section>
        <ButtonCell onClick={() => navigate('/stats')}>{t('btn_stats')}</ButtonCell>
        <ButtonCell onClick={() => navigate('/calendars')}>{t('btn_calendars')}</ButtonCell>
        <ButtonCell onClick={() => navigate('/settings')}>{t('btn_settings')}</ButtonCell>
      </Section>

      <Section>
        <ButtonCell onClick={() => openTelegramLink(tg, BOT_URL)}>{t('btn_feedback')}</ButtonCell>
        <ButtonCell onClick={() => openTelegramLink(tg, SHARE_BOT_URL)}>{t('btn_share')}</ButtonCell>
      </Section>
    </List>
  );
}

function CaseCard({ c, detail, t, labels }: { c: CaseSummary; detail: CaseDetail | undefined; t: TFn; labels: Labels }) {
  const filed = c.dates.filed;
  const line = forecastLine(t, labels, detail);
  return (
    <TapCell
      multiline
      onClick={() => navigate(`/case/${c.id}`)}
      subtitle={filed ? t('filed_line', { label: labels.milestone('filed'), date: formatDate(filed) }) : undefined}
      description={
        <>
          {line ? (
            <>
              {line}
              <br />
            </>
          ) : null}
          {t('docs_progress', { done: c.docs_done, total: c.docs_total })}
        </>
      }
    >
      {labels.voiv(c.voivodeship)} · {labels.purpose(c.purpose)}
    </TapCell>
  );
}
