import type { CaseDetail, CaseSummary, Me, Meta, StatsResponse } from '../api/types';

/** Invented data shaped exactly like the API contract (lang=ru). No real cases. */

export const me: Me = { tg_id: 42, lang: 'ru', reminders: false };

const VOIVS: [string, string][] = [
  ['dolnoslaskie', 'Dolnośląskie'],
  ['kujawsko_pomorskie', 'Kujawsko-pomorskie'],
  ['lubelskie', 'Lubelskie'],
  ['lubuskie', 'Lubuskie'],
  ['lodzkie', 'Łódzkie'],
  ['malopolskie', 'Małopolskie'],
  ['mazowieckie', 'Mazowieckie'],
  ['opolskie', 'Opolskie'],
  ['podkarpackie', 'Podkarpackie'],
  ['podlaskie', 'Podlaskie'],
  ['pomorskie', 'Pomorskie'],
  ['slaskie', 'Śląskie'],
  ['swietokrzyskie', 'Świętokrzyskie'],
  ['warminsko_mazurskie', 'Warmińsko-mazurskie'],
  ['wielkopolskie', 'Wielkopolskie'],
  ['zachodniopomorskie', 'Zachodniopomorskie'],
];

const CORE = [
  { code: 'wniosek', name: 'Wniosek' },
  { code: 'zdjecia', name: 'Zdjęcia' },
  { code: 'paszport', name: 'Kopia paszportu' },
];

/** /api/meta as servers before permit types sent it: a flat purpose list, no permit_types. */
export const legacyMeta: Meta = {
  voivodeships: VOIVS.map(([code, label]) => ({ code, label })),
  purposes: [
    { code: 'praca', label: 'работа', button: 'Работа (art. 114)' },
    { code: 'jdg', label: 'бизнес (JDG)', button: 'Своё дело / ИП — JDG (art. 142)' },
    { code: 'studia', label: 'учёба', button: 'Учёба' },
    { code: 'rodzina', label: 'семья', button: 'Семья' },
    { code: 'inne', label: 'другое', button: 'Другое' },
  ],
  channels: [
    { code: 'mos', label: 'MOS (онлайн)' },
    { code: 'paper', label: 'Лично / почтой' },
  ],
  milestones: [
    { code: 'filed', label: 'подача', hint: 'когда подал wniosek' },
    { code: 'case_number', label: 'номер дела', hint: 'когда пришёл номер дела (sygnatura)' },
    { code: 'braki', label: 'вызов на отпечатки пальцев', hint: 'когда пришёл вызов (wezwanie)' },
    { code: 'fingerprints', label: 'отпечатки сданы', hint: 'когда сдал отпечатки' },
    { code: 'decision', label: 'decyzja', hint: 'когда вынесли decyzję' },
    { code: 'card', label: 'карта', hint: 'когда получил карту' },
  ],
  checklists: {
    praca: [...CORE, { code: 'umowa_praca', name: 'Umowa o pracę / zlecenie' }],
    jdg: [...CORE, { code: 'ceidg', name: 'Wpis do CEIDG' }],
    studia: CORE,
    rodzina: CORE,
    inne: CORE,
  },
  limits: { max_cases: 5, max_custom_docs: 15, max_doc_name: 60 },
};

const TEMPORARY = ['praca', 'jdg', 'blue_card', 'studia', 'rodzina', 'inne'];
const typeOf = (code: string) =>
  TEMPORARY.includes(code) ? 'temporary' : code === 'staly' ? 'permanent' : 'eu_resident';
const purposeList = [
  ...legacyMeta.purposes.slice(0, 2),
  { code: 'blue_card', label: 'Blue Card', button: 'Blue Card (Niebieska Karta UE)' },
  ...legacyMeta.purposes.slice(2),
  { code: 'staly', label: 'постоянный побыт', button: 'Постоянный побыт (pobyt stały)' },
  { code: 'rezydent_ue', label: 'резидент ЕС', button: 'Резидент ЕС (rezydent długoterminowy UE)' },
];

/** /api/meta with permit types (current servers). */
export const meta: Meta = {
  ...legacyMeta,
  purposes: purposeList.map((p) => ({ ...p, permit_type: typeOf(p.code) })),
  permit_types: [
    { code: 'temporary', label: 'временный побыт', button: 'Временный побыт (pobyt czasowy)', purposes: TEMPORARY },
    { code: 'permanent', label: 'постоянный побыт', button: 'Постоянный побыт (pobyt stały)', purposes: ['staly'] },
    {
      code: 'eu_resident',
      label: 'резидент ЕС',
      button: 'Резидент ЕС (rezydent długoterminowy UE)',
      purposes: ['rezydent_ue'],
    },
  ],
  checklists: { ...legacyMeta.checklists, blue_card: CORE, staly: CORE, rezydent_ue: CORE },
};

export const caseDetail: CaseDetail = {
  id: 7,
  voivodeship: 'mazowieckie',
  purpose: 'praca',
  channel: 'mos',
  dates: { filed: '2025-01-10', case_number: '2025-03-01', fingerprints: '2025-05-20' },
  docs_done: 2,
  docs_total: 4,
  chain: [
    { milestone: 'case_number', own_days: 50, agg: { n: 23, mean: 61.4, min: 12, max: 140 } },
    { milestone: 'braki', own_days: null, agg: { n: 9, mean: 98.2, min: 40, max: 201 } },
    { milestone: 'fingerprints', own_days: 130, agg: { n: 17, mean: 150.6, min: 70, max: 260 } },
    { milestone: 'decision', own_days: null, agg: { n: 6, mean: 301, min: 180, max: 420 } },
    { milestone: 'card', own_days: null, agg: null },
  ],
  forecast: {
    kind: 'window',
    target: 'decision',
    start: '2025-11-02',
    likely: '2026-01-15',
    end: '2026-04-30',
    n: 11,
    scope: 'voiv',
    waited_longer_than: null,
    total: null,
    fastest: 120,
    slowest: 410,
  },
  documents: [
    { id: 101, code: 'wniosek', name: 'Wniosek', date: '2025-01-10', custom: false },
    { id: null, code: 'zdjecia', name: 'Zdjęcia', date: null, custom: false },
    { id: null, code: 'paszport', name: 'Kopia paszportu', date: null, custom: false },
    { id: 205, code: null, name: '<img src=x onerror=alert(1)> Zaświadczenie', date: '2025-02-01', custom: true },
  ],
};

export const cases: CaseSummary[] = [
  {
    id: caseDetail.id,
    voivodeship: caseDetail.voivodeship,
    purpose: caseDetail.purpose,
    channel: caseDetail.channel,
    dates: caseDetail.dates,
    docs_done: caseDetail.docs_done,
    docs_total: caseDetail.docs_total,
  },
];

export const stats: StatsResponse = {
  chain: caseDetail.chain.map((c) => ({ ...c, own_days: null })),
  who_now: { fingerprints: ['2025-03-01', '2025-04-01'], decision: null },
};
