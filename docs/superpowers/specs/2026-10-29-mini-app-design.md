# Czekachiko Mini App: design

*2026-10-29. Move the user interface from bot buttons to a Telegram Mini App. The bot keeps support, replies and inline cards.*

## Why
Bot buttons round-trip to the server on every tap. Date picking is slow, and screens are cramped. A Mini App gives a native-looking UI (Telegram theme, real date input, lists) and still identifies people by their Telegram account.

## Shape
- **Frontend:** `web/`, a React + TypeScript + Vite single-page app using `@telegram-apps/telegram-ui` components and Telegram's `telegram-web-app.js` (`window.Telegram.WebApp`). Static only, no secrets. A GitHub Actions workflow publishes it to GitHub Pages at `https://lartiquel.github.io/czekachiko/` on every push to `master` that touches `web/**`.
- **Backend API:** `czekachiko.api`, an aiohttp app running in the same image as the bot as a new compose service `api` on port 8080 inside Docker. It reuses `db/repo.py`, `stats.py`, `dates.py`, `documents.py`, `share.py` and `calendar` links unchanged. No business logic is duplicated.
- **Edge:** a `cloudflared` compose service (`tunnel run --token $CLOUDFLARE_TUNNEL_TOKEN`) publishes `https://czekachiko-api.artware.me` → `http://api:8080`. **No host ports are published.** Postgres stays on the internal `db` network. Networks:
  - `api` sits on `db` and `edge`;
  - `tunnel` sits on `edge` only;
  - `bot` sits on `db` and `egress`.
- **Bot:** the menu button (`setChatMenuButton`, `MenuButtonWebApp`) opens the app. `/start` shows one message with an inline `web_app` button «🚀 Открыть Czekachiko». The persistent reply keyboard becomes two buttons: «🚀 Открыть приложение» (`web_app`) and «✉️ Написать нам». The feedback flow, admin replies, inline cards (`@czekachiko_bot …`) and the calendar worker stay as they are. The old button screens stay reachable for now; they are not deleted in this change.

## Auth (every API request)
- Header `Authorization: tma <initData>`, where initData is `window.Telegram.WebApp.initData`.
- The server validates it per Telegram's spec: `secret = HMAC_SHA256(key="WebAppData", msg=bot_token)`, `hash == hex(HMAC_SHA256(secret, data_check_string))`, compared in constant time. `auth_date` must be at most **24 h** old and not in the future. The user is `user.id` from the signed `user` JSON.
- Anything missing, bad or stale gives `401 {"error":"unauthorized"}`. Outside Telegram there is no initData, so the frontend shows "Откройте через Telegram" and makes no calls.
- Ownership: every case and document access goes through `repo.get_case(session, tg_id, case_id)`. Someone else's id gives `404`.

## Abuse limits
- Request body capped at **16 KB**. JSON only (`Content-Type: application/json` for writes).
- Rate limits are in memory and use a token bucket:
  - per `tg_id`: 10 requests/s burst, 120/min sustained;
  - per client IP (`CF-Connecting-IP`): 300/min.
  - Over the limit: `429` with `Retry-After`.
- Write limits are reused from the bot: 5 cases per user, document limits, date rules.
- CORS: `Access-Control-Allow-Origin: https://lartiquel.github.io` only, methods GET/POST/PUT/PATCH/DELETE, header `Authorization, Content-Type`. Preflight is cached for 600 s.
- Generic error bodies, no stack traces. Logs never contain initData or tokens.
- Container limits: `api` gets `mem_limit 256m`, `cpus 0.5`, `pids_limit 128`, read-only filesystem. `tunnel` gets `mem_limit 128m`, `cpus 0.3`.

