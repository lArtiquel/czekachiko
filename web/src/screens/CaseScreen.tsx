import { Button, ButtonCell, Cell, Checkbox, Input, List, Section } from '@telegram-apps/telegram-ui';
import { Fragment, useEffect, useRef, useState, type MouseEvent } from 'react';
import { isApiError } from '../api/client';
import { MILESTONES, type CaseDetail, type CaseDocument, type IsoDate, type Milestone, type OutlierInfo } from '../api/types';
import { useApp } from '../app/context';
import { FieldError, LoadError, Loading, PageTitle, TapCell } from '../components/common';
import type { Params } from '../i18n';
import { EARLIEST, daysBetween, formatDate, todayIso, validateMilestones } from '../lib/dates';
import { DOC_MARGIN_DAYS, cleanDocName, docDateError, earliestDocDate } from '../lib/docs';
import { codeMessage } from '../lib/errors';
import { useLoad } from '../lib/useLoad';
import { navigate } from '../router';
import { useMainButton } from '../telegram/hooks';
import { alertDialog, confirmDialog, haptic, popupDialog, shareInline } from '../telegram/webapp';

type Editing =
  | { kind: 'milestone'; m: Milestone; date: string }
  | { kind: 'doc'; key: string; date: string; name: string }
  | { kind: 'newdoc'; date: string; name: string };

const docKey = (d: CaseDocument) => (d.custom ? `doc:${d.id}` : `std:${d.code}`);

export function CaseScreen({ id }: { id: number }) {
  const { api, cache } = useApp();
  const loaded = useLoad(() => api.caseDetail(id), [api, id]);
  const [detail, setDetail] = useState<CaseDetail | null>(() => cache.details.get(id) ?? null);

  useEffect(() => {
    if (loaded.data) {
      cache.put(loaded.data);
      setDetail(loaded.data);
    }
  }, [loaded.data, cache]);

  if (!detail) {
    if (loaded.error) return <LoadError error={loaded.error} onRetry={loaded.reload} />;
    return <Loading />;
  }
  return <CaseView detail={detail} onChange={setDetail} />;
}

