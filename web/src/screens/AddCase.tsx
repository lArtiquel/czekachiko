import { useMemo, useRef, useState } from 'react';
import { isApiError } from '../api/client';
import { useApp } from '../app/context';
import { DateField } from '../components/DateField';
import { FieldError, PageTitle } from '../components/common';
import { Check, Group, Page, RadioRow, RowButton, TextField } from '../components/ui';
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
  // Permit type first, then its basis. Nearly every applicant files for a temporary permit, so
  // it starts selected; a type with a single basis sets the purpose by itself.
  const permitTypes = meta.permit_types;
  const [permitType, setPermitType] = useState<string | null>(permitTypes?.[0]?.code ?? null);
  const [purpose, setPurpose] = useState<string | null>(null);
  const bases = permitTypes?.find((g) => g.code === permitType)?.purposes ?? [];
  const [channel, setChannel] = useState<string | null>(null);
  // In person, fingerprints are usually taken at the counter on the filing day.
  const [fpAtFiling, setFpAtFiling] = useState(true);
  const inPerson = channel === 'in_person';
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

  const pickPermitType = (code: string) => {
    selectionHaptic(tg);
    setPermitType(code);
    const next = permitTypes?.find((g) => g.code === code)?.purposes ?? [];
    setPurpose(next.length === 1 ? next[0]! : null);
    clearError('purpose');
  };

  const pickPurpose = (code: string) => {
    setPurpose(code);
    clearError('purpose');
  };

  const purposeRows = (codes: string[]) =>
    codes.map((code) => (
      <RadioRow
        key={code}
        name="purpose"
        value={code}
        checked={purpose === code}
        onChange={() => pickPurpose(code)}
        label={labels.purposeButton(code)}
      />
    ));

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
        ...(inPerson ? { fingerprints_at_filing: fpAtFiling } : {}),
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

      {permitTypes ? (
        <>
          <Group title={t('field_permit_type')} plain>
            <div className="card" role="radiogroup" aria-label={t('field_permit_type')}>
              {permitTypes.map((g) => (
                <RadioRow
                  key={g.code}
                  name="permit_type"
                  value={g.code}
                  checked={permitType === g.code}
                  onChange={() => pickPermitType(g.code)}
                  label={g.button}
                />
              ))}
            </div>
            {bases.length > 1 ? null : <FieldError message={errors.purpose} />}
          </Group>
          {bases.length > 1 ? (
            <Group title={t('field_basis')} plain>
              <div className="card" role="radiogroup" aria-label={t('field_basis')}>
                {purposeRows(bases)}
              </div>
              <FieldError message={errors.purpose} />
            </Group>
          ) : null}
        </>
      ) : (
        // A server without permit types: the flat list as before.
        <Group title={t('field_purpose')} plain>
          <div className="card" role="radiogroup" aria-label={t('field_purpose')}>
            {purposeRows(meta.purposes.map((p) => p.code))}
          </div>
          <FieldError message={errors.purpose} />
        </Group>
      )}

      <Group title={t('field_channel')} plain>
        <div className="card" role="radiogroup" aria-label={t('field_channel')}>
          {meta.channels.map((c) => (
            <RadioRow
              key={c.code}
              name="channel"
              value={c.code}
              checked={channel === c.code}
              onChange={() => {
                selectionHaptic(tg);
                setChannel(c.code);
                setFpAtFiling(true);
                clearError('channel');
              }}
              label={c.label}
            />
          ))}
        </div>
        {inPerson ? (
          <div className="card">
            <label className="row choice">
              <Check
                aria-label={t('fp_at_filing')}
                checked={fpAtFiling}
                onChange={(e) => setFpAtFiling(e.target.checked)}
              />
              <span className="row-main">
                <span className="row-title">{t('fp_at_filing')}</span>
                <span className="row-detail">{t('fp_at_filing_hint')}</span>
              </span>
            </label>
          </div>
        ) : null}
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
