import { useEffect, useRef, useState } from 'react';
import { MILESTONES, type Agg, type StatsResponse } from '../api/types';
import { useApp } from '../app/context';
import { FieldError, Loading, PageTitle } from '../components/common';
import { Button, Chip, Group, Page, RowButton, SelectField } from '../components/ui';
import { monthSpan } from '../lib/dates';
import { errorMessage } from '../lib/errors';
import { alertDialog, selectionHaptic, shareInline } from '../telegram/webapp';

const STEPS = MILESTONES.filter((m) => m !== 'filed');

export const MAX_COMPARE = 6;

type Result = { data: StatsResponse } | { error: unknown };

export function Stats() {
  const { api, tg, t, lang, meta, labels, cache, inline, fail } = useApp();
  const first = cache.list?.[0];
  const [purpose, setPurpose] = useState(first?.purpose ?? meta.purposes[0]?.code ?? 'praca');
  const [voivs, setVoivs] = useState<string[]>(first ? [first.voivodeship] : []);
  const [picking, setPicking] = useState(!first);
  const [results, setResults] = useState<Record<string, Result>>({});
  const inFlight = useRef(new Set<string>());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Numbers do not depend on the language, so results are cached per purpose and voivodeship.
  useEffect(() => {
    for (const v of voivs) {
      const key = `${purpose}|${v}`;
      if (results[key] || inFlight.current.has(key)) continue;
      inFlight.current.add(key);
      const settle = (result: Result) => {
        inFlight.current.delete(key);
        if (mounted.current) setResults((r) => ({ ...r, [key]: result }));
      };
      api.stats(v, purpose).then(
        (data) => settle({ data }),
        (error: unknown) => settle({ error }),
      );
    }
  }, [api, purpose, voivs, results]);

  const retry = (key: string) =>
    setResults((r) => {
      const { [key]: _gone, ...rest } = r;
      return rest;
    });

  const toggle = (code: string) => {
    selectionHaptic(tg);
    setVoivs((list) =>
      list.includes(code) ? list.filter((v) => v !== code) : list.length >= MAX_COMPARE ? list : [...list, code],
    );
  };

  const share = async () => {
    try {
      const { query } = await api.shareStats(purpose, voivs);
      if (!shareInline(tg, query, inline)) await alertDialog(tg, t('err_share'));
    } catch (err) {
      fail(err);
    }
  };

  const atMax = voivs.length >= MAX_COMPARE;
  const summary = voivs.length ? voivs.map((v) => labels.voiv(v)).join(', ') : t('stats_voivs_none');
  const keyOf = (v: string) => `${purpose}|${v}`;
  const ready = voivs.flatMap((v) => {
    const r = results[keyOf(v)];
    return r && 'data' in r ? [{ voiv: v, data: r.data }] : [];
  });
  const failed = voivs.flatMap((v) => {
    const r = results[keyOf(v)];
    return r && 'error' in r ? [{ voiv: v, error: r.error }] : [];
  });
  const pending = voivs.some((v) => !results[keyOf(v)]);
  const who = ready.filter((r) => r.data.who_now.fingerprints || r.data.who_now.decision);

  return (
    <Page>
      <PageTitle>{t('stats_title')}</PageTitle>

      <Group title={t('stats_purpose')} plain>
        <SelectField aria-label={t('stats_purpose')} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
          {meta.purposes.map((p) => (
            <option key={p.code} value={p.code}>
              {p.button}
            </option>
          ))}
        </SelectField>
      </Group>

      <Group title={t('stats_voivs', { max: MAX_COMPARE })} plain>
        {picking ? (
          <div className="stack-tight">
            <div className="chips" role="group" aria-label={t('stats_voivs', { max: MAX_COMPARE })}>
              {meta.voivodeships.map((v) => {
                const checked = voivs.includes(v.code);
                return (
                  <Chip
                    key={v.code}
                    name="voivodeships"
                    value={v.code}
                    label={v.label}
                    checked={checked}
                    disabled={!checked && atMax}
                    onChange={() => toggle(v.code)}
                  />
                );
              })}
            </div>
            <FieldError message={atMax ? t('cmp_limit', { max: MAX_COMPARE }) : undefined} />
            <Button wide disabled={!voivs.length} onClick={() => setPicking(false)}>
              {t('btn_done')}
            </Button>
          </div>
        ) : (
          <div className="card">
            <RowButton trailing={null} after={t('change')} onClick={() => setPicking(true)}>
              {summary}
            </RowButton>
          </div>
        )}
      </Group>

      {voivs.length === 0 ? <p className="note">{t('cmp_none')}</p> : null}

      {failed.map(({ voiv, error }) => (
        <div key={voiv} className="card card-pad retry-card">
          <p className="field-error" role="alert">
            {labels.voiv(voiv)}: {errorMessage(t, error)}
          </p>
          <Button small icon="refresh" onClick={() => retry(keyOf(voiv))}>
            {t('btn_retry')}
          </Button>
        </div>
      ))}

      {ready.length ? <p className="note">{t('cmp_legend')}</p> : null}

      {ready.length
        ? STEPS.map((m) => {
            const rows = ready.map(({ voiv, data }) => ({ voiv, agg: data.chain.find((c) => c.milestone === m)?.agg ?? null }));
            const axis = Math.max(1, ...rows.map((r) => r.agg?.max ?? 0));
            return (
              <Group key={m} title={<span className="cap">{labels.milestone(m)}</span>}>
                {rows.map(({ voiv, agg }) => (
                  <CompareRow key={voiv} name={labels.voiv(voiv)} agg={agg} axis={axis} />
                ))}
              </Group>
            );
          })
        : null}

      {pending ? <Loading /> : null}

      {who.length ? (
        <Group title={t('who_title')}>
          {who.map(({ voiv, data }) => (
            <div key={voiv} className="who-row">
              <span className="who-name">{labels.voiv(voiv)}</span>
              {data.who_now.fingerprints ? <p>{t('who_fp', { span: monthSpan(lang, data.who_now.fingerprints) })}</p> : null}
              {data.who_now.decision ? <p>{t('who_dec', { span: monthSpan(lang, data.who_now.decision) })}</p> : null}
            </div>
          ))}
        </Group>
      ) : null}

      {voivs.length ? (
        <Group footer={t('disclaimer')}>
          <RowButton icon="send" tone="accent" trailing={null} onClick={() => void share()}>
            {t('btn_send_chat')}
          </RowButton>
        </Group>
      ) : null}
    </Page>
  );
}

/** One voivodeship's average for a step, with the fastest-to-slowest range on a shared axis. */
function CompareRow({ name, agg, axis }: { name: string; agg: Agg | null; axis: number }) {
  const { t } = useApp();
  const pct = (days: number) => `${Math.min(100, Math.max(0, (days / axis) * 100))}%`;
  return (
    <div className="cmp-row">
      <div className="cmp-head">
        <span className="cmp-name">{name}</span>
        {agg ? <span className="cmp-value">{t('days_n', { n: Math.round(agg.mean) })}</span> : null}
      </div>
      {agg ? (
        <>
          <span className="range" aria-hidden="true">
            <span className="range-span" style={{ left: pct(agg.min), width: `calc(${pct(agg.max)} - ${pct(agg.min)})` }} />
            <span className="range-mean" style={{ left: pct(agg.mean) }} />
          </span>
          <span className="cmp-sub">{t('range_line', { min: agg.min, max: agg.max, n: agg.n })}</span>
        </>
      ) : (
        <span className="cmp-sub">{t('chain_none')}</span>
      )}
    </div>
  );
}