function CaseView({ detail, onChange }: { detail: CaseDetail; onChange: (d: CaseDetail) => void }) {
  const { api, tg, t, meta, labels, cache, fail } = useApp();
  const [editing, setEditing] = useState<Editing | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const today = todayIso();
  const id = detail.id;
  const filed = detail.dates.filed ?? today;
  const docParams: Params = {
    max: meta.limits.max_doc_name,
    date: formatDate(earliestDocDate(filed)),
    days: DOC_MARGIN_DAYS,
  };

  const open = (e: Editing) => {
    setErrors({});
    setEditing(e);
  };
  const close = () => {
    setErrors({});
    setEditing(null);
  };
  const applied = (d: CaseDetail) => {
    cache.put(d);
    onChange(d);
    haptic(tg, 'success');
  };

  /** One action at a time: guards double taps on the main button and the checkboxes. */
  const exclusive = async (action: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      await action();
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const invalid = (err: unknown, field: string, params?: Params): boolean => {
    if (!isApiError(err) || err.kind !== 'invalid') return false;
    const next: Record<string, string> = {};
    for (const [f, codes] of Object.entries(err.fields)) if (codes[0]) next[f] = codeMessage(t, codes[0], params);
    if (err.codes[0]) next[field] = codeMessage(t, err.codes[0], params);
    if (!Object.keys(next).length) next[field] = t('err_invalid');
    setErrors(next);
    haptic(tg, 'error');
    return true;
  };

  const localError = (field: string, code: string, params?: Params) => {
    setErrors({ [field]: codeMessage(t, code, params) });
    haptic(tg, 'error');
  };

  // --- milestones ---------------------------------------------------------

  const outlierText = (o: OutlierInfo) => {
    const common = {
      voiv: labels.voiv(detail.voivodeship),
      p10: Math.round(o.typical.p10),
      p90: Math.round(o.typical.p90),
      value: o.value,
    };
    return o.from && o.to
      ? t('outlier_pair', { ...common, from: labels.milestone(o.from), to: labels.milestone(o.to) })
      : t('outlier_generic', common);
  };

  const saveMilestone = (m: Milestone, date: string) =>
    exclusive(async () => {
      if (!date) return localError('date', 'required_date');
      const codes = validateMilestones({ ...detail.dates, [m]: date }, today);
      if (codes[0]) return localError('date', codes[0]);
      const put = async (confirmOutlier: boolean): Promise<void> => {
        try {
          applied(await api.setMilestone(id, m, date, confirmOutlier));
          close();
        } catch (err) {
          if (isApiError(err) && err.kind === 'outlier' && err.outlier && !confirmOutlier) {
            haptic(tg, 'warning');
            const choice = await popupDialog(tg, {
              title: t('outlier_title'),
              message: outlierText(err.outlier),
              buttons: [
                { id: 'ok', type: 'default', text: t('btn_outlier_ok') },
                { id: 'fix', type: 'default', text: t('btn_outlier_fix') },
              ],
            });
            if (choice === 'ok') await put(true);
            return; // "fix" or dismissed: the editor stays open
          }
          if (!invalid(err, 'date')) fail(err);
        }
      };
      await put(false);
    });

  const clearMilestone = (m: Milestone) =>
    exclusive(async () => {
      try {
        applied(await api.clearMilestone(id, m));
        close();
      } catch (err) {
        if (!invalid(err, 'date')) fail(err);
      }
    });

  // --- documents ----------------------------------------------------------

  const findDoc = (key: string) => detail.documents.find((d) => docKey(d) === key);

  const putDocDate = (doc: CaseDocument, date: IsoDate | null) =>
    doc.custom && doc.id !== null
      ? api.updateDocument(id, doc.id, { date })
      : api.setStandardDocument(id, doc.code ?? '', date);

  const toggleDoc = (doc: CaseDocument) =>
    exclusive(async () => {
      try {
        applied(await putDocDate(doc, doc.date ? null : today));
      } catch (err) {
        fail(err, docParams);
      }
    });

  const saveDoc = (key: string, date: string, rawName: string) =>
    exclusive(async () => {
      const doc = findDoc(key);
      if (!doc) return close();
      if (date) {
        const code = docDateError(date, filed, today);
        if (code) return localError('date', code, docParams);
      }
      let name: string | undefined;
      if (doc.custom) {
        const cleaned = cleanDocName(rawName, meta.limits.max_doc_name);
        if ('error' in cleaned) return localError('name', cleaned.error, docParams);
        if (cleaned.name !== doc.name) name = cleaned.name;
      }
      try {
        const d =
          doc.custom && doc.id !== null
            ? await api.updateDocument(id, doc.id, { ...(name ? { name } : {}), date: date || null })
            : await api.setStandardDocument(id, doc.code ?? '', date || null);
        applied(d);
        close();
      } catch (err) {
        if (!invalid(err, 'date', docParams)) fail(err, docParams);
      }
    });

  const addDoc = (rawName: string, date: string) =>
    exclusive(async () => {
      const cleaned = cleanDocName(rawName, meta.limits.max_doc_name);
      if ('error' in cleaned) return localError('name', cleaned.error, docParams);
      if (date) {
        const code = docDateError(date, filed, today);
        if (code) return localError('date', code, docParams);
      }
      try {
        applied(await api.addDocument(id, { name: cleaned.name, date: date || null }));
        close();
      } catch (err) {
        if (isApiError(err) && err.kind === 'conflict') {
          haptic(tg, 'error');
          await alertDialog(tg, t('doc_limit', { max: meta.limits.max_custom_docs }));
        } else if (!invalid(err, 'name', docParams)) {
          fail(err, docParams);
        }
      }
    });

  const deleteDoc = (doc: CaseDocument) =>
    exclusive(async () => {
      if (doc.id === null) return;
      if (!(await confirmDialog(tg, t('confirm_delete_doc', { name: doc.name })))) return;
      try {
        applied(await api.deleteDocument(id, doc.id));
        close();
      } catch (err) {
        fail(err);
      }
    });

  // --- case ---------------------------------------------------------------

  const share = async () => {
    try {
      const { query } = await api.shareCase(id);
      if (!shareInline(tg, query)) await alertDialog(tg, t('err_share'));
    } catch (err) {
      fail(err);
    }
  };

  const remove = () =>
    exclusive(async () => {
      if (!(await confirmDialog(tg, t('confirm_delete_case')))) return;
      try {
        await api.deleteCase(id);
        cache.drop(id);
        haptic(tg, 'success');
        navigate('/');
      } catch (err) {
        fail(err);
      }
    });

  const submit = () => {
    if (!editing) return;
    if (editing.kind === 'milestone') void saveMilestone(editing.m, editing.date);
    else if (editing.kind === 'doc') void saveDoc(editing.key, editing.date, editing.name);
    else void addDoc(editing.name, editing.date);
  };
  useMainButton(tg, editing ? { text: t('btn_save'), onClick: submit, progress: busy } : null);

  // --- view ---------------------------------------------------------------

  const customCount = detail.documents.filter((d) => d.custom).length;
  const docsDone = detail.docs_done ?? detail.documents.filter((d) => d.date).length;
  const docsTotal = detail.docs_total ?? detail.documents.length;

  return (
    <List className="page">
      <PageTitle sub={`${labels.channel(detail.channel)} · ${t('case_day', { n: Math.max(0, daysBetween(filed, today)) })}`}>
        {labels.voiv(detail.voivodeship)} · {labels.purpose(detail.purpose)}
      </PageTitle>

      <Section header={t('chain_title')} footer={t('timeline_hint')}>
        {MILESTONES.map((m) => {
          const date = detail.dates[m];
          const item = detail.chain.find((c) => c.milestone === m);
          const isEditing = editing?.kind === 'milestone' && editing.m === m;
          let subtitle: string;
          if (m === 'filed') subtitle = date ? formatDate(date) : t('tap_to_set');
          else if (date) subtitle = t('chain_own', { date: formatDate(date), days: item?.own_days ?? daysBetween(filed, date) });
          else subtitle = t('tap_to_set');
          const agg = item?.agg;
          const description =
            m === 'filed'
              ? undefined
              : agg
                ? t('chain_line', { mean: Math.round(agg.mean), min: agg.min, max: agg.max, n: agg.n })
                : t('chain_none');
          return (
            <Fragment key={m}>
              <TapCell
                multiline
                aria-expanded={isEditing}
                before={<span className="mark" aria-hidden="true">{date ? '✅' : '⏳'}</span>}
                subtitle={subtitle}
                description={description}
                onClick={() => (isEditing ? close() : open({ kind: 'milestone', m, date: date ?? '' }))}
              >
                {labels.milestone(m)}
              </TapCell>
              {isEditing ? (
                <div className="editor">
                  <p className="hint">{labels.hint(m)}</p>
                  <Input
                    type="date"
                    aria-label={labels.milestone(m)}
                    status={errors.date ? 'error' : undefined}
                    min={m === 'filed' ? EARLIEST : filed}
                    max={today}
                    value={editing.date}
                    onChange={(e) => setEditing({ ...editing, date: e.target.value })}
                  />
                  <FieldError message={errors.date} />
                  <div className="editor-actions">
                    <Button size="s" mode="gray" onClick={close}>
                      {t('btn_cancel')}
                    </Button>
                    {m !== 'filed' && date ? (
                      <Button size="s" mode="gray" className="danger" disabled={busy} onClick={() => void clearMilestone(m)}>
                        {t('btn_clear_date')}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </Fragment>
          );
        })}
      </Section>

      <Section header={detail.forecast ? t('fc_title', { target: labels.milestone(detail.forecast.target) }) : undefined}>
        <ForecastBlock detail={detail} />
      </Section>

      <Section header={t('docs_title', { done: docsDone, total: docsTotal })} footer={t('docs_note')}>
        <p className="section-text hint">{t('docs_hint')}</p>
        {detail.documents.map((doc) => {
          const key = docKey(doc);
          const isEditing = editing?.kind === 'doc' && editing.key === key;
          const stop = (e: MouseEvent) => e.stopPropagation();
          return (
            <Fragment key={key}>
              <Cell
                multiline
                onClick={() => (isEditing ? close() : open({ kind: 'doc', key, date: doc.date ?? today, name: doc.name }))}
                before={
                  <span onClick={stop}>
                    <Checkbox checked={!!doc.date} aria-label={doc.name} onChange={() => void toggleDoc(doc)} />
                  </span>
                }
                subtitle={doc.date ? t('doc_sent', { date: formatDate(doc.date) }) : t('doc_not_sent')}
              >
                <button type="button" className="text-button wrap" aria-expanded={isEditing}>
                  {doc.name}
                </button>
              </Cell>
              {isEditing ? (
                <div className="editor">
                  {doc.custom ? (
                    <>
                      <Input
                        aria-label={t('doc_name')}
                        status={errors.name ? 'error' : undefined}
                        maxLength={meta.limits.max_doc_name}
                        value={editing.name}
                        onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                      />
                      <FieldError message={errors.name} />
                    </>
                  ) : null}
                  <Input
                    type="date"
                    aria-label={t('doc_date')}
                    status={errors.date ? 'error' : undefined}
                    min={earliestDocDate(filed)}
                    max={today}
                    value={editing.date}
                    onChange={(e) => setEditing({ ...editing, date: e.target.value })}
                  />
                  <FieldError message={errors.date} />
                  <div className="editor-actions">
                    <Button size="s" mode="gray" onClick={close}>
                      {t('btn_cancel')}
                    </Button>
                    {doc.date ? (
                      <Button size="s" mode="gray" disabled={busy} onClick={() => void saveDoc(key, '', editing.name)}>
                        {t('btn_doc_untick')}
                      </Button>
                    ) : null}
                    {doc.custom ? (
                      <Button size="s" mode="gray" className="danger" disabled={busy} onClick={() => void deleteDoc(doc)}>
                        {t('btn_doc_delete')}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </Fragment>
          );
        })}
        {editing?.kind === 'newdoc' ? (
          <div className="editor">
            <Input
              aria-label={t('doc_name')}
              placeholder={t('doc_name_placeholder')}
              status={errors.name ? 'error' : undefined}
              maxLength={meta.limits.max_doc_name}
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            />
            <FieldError message={errors.name} />
            <Input
              type="date"
              aria-label={t('doc_date')}
              status={errors.date ? 'error' : undefined}
              min={earliestDocDate(filed)}
              max={today}
              value={editing.date}
              onChange={(e) => setEditing({ ...editing, date: e.target.value })}
            />
            <FieldError message={errors.date} />
            <div className="editor-actions">
              <Button size="s" mode="gray" onClick={close}>
                {t('btn_cancel')}
              </Button>
            </div>
          </div>
        ) : customCount < meta.limits.max_custom_docs ? (
          <ButtonCell onClick={() => open({ kind: 'newdoc', name: '', date: '' })}>{t('btn_doc_add')}</ButtonCell>
        ) : (
          <p className="section-text hint">{t('doc_limit', { max: meta.limits.max_custom_docs })}</p>
        )}
      </Section>

      <Section>
        <ButtonCell onClick={() => void share()}>{t('btn_send_chat')}</ButtonCell>
        <ButtonCell mode="destructive" disabled={busy} onClick={() => void remove()}>
          {t('btn_delete_case')}
        </ButtonCell>
      </Section>
    </List>
  );
}

function ForecastBlock({ detail }: { detail: CaseDetail }) {
  const { t, labels } = useApp();
  const f = detail.forecast;
  const voiv = labels.voiv(detail.voivodeship);
  const purpose = labels.purpose(detail.purpose);
  let body: string | null = null;
  let basis: string | null = null;
  if (!f) body = t('fc_all_done');
  else if (f.kind === 'no_data') body = t('fc_no_data');
  else if (f.kind === 'waited_longer') body = t('fc_waited_longer', { x: f.waited_longer_than ?? 0, y: f.total ?? 0 });
  else if (f.start && f.end && f.likely) {
    body = t('fc_window', { start: formatDate(f.start), end: formatDate(f.end), likely: formatDate(f.likely) });
    const scope = t(f.scope === 'national' ? 'fc_scope_national' : f.scope === 'voiv_filed' ? 'fc_scope_voiv_filed' : 'fc_scope_voiv', { voiv, purpose });
    basis = t('fc_basis', { n: f.n, scope });
  } else body = t('fc_no_data');
  const extremes =
    f && f.kind !== 'no_data' && f.fastest !== null && f.slowest !== null
      ? t('fc_fastest_slowest', { fastest: f.fastest, slowest: f.slowest })
      : null;
  return (
    <div className="section-text forecast">
      <p className="forecast-main">{body}</p>
      {basis ? <p className="hint">{basis}</p> : null}
      {extremes ? <p className="hint">{extremes}</p> : null}
      <p className="disclaimer">{t('disclaimer')}</p>
    </div>
  );
}