## API contract (JSON, dates as `YYYY-MM-DD`, `lang` ∈ `ru`/`en`)
| Method & path | Body | Response |
|---|---|---|
| `GET /api/health` | — | `{"ok":true}`. No auth; used by deploy checks. |
| `GET /api/me` | — | `{"tg_id", "lang", "reminders"}` |
| `PATCH /api/me` | `{"lang"?: "ru"\|"en"}` | same as GET |
| `DELETE /api/me` | — | `204`. Deletes all the user's data (cases, documents, feedback). |
| `GET /api/meta?lang=` | — | `{"voivodeships":[{code,label}], "purposes":[{code,label,button,permit_type}], "permit_types":[{code,label,button,purposes:[code]}], "channels":[{code,label}], "milestones":[{code,label,hint}], "checklists":{purpose:[{code,name}]}, "limits":{"max_cases":5,"max_custom_docs":15,"max_doc_name":60}}`. `purposes` stays flat (picker order); `permit_types` groups them: temporary, permanent, eu_resident, and unknown (`nieznane`, basis not given; never pooled into the others). `channels` are `in_person`, `post` (post or e-Doręczenia) and `mos`, in picker order; `unknown` belongs to imported cases and is never listed |
| `GET /api/cases` | — | `[{"id","voivodeship","purpose","channel","dates":{milestone:date},"docs_done","docs_total"}]` |
| `POST /api/cases` | `{"voivodeship","purpose","channel","filed","client_token","fingerprints_at_filing"?:bool}` | `201` case. `channel` is `in_person\|post\|mos`. `fingerprints_at_filing: true` (in person only) also saves fingerprints on the filing date. `409 {"error":"too_many_cases"}`. `422 {"error":"invalid","fields":{...}}` |
| `GET /api/cases/{id}` | — | case plus `"chain":[{"milestone","own_days"\|null,"agg":{n,mean,min,max}\|null}]` in the case channel's path order, with that channel's numbers, `"forecast":{kind,target,start,likely,end,n,scope,waited_longer_than,total,fastest,slowest}\|null`, `"documents":[{"id"\|null,"code"\|null,"name","date"\|null,"custom":bool}]`. `scope` is `voiv`, `voiv_filed`, `voiv_group`, `national` or `national_group` for the case's channel, or the same with `_any` when it fell back to every channel |
| `PATCH /api/cases/{id}` | `{"channel"}` | `200` case detail. `channel` is `in_person\|post\|mos`, else `422`. Aggregates recompute; calendar events carry no channel, so the outbox is untouched |
| `DELETE /api/cases/{id}` | — | `204` |
| `PUT /api/cases/{id}/milestones/{m}` | `{"date","confirm_outlier"?:bool}` | `200` case detail. `422 {"error":"invalid","codes":[...]}` uses the `validate_milestones` codes. `409 {"error":"outlier","typical":{p10,p90},"value"}` unless `confirm_outlier` is true. |
| `DELETE /api/cases/{id}/milestones/{m}` | — | `200` case detail. `filed` cannot be removed: `422`. |
| `PUT /api/cases/{id}/documents/std/{code}` | `{"date": date\|null}` | `200` case detail |
| `POST /api/cases/{id}/documents` | `{"name","date"\|null}` | `201` case detail. `422` for name/date. `409` at the limit. |
| `PATCH /api/cases/{id}/documents/{doc_id}` | `{"name"?,"date"?}` | `200` case detail |
| `DELETE /api/cases/{id}/documents/{doc_id}` | — | `200` case detail |
| `GET /api/stats?voivodeship=&purpose=&channel=` or `…&group=` | — | `{"chain":[…as above, own_days null…], "who_now":{"fingerprints":[from,to]\|null,"decision":[from,to]\|null}}`. `purpose=a,b` takes bases of one permit type (else `mixed`); `group=temporary\|permanent\|eu_resident\|unknown` takes all its bases (not both: `exclusive`); no `voivodeship` means all of Poland. Several purposes are pooled from intervals, never averaged. `channel=in_person\|post\|mos` gives that channel's numbers in its path order (anything else: `422`); the app always sends it. Without it, every channel counts, `unknown` included. In person, `who_now.fingerprints` is null: nobody is called for them |
| `GET /api/calendars` | — | `[{"voivodeship","label","url"}]` |
| `GET /api/share/case/{id}` | — | `{"query":"c:{id}"}` (owner only) |
| `GET /api/share/stats?purpose=&voivodeships=a,b` or `group=` | — | `{"query":"s:…"}` (validated, max 6; `all` in `voivodeships` is all of Poland). Codes: `s:<selector>:<places>`, selector `jdg`, `praca+jdg` or `temporary`, places voivodeship indexes or `all`; old `s:<purpose>:<indexes>` codes decode as before |

Writes go through the same repo functions as the bot, so aggregates recompute and the calendar outbox fills exactly as before.

## Frontend screens
1. **Home:** my cases (cards with voivodeship · purpose, filing date, next forecast line, docs progress), «➕ Добавить дело», and entries to Сроки, Календари, Настройки, «✉️ Написать нам» (opens `https://t.me/czekachiko_bot` via `openTelegramLink`) and «📣 Поделиться ботом».
2. **Add case:** voivodeship (searchable list), purpose, channel, filing date (date input with max today, min 2015-01-01), then save.
3. **Case:** the timeline (each milestone with its own date, days from filing, typical mean/min/max and n, tap to set, change or clear), forecast block with disclaimer, documents checklist (tick plus date, custom add, rename, delete), «📤 Отправить в чат» (`Telegram.WebApp.switchInlineQuery(query, ["users","groups","channels"])`), delete case (confirm with `showConfirm`).
4. **Stats:** pick a purpose and one or more voivodeships (max 6). Shows the chain per voivodeship and who-now, plus «📤 Отправить в чат».
5. **Calendars:** 16 voivodeship links, opened with `openLink`.
6. **Settings:** language RU/EN (default from `initDataUnsafe.user.language_code`, persisted via `PATCH /api/me`), delete all my data (confirm), privacy text.

UX: Telegram theme colours, the `BackButton` for navigation, `MainButton` for the primary action on forms, `HapticFeedback` on success, and outlier confirmation via `showPopup`. RU is the default, EN optional, and every string is in both. Hash routing (`#/case/12`) so GitHub Pages needs no server rewrites. Base path `/czekachiko/`.

## Out of scope
Removing the old button UI, reminders, new statistics, a custom domain for Pages.
