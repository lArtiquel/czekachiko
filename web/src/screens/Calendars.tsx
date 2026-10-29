import { List, Section } from '@telegram-apps/telegram-ui';
import { useApp } from '../app/context';
import { LoadError, Loading, PageTitle, TapCell } from '../components/common';
import { useLoad } from '../lib/useLoad';
import { openExternal } from '../telegram/webapp';

export function Calendars() {
  const { api, tg, t } = useApp();
  const cals = useLoad(() => api.calendars(), [api]);

  return (
    <List className="page">
      <PageTitle sub={t('calendar_text')}>{t('calendars_title')}</PageTitle>
      {cals.loading ? <Loading /> : null}
      {cals.error ? <LoadError error={cals.error} onRetry={cals.reload} /> : null}
      {cals.data && cals.data.length === 0 ? <p className="section-text">{t('calendar_soon')}</p> : null}
      {cals.data && cals.data.length > 0 ? (
        <Section>
          {cals.data.map((c) => (
            <TapCell key={c.voivodeship} after={<span aria-hidden="true">↗</span>} onClick={() => openExternal(tg, c.url)}>
              {c.label}
            </TapCell>
          ))}
        </Section>
      ) : null}
    </List>
  );
}
