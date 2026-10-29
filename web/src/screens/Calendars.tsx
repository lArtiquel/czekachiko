import { useApp } from '../app/context';
import { LoadError, Loading, PageTitle } from '../components/common';
import { Group, Page, RowButton } from '../components/ui';
import { useLoad } from '../lib/useLoad';
import { openExternal } from '../telegram/webapp';

export function Calendars() {
  const { api, tg, t } = useApp();
  const cals = useLoad(() => api.calendars(), [api]);

  return (
    <Page>
      <PageTitle sub={t('calendar_text')}>{t('calendars_title')}</PageTitle>
      {cals.loading ? <Loading /> : null}
      {cals.error ? <LoadError error={cals.error} onRetry={cals.reload} /> : null}
      {cals.data && cals.data.length === 0 ? <p className="card card-pad">{t('calendar_soon')}</p> : null}
      {cals.data && cals.data.length > 0 ? (
        <Group>
          {cals.data.map((c) => (
            <RowButton key={c.voivodeship} icon="calendar" trailing="external" onClick={() => openExternal(tg, c.url)}>
              {c.label}
            </RowButton>
          ))}
        </Group>
      ) : null}
    </Page>
  );
}
