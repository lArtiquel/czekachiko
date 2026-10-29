/**
 * Models for the API contract in docs/superpowers/specs/2026-10-29-mini-app-design.md.
 * Dates are `YYYY-MM-DD` strings.
 */

export type Lang = 'ru' | 'en';
export type IsoDate = string;

export const MILESTONES = [
  'filed',
  'case_number',
  'braki',
  'fingerprints',
  'decision',
  'card',
] as const;
export type Milestone = (typeof MILESTONES)[number];

export interface Me {
  tg_id: number;
  lang: Lang;
  reminders: boolean;
}

export interface Option {
  code: string;
  label: string;
}

export interface PurposeOption extends Option {
  /** Longer label for pickers, e.g. "Работа (art. 114)". */
  button: string;
}

export interface MilestoneOption {
  code: Milestone;
  label: string;
  hint: string;
}

export interface ChecklistItem {
  code: string;
  name: string;
}

export interface Limits {
  max_cases: number;
  max_custom_docs: number;
  max_doc_name: number;
}

export interface Meta {
  voivodeships: Option[];
  purposes: PurposeOption[];
  channels: Option[];
  milestones: MilestoneOption[];
  checklists: Record<string, ChecklistItem[]>;
  limits: Limits;
}

export interface CaseSummary {
  id: number;
  voivodeship: string;
  purpose: string;
  channel: string;
  dates: Partial<Record<Milestone, IsoDate>>;
  docs_done: number;
  docs_total: number;
}

export interface Agg {
  n: number;
  mean: number;
  min: number;
  max: number;
}

export interface ChainItem {
  milestone: Milestone;
  own_days: number | null;
  agg: Agg | null;
}

export interface Forecast {
  kind: 'window' | 'waited_longer' | 'no_data';
  target: Milestone;
  start: IsoDate | null;
  likely: IsoDate | null;
  end: IsoDate | null;
  n: number;
  scope: 'voiv' | 'voiv_filed' | 'national' | null;
  waited_longer_than: number | null;
  total: number | null;
  fastest: number | null;
  slowest: number | null;
}

export interface CaseDocument {
  /** Null for a standard item that was never ticked. */
  id: number | null;
  /** Standard checklist code; null for the owner's own documents. */
  code: string | null;
  name: string;
  date: IsoDate | null;
  custom: boolean;
}

export interface CaseDetail extends CaseSummary {
  chain: ChainItem[];
  /** Null once every milestone is done. */
  forecast: Forecast | null;
  documents: CaseDocument[];
}

export interface NewCase {
  voivodeship: string;
  purpose: string;
  channel: string;
  filed: IsoDate;
  client_token: string;
}

export interface StatsResponse {
  chain: ChainItem[];
  who_now: {
    fingerprints: [IsoDate, IsoDate] | null;
    decision: [IsoDate, IsoDate] | null;
  };
}

export interface CalendarLink {
  voivodeship: string;
  label: string;
  url: string;
}

export interface ShareQuery {
  query: string;
}

/** Body of `409 {"error":"outlier"}`. `from`/`to` are not in the contract; used if the server sends them. */
export interface OutlierInfo {
  typical: { p10: number; p90: number };
  value: number;
  from?: Milestone;
  to?: Milestone;
}
