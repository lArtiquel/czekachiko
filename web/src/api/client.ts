import type {
  CalendarLink,
  CaseDetail,
  CaseSummary,
  IsoDate,
  Lang,
  Me,
  Meta,
  Milestone,
  NewCase,
  OutlierInfo,
  ShareQuery,
  StatsResponse,
  StatsSelection,
} from './types';

export type ApiErrorKind =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'outlier'
  | 'invalid'
  | 'rate_limited'
  | 'network'
  | 'server';

interface ApiErrorInit {
  kind: ApiErrorKind;
  status: number;
  code?: string | null;
  fields?: Record<string, string[]>;
  codes?: string[];
  outlier?: OutlierInfo | null;
  retryAfter?: number | null;
}

/** Every failed request becomes one of these. Messages never include request data. */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  /** HTTP status; 0 when the request never got a response. */
  readonly status: number;
  /** The `error` string from the body, e.g. `too_many_cases`. */
  readonly code: string | null;
  /** 422 field errors, each normalised to a list of codes. */
  readonly fields: Record<string, string[]>;
  /** 422 codes without a field, e.g. from `validate_milestones`. */
  readonly codes: string[];
  readonly outlier: OutlierInfo | null;
  readonly retryAfter: number | null;

  constructor(init: ApiErrorInit) {
    super(`API ${init.kind} (${init.status})`);
    this.name = 'ApiError';
    this.kind = init.kind;
    this.status = init.status;
    this.code = init.code ?? null;
    this.fields = init.fields ?? {};
    this.codes = init.codes ?? [];
    this.outlier = init.outlier ?? null;
    this.retryAfter = init.retryAfter ?? null;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

export interface ApiClientOptions {
  baseUrl: string;
  initData: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  /** Called on any 401, before the error is thrown. */
  onUnauthorized?: () => void;
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];

function normalizeFields(raw: unknown): Record<string, string[]> {
  if (!isRecord(raw)) return {};
  const out: Record<string, string[]> = {};
  for (const [field, value] of Object.entries(raw)) {
    const codes = typeof value === 'string' ? [value] : strings(value);
    if (codes.length) out[field] = codes;
  }
  return out;
}

function parseOutlier(body: Record<string, unknown>): OutlierInfo | null {
  const typical = body.typical;
  if (!isRecord(typical) || typeof body.value !== 'number') return null;
  const { p10, p90 } = typical;
  if (typeof p10 !== 'number' || typeof p90 !== 'number') return null;
  const info: OutlierInfo = { typical: { p10, p90 }, value: body.value };
  if (typeof body.from === 'string') info.from = body.from as Milestone;
  if (typeof body.to === 'string') info.to = body.to as Milestone;
  return info;
}

function parseRetryAfter(header: string | null): number | null {
  if (!header) return null;
  const seconds = Number.parseInt(header, 10);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function errorFromResponse(status: number, body: unknown, retryAfter: string | null) {
  const b = isRecord(body) ? body : {};
  const code = typeof b.error === 'string' ? b.error : null;
  if (status === 401) return new ApiError({ kind: 'unauthorized', status, code });
  // The API only answers pages served from its allowed origin.
  if (status === 403) return new ApiError({ kind: 'forbidden', status, code });
  if (status === 404) return new ApiError({ kind: 'not_found', status, code });
  if (status === 409) {
    const outlier = code === 'outlier' ? parseOutlier(b) : null;
    return outlier
      ? new ApiError({ kind: 'outlier', status, code, outlier })
      : new ApiError({ kind: 'conflict', status, code });
  }
  if (status === 422) {
    return new ApiError({
      kind: 'invalid',
      status,
      code,
      fields: normalizeFields(b.fields),
      codes: strings(b.codes),
    });
  }
  if (status === 429) {
    return new ApiError({ kind: 'rate_limited', status, code, retryAfter: parseRetryAfter(retryAfter) });
  }
  return new ApiError({ kind: 'server', status, code });
}

const seg = (v: string | number) => encodeURIComponent(String(v));

function selectionParams(selection: StatsSelection): URLSearchParams {
  return new URLSearchParams(
    'group' in selection ? { group: selection.group } : { purpose: selection.purposes.join(',') },
  );
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly initData: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private readonly onUnauthorized: (() => void) | undefined;

  constructor(opts: ApiClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, '');
    this.initData = opts.initData;
    this.fetchImpl = opts.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
    this.timeoutMs = opts.timeoutMs ?? 15000;
    this.onUnauthorized = opts.onUnauthorized;
  }

  async request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      Authorization: `tma ${this.initData}`,
    };
    const init: RequestInit = {
      method,
      headers,
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store',
      referrerPolicy: 'no-referrer',
    };
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    const controller = typeof AbortController === 'undefined' ? null : new AbortController();
    const timer = controller ? setTimeout(() => controller.abort(), this.timeoutMs) : null;
    if (controller) init.signal = controller.signal;

    let res: Response;
    try {
      res = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    } catch {
      throw new ApiError({ kind: 'network', status: 0 });
    } finally {
      if (timer) clearTimeout(timer);
    }

    if (res.status === 204) return undefined as T;
    let data: unknown = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok) {
      const err = errorFromResponse(res.status, data, res.headers.get('Retry-After'));
      if (err.kind === 'unauthorized') this.onUnauthorized?.();
      throw err;
    }
    if (data === null) throw new ApiError({ kind: 'server', status: res.status });
    return data as T;
  }

  me() {
    return this.request<Me>('GET', '/api/me');
  }
  updateMe(patch: { lang?: Lang }) {
    return this.request<Me>('PATCH', '/api/me', patch);
  }
  deleteMe() {
    return this.request<void>('DELETE', '/api/me');
  }
  meta(lang: Lang) {
    return this.request<Meta>('GET', `/api/meta?${new URLSearchParams({ lang })}`);
  }
  cases() {
    return this.request<CaseSummary[]>('GET', '/api/cases');
  }
  createCase(body: NewCase) {
    return this.request<CaseSummary>('POST', '/api/cases', body);
  }
  caseDetail(id: number) {
    return this.request<CaseDetail>('GET', `/api/cases/${seg(id)}`);
  }
  deleteCase(id: number) {
    return this.request<void>('DELETE', `/api/cases/${seg(id)}`);
  }
  setChannel(id: number, channel: string) {
    return this.request<CaseDetail>('PATCH', `/api/cases/${seg(id)}`, { channel });
  }
  setMilestone(id: number, m: Milestone, date: IsoDate, confirmOutlier = false) {
    const body = confirmOutlier ? { date, confirm_outlier: true } : { date };
    return this.request<CaseDetail>('PUT', `/api/cases/${seg(id)}/milestones/${seg(m)}`, body);
  }
  clearMilestone(id: number, m: Milestone) {
    return this.request<CaseDetail>('DELETE', `/api/cases/${seg(id)}/milestones/${seg(m)}`);
  }
  setStandardDocument(id: number, code: string, date: IsoDate | null) {
    return this.request<CaseDetail>('PUT', `/api/cases/${seg(id)}/documents/std/${seg(code)}`, {
      date,
    });
  }
  addDocument(id: number, body: { name: string; date: IsoDate | null }) {
    return this.request<CaseDetail>('POST', `/api/cases/${seg(id)}/documents`, body);
  }
  updateDocument(id: number, docId: number, patch: { name?: string; date?: IsoDate | null }) {
    return this.request<CaseDetail>('PATCH', `/api/cases/${seg(id)}/documents/${seg(docId)}`, patch);
  }
  deleteDocument(id: number, docId: number) {
    return this.request<CaseDetail>('DELETE', `/api/cases/${seg(id)}/documents/${seg(docId)}`);
  }
  /** `voivodeship` null means all of Poland; no `channel` means every filing channel. */
  stats(voivodeship: string | null, selection: StatsSelection, channel?: string) {
    const q = selectionParams(selection);
    if (voivodeship !== null) q.set('voivodeship', voivodeship);
    if (channel) q.set('channel', channel);
    return this.request<StatsResponse>('GET', `/api/stats?${q}`);
  }
  calendars() {
    return this.request<CalendarLink[]>('GET', '/api/calendars');
  }
  shareCase(id: number) {
    return this.request<ShareQuery>('GET', `/api/share/case/${seg(id)}`);
  }
  /** `places` are voivodeship codes and possibly ALL_POLAND. */
  shareStats(selection: StatsSelection, places: string[]) {
    const q = selectionParams(selection);
    q.set('voivodeships', places.join(','));
    return this.request<ShareQuery>('GET', `/api/share/stats?${q}`);
  }
}
