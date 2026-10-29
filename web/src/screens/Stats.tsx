import { Button, ButtonCell, Cell, Checkbox, List, Section, Select } from '@telegram-apps/telegram-ui';
import { useEffect, useRef, useState } from 'react';
import type { StatsResponse } from '../api/types';
import { useApp } from '../app/context';
import { FieldError, PageTitle, TapCell } from '../components/common';
import { monthSpan } from '../lib/dates';
import { errorMessage } from '../lib/errors';
import { alertDialog, selectionHaptic, shareInline } from '../telegram/webapp';

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

  return (
    <List className="page">
      <PageTitle>{t('stats_title')}</PageTitle>

      <Section header={t('stats_purpose')}>
        <Select aria-label={t('stats_purpose')} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
          {meta.purposes.map((p) => (
            <option key={p.code} value={p.code}>
              {p.button}
            </option>
          ))}
        </Select>
      </Section>

      <Section
        header={t('stats_voivs', { max: MAX_COMPARE })}
        footer={picking ? <FieldError message={atMax ? t('cmp_limit', { max: MAX_COMPARE }) : undefined} /> : undefined}
      >
        {picking ? (
          <>
            {meta.voivodeships.map((v) => {
              const checked = voivs.includes(v.code);
              return (
                <Cell
                  key={v.code}
                  Component="label"
                  before={
                    <Checkbox
                      name="voivodeships"
                      value={v.code}
                      checked={checked}
                      disabled={!checked && atMax}
                      onChange={() => toggle(v.code)}
                    />
                  }
                >
                  {v.label}
                </Cell>
              );
            })}
            <div className="editor-actions padded">
              <Button size="m" mode="bezeled" stretched disabled={!voivs.length} onClick={() => setPicking(false)}>
                {t('btn_done')}
              </Button>
            </div>
          </>
        ) : (
          <TapCell multiline after={<span className="hint">{t('change')}</span>} onClick={() => setPicking(true)}>
            {summary}
          </TapCell>
        )}
      </Section>

      {voivs.length === 0 ? <p className="section-text hint">{t('cmp_none')}</p> : null}

      {voivs.map((v) => {
        const key = `${purpose}|${v}`;
        const result = results[key];
        return (
          <Section key={key} header={t('stats_group', { voiv: labels.voiv(v), purpose: labels.purpose(purpose) })}>
            {!result ? <p className="section-text hint">{t('loading')}</p> : null}
            {result && 'error' in result ? (
              <div className="section-text">
                <p className="field-error" role="alert">
                  {errorMessage(t, result.error)}
                </p>
                <Button size="s" mode="bezeled" onClick={() => retry(key)}>
                  {t('btn_retry')}
                </Button>
              </div>
            ) : null}
            {result && 'data' in result ? (
              <>
                {result.data.chain.map((item) => (
                  <Cell
                    key={item.milestone}
                    multiline
                    description={
                      item.agg
                        ? t('chain_line', {
                            mean: Math.round(item.agg.mean),
                            min: item.agg.min,
                            max: item.agg.max,
                            n: item.agg.n,
                          })
                        : t('chain_none')
                    }
                  >
                    {labels.milestone(item.milestone)}
                  </Cell>
                ))}
                {result.data.who_now.fingerprints ? (
                  <p className="section-text">{t('who_fp', { span: monthSpan(lang, result.data.who_now.fingerprints) })}</p>
                ) : null}
                {result.data.who_now.decision ? (
                  <p className="section-text">{t('who_dec', { span: monthSpan(lang, result.data.who_now.decision) })}</p>
                ) : null}
              </>
            ) : null}
          </Section>
        );
      })}

      {voivs.length ? (
        <Section footer={t('disclaimer')}>
          <ButtonCell onClick={() => void share()}>{t('btn_send_chat')}</ButtonCell>
        </Section>
      ) : null}
    </List>
  );
}
