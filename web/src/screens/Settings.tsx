import { ButtonCell, Cell, List, Radio, Section } from '@telegram-apps/telegram-ui';
import { useState } from 'react';
import type { Lang } from '../api/types';
import { useApp } from '../app/context';
import { PageTitle } from '../components/common';
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
    <List className="page">
      <PageTitle>{t('settings_title')}</PageTitle>

      <Section header={t('lang_title')}>
        <div role="radiogroup" aria-label={t('lang_title')}>
          {LANGS.map((l) => (
            <Cell
              key={l}
              Component="label"
              before={
                <Radio
                  name="lang"
                  value={l}
                  checked={shown === l}
                  disabled={pending !== null}
                  onChange={() => void pickLang(l)}
                />
              }
            >
              <span lang={l}>{LANG_NAMES[l]}</span>
            </Cell>
          ))}
        </div>
      </Section>

      <Section header={t('help_title')}>
        <p className="section-text">{t('help')}</p>
      </Section>

      <Section header={t('privacy_title')}>
        <p className="section-text">{t('privacy')}</p>
      </Section>

      <Section>
        <ButtonCell mode="destructive" disabled={deleting} onClick={() => void deleteAll()}>
          {t('btn_delete_all')}
        </ButtonCell>
      </Section>
    </List>
  );
}
