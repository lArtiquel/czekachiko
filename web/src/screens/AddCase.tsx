import { useMemo, useRef, useState } from 'react';
import { isApiError } from '../api/client';
import { useApp } from '../app/context';
import { DateField } from '../components/DateField';
import { FieldError, PageTitle } from '../components/common';
import { Group, Page, RadioRow, RowButton, Segmented, TextField } from '../components/ui';
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
  const [clientToken, setClientToken] = useState(newClientToken);
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
      if (isApiError(err) && err.kind === 'invalid' && err.fields.client_token) {
        // Only possible if the token belongs to someone else's case: start over with a new one.
        setClientToken(newClientToken());
        haptic(tg, 'error');
        await alertDialog(tg, t('err_try_again'));
      } else if (isApiError(err) && err.kind === 'invalid') {
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
    <Page>
      <PageTitle>{t('add_title')}</PageTitle>

      <Group title={t('field_voiv')} plain>
        {voivOpen || !voivodeship ? (
          <div className="stack-tight">
            <TextField
              icon="search"
              type="search"
              aria-label={t('voiv_search')}
              placeholder={t('voiv_search')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoComplete="off"
              enterKeyHint="search"
            />
            <div className="card" role="radiogroup" aria-label={t('field_voiv')}>
              {voivs.length === 0 ? <p className="card-pad hint">{t('voiv_search_empty')}</p> : null}
              {voivs.map((v) => (
                <RadioRow
                  key={v.code}
                  name="voivodeship"
                  value={v.code}
                  checked={voivodeship === v.code}
                  onChange={() => pickVoivodeship(v.code)}
                  label={v.label}
                />
              ))}
            </div>
          </div>
        ) : (
          <div className="card">
            <RowButton trailing={null} after={t('change')} onClick={() => setVoivOpen(true)}>
              {labels.voiv(voivodeship)}
            </RowButton>
          </div>
        )}
        <FieldError message={errors.voivodeship} />
      </Group>

      <Group title={t('field_purpose')} plain>
        <div className="card" role="radiogroup" aria-label={t('field_purpose')}>
          {meta.purposes.map((p) => (
            <RadioRow
              key={p.code}
              name="purpose"
              value={p.code}
              checked={purpose === p.code}
              onChange={() => {
                setPurpose(p.code);
                clearError('purpose');
              }}
              label={p.button}
            />
          ))}
        </div>
        <FieldError message={errors.purpose} />
      </Group>

      <Group title={t('field_channel')} plain>
        <Segmented
          name="channel"
          label={t('field_channel')}
          options={meta.channels.map((c) => ({ value: c.code, label: c.label }))}
          value={channel}
          onChange={(code) => {
            setChannel(code);
            clearError('channel');
          }}
        />
        <FieldError message={errors.channel} />
      </Group>

      <Group title={t('field_filed')} plain>
        <DateField
          label={t('field_filed')}
          labelHidden
          min={EARLIEST}
          max={today}
          value={filed}
          error={errors.filed}
          onChange={(value) => {
            setFiled(value);
            clearError('filed');
          }}
        />
      </Group>
    </Page>
  );
}
