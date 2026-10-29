import { Cell, Input, List, Radio, Section } from '@telegram-apps/telegram-ui';
import { useMemo, useRef, useState } from 'react';
import { isApiError } from '../api/client';
import { useApp } from '../app/context';
import { FieldError, PageTitle, TapCell } from '../components/common';
import { EARLIEST, todayIso } from '../lib/dates';
import { codeMessage } from '../lib/errors';
import { newClientToken, validateNewCase } from '../lib/validation';
import { filterVoivodeships } from '../lib/voivSearch';
import { navigate } from '../router';
import { useMainButton } from '../telegram/hooks';
import { alertDialog, haptic, selectionHaptic } from '../telegram/webapp';

const FIELDS = ['voivodeship', 'purpose', 'channel', 'filed'] as const;

export function AddCase() {
  const { api, tg, t, meta, labels, cache, fail } = useApp();
  const [clientToken] = useState(newClientToken);
  const [voivodeship, setVoivodeship] = useState<string | null>(null);
  const [voivOpen, setVoivOpen] = useState(true);
  const [query, setQuery] = useState('');
  const [purpose, setPurpose] = useState<string | null>(null);
  const [channel, setChannel] = useState<string | null>(null);
  const [filed, setFiled] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const today = todayIso();

  const voivs = useMemo(() => filterVoivodeships(meta.voivodeships, query), [meta.voivodeships, query]);

  const clearError = (field: string) =>
    setErrors((e) => {
      if (!(field in e)) return e;
      const { [field]: _gone, ...rest } = e;
      return rest;
    });

  const pickVoivodeship = (code: string) => {
    selectionHaptic(tg);
    setVoivodeship(code);
    setVoivOpen(false);
    setQuery('');
    clearError('voivodeship');
  };

  const save = async () => {
    if (savingRef.current) return;
    const draft = { voivodeship, purpose, channel, filed };
    const codes = validateNewCase(draft, today);
    if (Object.keys(codes).length) {
      setErrors(Object.fromEntries(Object.entries(codes).map(([f, c]) => [f, codeMessage(t, c)])));
      if (codes.voivodeship) setVoivOpen(true);
      haptic(tg, 'error');
      return;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      const created = await api.createCase({
        voivodeship: voivodeship!,
        purpose: purpose!,
        channel: channel!,
        filed,
        client_token: clientToken,
      });
      cache.list = null;
      haptic(tg, 'success');
      navigate(`/case/${created.id}`);
    } catch (err) {
      if (isApiError(err) && err.kind === 'invalid') {
        const next: Record<string, string> = {};
        for (const f of FIELDS) {
          const code = err.fields[f]?.[0];
          if (code) next[f] = codeMessage(t, code);
        }
        const loose = err.codes[0];
        if (!Object.keys(next).length) next.filed = codeMessage(t, loose ?? 'invalid');
        setErrors(next);
        haptic(tg, 'error');
      } else if (isApiError(err) && err.kind === 'conflict' && err.code === 'too_many_cases') {
        haptic(tg, 'error');
        await alertDialog(tg, t('case_limit', { max: meta.limits.max_cases }));
      } else {
        fail(err);
      }
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  useMainButton(tg, { text: t('btn_save'), onClick: () => void save(), progress: saving });

  return (
    <List className="page">
      <PageTitle>{t('add_title')}</PageTitle>

      <Section header={t('field_voiv')} footer={<FieldError message={errors.voivodeship} />}>
        {voivOpen || !voivodeship ? (
          <>
            <Input
              type="search"
              aria-label={t('voiv_search')}
              placeholder={t('voiv_search')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoComplete="off"
              enterKeyHint="search"
            />
            {voivs.length === 0 ? <p className="section-text hint">{t('voiv_search_empty')}</p> : null}
            <div role="radiogroup" aria-label={t('field_voiv')}>
              {voivs.map((v) => (
                <Cell
                  key={v.code}
                  Component="label"
                  before={
                    <Radio
                      name="voivodeship"
                      value={v.code}
                      checked={voivodeship === v.code}
                      onChange={() => pickVoivodeship(v.code)}
                    />
                  }
                >
                  {v.label}
                </Cell>
              ))}
            </div>
          </>
        ) : (
          <TapCell after={<span className="hint">{t('change')}</span>} onClick={() => setVoivOpen(true)}>
            {labels.voiv(voivodeship)}
          </TapCell>
        )}
      </Section>

      <Section header={t('field_purpose')} footer={<FieldError message={errors.purpose} />}>
        <div role="radiogroup" aria-label={t('field_purpose')}>
          {meta.purposes.map((p) => (
            <Cell
              key={p.code}
              Component="label"
              multiline
              before={
                <Radio
                  name="purpose"
                  value={p.code}
                  checked={purpose === p.code}
                  onChange={() => {
                    setPurpose(p.code);
                    clearError('purpose');
                  }}
                />
              }
            >
              {p.button}
            </Cell>
          ))}
        </div>
      </Section>

      <Section header={t('field_channel')} footer={<FieldError message={errors.channel} />}>
        <div role="radiogroup" aria-label={t('field_channel')}>
          {meta.channels.map((c) => (
            <Cell
              key={c.code}
              Component="label"
              multiline
              before={
                <Radio
                  name="channel"
                  value={c.code}
                  checked={channel === c.code}
                  onChange={() => {
                    setChannel(c.code);
                    clearError('channel');
                  }}
                />
              }
            >
              {c.label}
            </Cell>
          ))}
        </div>
      </Section>

      <Section header={t('field_filed')} footer={<FieldError message={errors.filed} id="filed-error" />}>
        <Input
          type="date"
          aria-label={t('field_filed')}
          aria-invalid={errors.filed ? true : undefined}
          aria-describedby={errors.filed ? 'filed-error' : undefined}
          status={errors.filed ? 'error' : undefined}
          min={EARLIEST}
          max={today}
          value={filed}
          onChange={(e) => {
            setFiled(e.target.value);
            clearError('filed');
          }}
        />
      </Section>
    </List>
  );
}
