import { useState } from 'react';
import type { Lang } from '../api/types';
import { useApp } from '../app/context';
import { PageTitle } from '../components/common';
import { Group, Page, RowButton, Segmented } from '../components/ui';
import { LANG_NAMES } from '../i18n';
import { navigate } from '../router';
import { alertDialog, confirmDialog, haptic } from '../telegram/webapp';

const LANGS: Lang[] = ['ru', 'en'];

export function Settings() {
  const { api, tg, t, lang, cache, changeLang, fail } = useApp();
  const [pending, setPending] = useState<Lang | null>(null);
  const [deleting, setDeleting] = useState(false);
  const shown = pending ?? lang;

  const pickLang = async (next: Lang) => {
    if (next === lang || pending) return;
    setPending(next);
    try {
      await changeLang(next);
      haptic(tg, 'success');
    } catch (err) {
      fail(err);
    } finally {
      setPending(null);
    }
  };

  const deleteAll = async () => {
    if (deleting || !(await confirmDialog(tg, t('confirm_delete_all')))) return;
    setDeleting(true);
    try {
      await api.deleteMe();
      cache.clear();
      haptic(tg, 'success');
      await alertDialog(tg, t('all_deleted'));
      navigate('/');
    } catch (err) {
      fail(err);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Page>
      <PageTitle>{t('settings_title')}</PageTitle>

      <Group title={t('lang_title')} plain>
        <Segmented
          name="lang"
          label={t('lang_title')}
          options={LANGS.map((l) => ({ value: l, label: LANG_NAMES[l], lang: l }))}
          value={shown}
          disabled={pending !== null}
          onChange={(l) => void pickLang(l as Lang)}
        />
      </Group>

      <Group title={t('help_title')}>
        <p className="card-pad prose">{t('help')}</p>
      </Group>

      <Group title={t('privacy_title')}>
        <p className="card-pad prose">{t('privacy')}</p>
      </Group>

      <Group>
        <RowButton icon="trash" tone="danger" trailing={null} disabled={deleting} onClick={() => void deleteAll()}>
          {t('btn_delete_all')}
        </RowButton>
      </Group>
    </Page>
  );
}
