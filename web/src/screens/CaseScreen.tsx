import { useEffect, useRef, useState, type CSSProperties, type MouseEvent, type ReactNode } from 'react';
import { isApiError } from '../api/client';
import { MILESTONES, type CaseDetail, type CaseDocument, type IsoDate, type Milestone, type OutlierInfo } from '../api/types';
import { useApp } from '../app/context';
import { DateField } from '../components/DateField';
import { FieldError, LoadError, Loading, PageTitle } from '../components/common';
import { Icon } from '../components/icons';
import { Button, Check, Group, Page, Progress, RowButton, TextField } from '../components/ui';
import type { Params } from '../i18n';
import { EARLIEST, clampDate, daysBetween, formatDate, todayIso, validateMilestones } from '../lib/dates';
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
  const { api, tg, t, meta, labels, cache, inline, fail } = useApp();
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

  const removeMilestone = async (m: Milestone) => {
    try {
      applied(await api.clearMilestone(id, m));
      close();
    } catch (err) {
      if (!invalid(err, 'date')) fail(err);
    }
  };

  /** Saving a cleared field removes the date; `filed` can't be removed. */
  const canRemove = (m: Milestone) => m !== 'filed' && !!detail.dates[m];

  const saveMilestone = (m: Milestone, date: string) =>
    exclusive(async () => {
      if (!date) return canRemove(m) ? removeMilestone(m) : localError('date', 'required_date');
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
      if (!shareInline(tg, query, inline)) await alertDialog(tg, t('err_share'));
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
  // The main button says what saving will do: a cleared date removes it or unticks the document.
  let mainText = t('btn_save');
  if (editing?.kind === 'milestone' && !editing.date && canRemove(editing.m)) mainText = t('btn_remove_date');
  if (editing?.kind === 'doc' && !editing.date) {
    const doc = findDoc(editing.key);
    if (doc?.date && (!doc.custom || editing.name === doc.name)) mainText = t('btn_doc_untick');
  }
  useMainButton(tg, editing ? { text: mainText, onClick: submit, progress: busy } : null);

  // --- view ---------------------------------------------------------------

  const customCount = detail.documents.filter((d) => d.custom).length;
  const docsDone = detail.docs_done ?? detail.documents.filter((d) => d.date).length;
  const docsTotal = detail.docs_total ?? detail.documents.length;
  const stop = (e: MouseEvent) => e.stopPropagation();

  return (
    <Page>
      <PageTitle
        sub={labels.channel(detail.channel)}
        aside={<span className="pill">{t('case_day', { n: Math.max(0, daysBetween(filed, today)) })}</span>}
      >
        {labels.voiv(detail.voivodeship)} · {labels.purpose(detail.purpose)}
      </PageTitle>

      <ForecastCard detail={detail} today={today} />
      <p className="note note-attached">
        <Icon name="info" size={16} />
        <span>{t('disclaimer')}</span>
      </p>

      <Group title={t('chain_title')} footer={t('timeline_hint')}>
        <Timeline
          detail={detail}
          today={today}
          editingMilestone={editing?.kind === 'milestone' ? editing.m : null}
          onToggle={(m) =>
            editing?.kind === 'milestone' && editing.m === m
              ? close()
              : open({
                  kind: 'milestone',
                  m,
                  date: detail.dates[m] ?? clampDate(today, m === 'filed' ? EARLIEST : filed, today),
                })
          }
          renderEditor={(m) =>
            editing?.kind === 'milestone' && editing.m === m ? (
              <div className="editor">
                <DateField
                  label={labels.milestone(m)}
                  labelHidden
                  hint={labels.hint(m)}
                  min={m === 'filed' ? EARLIEST : filed}
                  max={today}
                  value={editing.date}
                  error={errors.date}
                  clearable={m !== 'filed'}
                  onChange={(date) => setEditing({ ...editing, date })}
                />
                <div className="editor-actions">
                  <Button variant="plain" small onClick={close}>
                    {t('btn_cancel')}
                  </Button>
                </div>
              </div>
            ) : null
          }
        />
      </Group>

      <Group
        title={t('docs_heading')}
        aside={
          <span className="docs-count">
            <span>{t('docs_count', { done: docsDone, total: docsTotal })}</span>
            <Progress value={docsDone} max={docsTotal} />
          </span>
        }
        footer={
          <>
            <p>{t('docs_hint')}</p>
            <p>{t('docs_note')}</p>
          </>
        }
      >
        <ul className="checklist">
          {detail.documents.map((doc) => {
            const key = docKey(doc);
            const isEditing = editing?.kind === 'doc' && editing.key === key;
            const toggleEditor = () =>
              isEditing ? close() : open({ kind: 'doc', key, date: doc.date ?? today, name: doc.name });
            return (
              <li key={key} className={`check-item${doc.date ? ' is-done' : ''}`}>
                <div className="check-row" onClick={toggleEditor}>
                  <label className="check-hit" onClick={stop}>
                    <Check checked={!!doc.date} aria-label={doc.name} onChange={() => void toggleDoc(doc)} />
                  </label>
                  <span className="check-text">
                    <button type="button" className="text-button check-name" aria-expanded={isEditing}>
                      {doc.name}
                    </button>
                    <span className="check-sub">
                      {doc.date ? t('doc_sent', { date: formatDate(doc.date) }) : t('doc_not_sent')}
                    </span>
                  </span>
                  <Icon name="pencil" size={16} className="row-trailing" />
                </div>
                {isEditing ? (
                  <div className="editor editor-doc">
                    {doc.custom ? (
                      <div className="field-block">
                        <label className="field-label" htmlFor={`doc-name-${key}`}>
                          {t('doc_name')}
                        </label>
                        <TextField
                          id={`doc-name-${key}`}
                          invalid={!!errors.name}
                          maxLength={meta.limits.max_doc_name}
                          value={editing.name}
                          onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                        />
                        <FieldError message={errors.name} />
                      </div>
                    ) : null}
                    <DateField
                      label={t('doc_date')}
                      min={earliestDocDate(filed)}
                      max={today}
                      value={editing.date}
                      error={errors.date}
                      onChange={(date) => setEditing({ ...editing, date })}
                    />
                    <div className="editor-actions">
                      <Button variant="plain" small onClick={close}>
                        {t('btn_cancel')}
                      </Button>
                      {doc.custom ? (
                        <Button variant="danger" small icon="trash" disabled={busy} onClick={() => void deleteDoc(doc)}>
                          {t('btn_doc_delete')}
                        </Button>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
        {editing?.kind === 'newdoc' ? (
          <div className="editor editor-doc editor-new">
            <div className="field-block">
              <label className="field-label" htmlFor="doc-name-new">
                {t('doc_name')}
              </label>
              <TextField
                id="doc-name-new"
                placeholder={t('doc_name_placeholder')}
                invalid={!!errors.name}
                maxLength={meta.limits.max_doc_name}
                value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
              />
              <FieldError message={errors.name} />
            </div>
            <DateField
              label={t('doc_date')}
              min={earliestDocDate(filed)}
              max={today}
              value={editing.date}
              error={errors.date}
              onChange={(date) => setEditing({ ...editing, date })}
            />
            <div className="editor-actions">
              <Button variant="plain" small onClick={close}>
                {t('btn_cancel')}
              </Button>
            </div>
          </div>
        ) : customCount < meta.limits.max_custom_docs ? (
          <RowButton icon="plus" tone="accent" trailing={null} onClick={() => open({ kind: 'newdoc', name: '', date: '' })}>
            {t('btn_doc_add')}
          </RowButton>
        ) : (
          <p className="card-pad hint">{t('doc_limit', { max: meta.limits.max_custom_docs })}</p>
        )}
      </Group>

      <Group>
        <RowButton icon="send" tone="accent" trailing={null} onClick={() => void share()}>
          {t('btn_send_chat')}
        </RowButton>
        <RowButton icon="trash" tone="danger" trailing={null} disabled={busy} onClick={() => void remove()}>
          {t('btn_delete_case')}
        </RowButton>
      </Group>
    </Page>
  );
}

function ForecastCard({ detail, today }: { detail: CaseDetail; today: IsoDate }) {
  const { t, labels } = useApp();
  const f = detail.forecast;
  if (!f) {
    return (
      <section className="forecast is-complete">
        <span className="forecast-badge" aria-hidden="true">
          <Icon name="check" size={20} />
        </span>
        <p className="forecast-text">{t('fc_all_done')}</p>
      </section>
    );
  }
  const voiv = labels.voiv(detail.voivodeship);
  const purpose = labels.purpose(detail.purpose);
  const extremes =
    f.kind !== 'no_data' && f.fastest !== null && f.slowest !== null
      ? t('fc_fastest_slowest', { fastest: f.fastest, slowest: f.slowest })
      : null;
  const win = f.kind === 'window' && f.start && f.end && f.likely ? { start: f.start, end: f.end, likely: f.likely } : null;

  let body: ReactNode;
  if (win) {
    const scope = t(
      f.scope === 'national' ? 'fc_scope_national' : f.scope === 'voiv_filed' ? 'fc_scope_voiv_filed' : 'fc_scope_voiv',
      { voiv, purpose },
    );
    const inDays = daysBetween(today, win.likely);
    body = (
      <>
        <p className="forecast-label">{t('fc_likely')}</p>
        <p className="forecast-date">
          <span>{formatDate(win.likely)}</span>
          {inDays > 0 ? <span className="forecast-in">{t('fc_in_days', { n: inDays })}</span> : null}
        </p>
        <WindowStrip
          {...win}
          label={t('fc_window', { start: formatDate(win.start), end: formatDate(win.end), likely: formatDate(win.likely) })}
        />
        <p className="forecast-basis">{t('fc_basis', { n: f.n, scope })}</p>
      </>
    );
  } else if (f.kind === 'waited_longer') {
    body = <p className="forecast-text">{t('fc_waited_longer', { x: f.waited_longer_than ?? 0, y: f.total ?? 0 })}</p>;
  } else {
    body = <p className="forecast-text">{t('fc_no_data')}</p>;
  }

  return (
    <section className="forecast">
      <h2 className="forecast-title">
        <Icon name="clock" size={16} />
        <span>{t('fc_title', { target: labels.milestone(f.target) })}</span>
      </h2>
      {body}
      {extremes ? <p className="forecast-basis">{extremes}</p> : null}
    </section>
  );
}

/** The forecast window as a bar from its first to its last day, with the likeliest day marked. */
function WindowStrip({ start, likely, end, label }: { start: IsoDate; likely: IsoDate; end: IsoDate; label: string }) {
  const span = Math.max(1, daysBetween(start, end));
  const at = Math.min(100, Math.max(0, (daysBetween(start, likely) / span) * 100));
  return (
    <div className="window" role="img" aria-label={label}>
      <div className="window-track">
        <span className="window-likely" style={{ left: `${at}%` }} />
      </div>
      <div className="window-ends" aria-hidden="true">
        <span>{formatDate(start)}</span>
        <span>{formatDate(end)}</span>
      </div>
    </div>
  );
}

/**
 * Milestones as a vertical timeline. Each step's typical range sits on one shared axis of days
 * since filing, so later steps sit further right and the person's own day count is marked.
 */
function Timeline({
  detail,
  today,
  editingMilestone,
  onToggle,
  renderEditor,
}: {
  detail: CaseDetail;
  today: IsoDate;
  editingMilestone: Milestone | null;
  onToggle: (m: Milestone) => void;
  renderEditor: (m: Milestone) => ReactNode;
}) {
  const { t, labels } = useApp();
  const filed = detail.dates.filed ?? today;
  const lastDone = MILESTONES.reduce((last, m, i) => (detail.dates[m] ? i : last), -1);
  const next = MILESTONES.findIndex((m, i) => i > lastDone && !detail.dates[m]);
  const axis = Math.max(
    1,
    ...detail.chain.flatMap((c) => [c.agg?.max ?? 0, c.own_days ?? 0]),
  );
  const pct = (days: number) => `${Math.min(100, Math.max(0, (days / axis) * 100))}%`;

  return (
    <ol className="timeline">
      {MILESTONES.map((m, i) => {
        const date = detail.dates[m];
        const item = detail.chain.find((c) => c.milestone === m);
        const own = date && m !== 'filed' ? (item?.own_days ?? daysBetween(filed, date)) : null;
        const agg = item?.agg;
        const state = date ? 'done' : i === next ? 'next' : 'todo';
        const upto = i <= lastDone;
        const reached = i < lastDone;
        let when: string;
        if (m === 'filed') when = date ? formatDate(date) : t('tap_to_set');
        else if (date) when = t('chain_own', { date: formatDate(date), days: own ?? 0 });
        else when = t('tap_to_set');
        return (
          <li
            key={m}
            className={`tl-item is-${state}${upto ? ' is-upto' : ''}${reached ? ' is-reached' : ''}`}
            style={{ '--i': i } as CSSProperties}
          >
            <span className="tl-dot" aria-hidden="true">
              {date ? <Icon name="check" size={14} /> : null}
            </span>
            <button type="button" className="tl-row" aria-expanded={editingMilestone === m} onClick={() => onToggle(m)}>
              <span className="tl-title cap">{labels.milestone(m)}</span>
              <span className={date ? 'tl-when' : 'tl-when is-empty'}>{when}</span>
              {m !== 'filed' && agg ? (
                <span className="range" aria-hidden="true">
                  <span className="range-span" style={{ left: pct(agg.min), width: `calc(${pct(agg.max)} - ${pct(agg.min)})` }} />
                  <span className="range-mean" style={{ left: pct(agg.mean) }} />
                  {own !== null ? <span className="range-own" style={{ left: pct(own) }} /> : null}
                </span>
              ) : null}
              {m !== 'filed' ? (
                <span className="tl-typical">
                  {agg
                    ? t('chain_line', { mean: Math.round(agg.mean), min: agg.min, max: agg.max, n: agg.n })
                    : t('chain_none')}
                </span>
              ) : null}
            </button>
            {renderEditor(m)}
          </li>
        );
      })}
    </ol>
  );
}
