# Filing channels: three separate timelines

*2026-10-30. The way a case was filed changes its path, so statistics, forecasts and the stats screen are split by channel.*

## Why

Users noticed that "fingerprints" comes out earlier than "the fingerprint call" in the chain. The data shows why: people who file **in person** usually give fingerprints at the counter on the filing day and never get a call, while people who file **by post, e-Doręczenia or MOS** get a call months later. Today all of them are averaged together, and the app's only filing choices are `mos` and `paper`.

The pobyt-tracker source already records the method, but the importer collapsed it into `paper`:

| Source `method` | Cases | Fingerprints on the filing day | Call, then fingerprints | Fingerprints later, no call entered |
|---|---|---|---|---|
| `personal` | 177 | 57 | 3 | 12 |
| `post` | 100 | 3 | 14 | 37 |
| `edor` | 67 | 1 | 8 | 13 |
| `mos2` | 115 | 2 | 33 | 20 |
| `unk` (not given) | 357 | 23 | 31 | 96 |

## Channels

| Code | Shown as | Main path |
|---|---|---|
| `in_person` | Лично в urzędzie | Подача (отпечатки при подаче) → Номер дела → Decyzja → Карта |
| `post` | Почта или e-Doręczenia | Подача → Номер дела → Вызов → Отпечатки → Decyzja → Карта |
| `mos` | MOS (онлайн) | the same as `post`, with its own numbers |
| `unknown` | Способ не указан | imported cases only; never offered in the app |

- In person, "Вызов" stays available as an optional step: a wezwanie for missing documents can still come.
- Choosing "Лично" turns on «Отпечатки сдал(а) при подаче» in the add-case form, which sets fingerprints to the filing date. It can be switched off (12 in-person cases gave fingerprints later).

## Data

- `Channel` gains `in_person`, `post` and `unknown`; `paper` goes away.
- Imported cases are reclassified from the source: `personal` → `in_person`, `post`/`edor` → `post`, `mos2` → `mos`, `unk` → `unknown`, except `unk` with fingerprints on the filing day → `in_person` (only an in-person filing allows that).
- User cases with the old `paper` (13 today) become `post`, with no question asked (decided 2026-10-30). Owners can change it in the case screen.
- The importer keeps doing this on every manual run.

## Statistics and forecasts

- Every aggregate and interval lookup gets the channel as a dimension.
- The case screen shows the chain of the case's own channel, with that channel's steps.
- Forecast fallback: same voivodeship + basis + channel → voivodeship + permit type + channel → Poland + basis + channel → Poland + permit type + channel → then the same four without the channel ("все способы подачи"), which is the only place `unknown` cases count. The basis line says which one was used.
- **Stats screen:** a three-way switch, «Лично · Почта/e-Doręczenia · MOS», above the voivodeship chain. Each tab shows its own path and steps. Default: the channel of the user's latest case, otherwise "Почта/e-Doręczenia".

## Out of scope

- Inline share cards stay channel-agnostic (all methods). The golden tests must not change.
- The calendar is unchanged.
- One cohort for the whole chain (same cases for every step, so counts stop differing) is a separate change.

## Decisions (2026-10-30)

1. The 13 user `paper` cases become `post`. The case screen lets the owner change the channel.
2. The `unknown` imported cases count only in the "все способы" fallback; there is no fourth tab.
3. `unk` cases with fingerprints on the filing day are reclassified as `in_person`.
