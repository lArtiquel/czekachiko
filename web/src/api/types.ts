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
  /** `temporary`, `permanent`, `eu_resident` or `unknown`. Absent from servers older than permit types. */
  permit_type?: string;
}

/** A permit type with its bases (purpose codes), in picker order. */
export interface PermitTypeOption extends Option {
  /** Picker heading, e.g. "Временный побыт (pobyt czasowy)". */
  button: string;
  purposes: string[];
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
  /** Flat, in picker order. */
  purposes: PurposeOption[];
  /**
   * The same purposes grouped by permit type. Its presence also tells the app that the server
   * takes several bases, permit types and all of Poland in stats.
   */
  permit_types?: PermitTypeOption[];
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
  /** Where the numbers come from; `_group` means every basis of the case's permit type. */
  scope: 'voiv' | 'voiv_filed' | 'voiv_group' | 'national' | 'national_group' | null;
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

/** Stats for one or more bases, or for every basis of a permit type. */
export type StatsSelection = { purposes: string[] } | { group: string };

/** All of Poland, as a place next to voivodeships (`voivodeships=all` when sharing). */
export const ALL_POLAND = 'all';

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
