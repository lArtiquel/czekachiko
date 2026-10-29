# Czekachiko Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `@czekachiko_bot`, a Telegram bot that collects anonymous residence-permit milestones, forecasts the next step per voivodeship, and mirrors every milestone into a public Google Calendar. Deploy it to the host as its own compose project.

**Architecture:** aiogram 3 long-polling bot over Postgres 16 (SQLAlchemy async, Alembic). Pure modules hold all logic (`dates`, `stats`, `ui`), so they can be unit-tested. Handlers stay thin. Aggregates are recomputed per affected key on every write. Calendar sync is a DB outbox drained by a background task. Nothing listens on the network.

**Tech Stack:** Python 3.12, aiogram 3, SQLAlchemy 2 async + asyncpg, Alembic, pydantic-settings, google-auth + httpx (Calendar REST), pytest + pytest-asyncio, ruff, gitleaks, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-29-czekachiko-bot-design.md`

## Global Constraints

- No free-text input is stored anywhere. Enumerations come from buttons only. Dates come from the calendar keyboard or the typed formats `DD.MM.YYYY`, `D.M.YYYY` and `YYYY-MM-DD`.
- The bot never sends a message that the user did not trigger. The reminders flag exists, defaults to off, and nothing reads it.
- At most 5 cases per Telegram user.
- `filed` ≥ 2015-01-01. No date in the future. Every other milestone ≥ `filed`. `fingerprints ≤ decision ≤ card` when set.
- Forecast thresholds: a window needs n ≥ 5. Outlier check needs n ≥ 8, fence `[Q1 − 3·IQR, Q3 + 3·IQR]`. "Who is called now" needs ≥ 3 events in the last 30 days.
- Window = p10…p90 and median. Percentiles use linear interpolation.
- Languages: `ru` (default) and `en`. Every key exists in both.
- The repo is public. No secrets, IPs, hostnames, server paths or real case data in any committed file. Fixtures use invented cases.
- Nothing publishes a port. Postgres is only on an `internal: true` network.
- Memory limits: bot 200 MB, Postgres 150 MB. Deploy aborts if the host has < 500 MB available.
- **The bot must not be able to starve the host** (the host runs a production VPN): `cpus: 0.5` for the bot and `0.3` for db, `pids_limit: 128`, docker log rotation `max-size: 10m`, `max-file: 3`.
- **Flood protection:** per-user throttle of 5 updates per 3 s; extra updates are dropped silently. If a user exceeds 40 updates per minute, the bot ignores them for 10 minutes and logs it once. At most 20 updates are processed concurrently.
- Deploy touches only the compose project `czekachiko`.

## Review Focus

1. **A double-tap on "Save case" or a resent callback** must not create two cases. Covered by a `test_create_case_idempotent` step in Task 4.
2. **Editing `filed` so that it lands after an existing later milestone** must be rejected, not stored. Covered by a `test_edit_filed_after_fingerprints_rejected` step in Task 2.
3. **A group where all intervals are equal (IQR = 0)** must not flag every new value as an outlier. Covered by `test_outlier_zero_iqr_uses_floor` in Task 3.
4. **A stale button after a restart, or for a deleted case**, must re-render the main menu instead of raising an error. Telegram's "message is not modified" must be ignored. Covered by `test_stale_case_callback_shows_menu` in Task 6.
5. **Deleting a case or "Delete all my data"** must remove its calendar events and recompute every affected aggregate. Covered by `test_delete_case_enqueues_calendar_deletes_and_recomputes` in Task 4.

---

## File Structure

```
pyproject.toml  Dockerfile  docker-compose.yml  alembic.ini
.env.example  deploy.env.example  .pre-commit-config.yaml  README.md
.github/workflows/ci.yml
migrations/env.py  migrations/versions/0001_initial.py
src/czekachiko/
  __main__.py        # startup: migrate, start calendar worker, start polling
  config.py          # Settings (pydantic-settings)
  domain.py          # enums + ordering + interval pairs
  dates.py           # parse_date, validate_milestones
  stats.py           # pure stats: percentiles, Aggregate, outlier, forecast, who_now
  db/models.py       # SQLAlchemy models
  db/session.py      # engine/session factory
  db/repo.py         # CRUD, recompute, outbox enqueue
  fsm_storage.py     # aiogram BaseStorage on Postgres
  i18n.py            # t(lang, key, **kw); locales dicts
  locales/ru.py  locales/en.py
  ui/keyboards.py    # date picker, nav, enum pickers
  ui/screens.py      # pure renderers -> (text, InlineKeyboardMarkup)
  handlers/__init__.py  # router assembly
  handlers/common.py    # /start /help /cancel, stale callbacks, text fallback
  handlers/cases.py     # list, view, add wizard, edit milestone, delete
  handlers/stats.py     # voivodeship stats
  handlers/settings.py  # language, reminders, delete all
  handlers/calendar.py  # /calendar
  handlers/admin.py     # /admin, /admin recompute
  calendar_sync.py      # GoogleCalendarClient + outbox worker
scripts/deploy.sh  scripts/backup.sh
tests/...
```

---

### Task 1: Scaffold, tooling and CI

**Files:**
- Create: `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `.env.example`, `deploy.env.example`, `README.md`, `src/czekachiko/__init__.py`, `src/czekachiko/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `config.Settings` with fields `bot_token: SecretStr`, `database_url: str`, `admin_tg_id: int | None = None`, `google_service_account_json: str | None = None` (a file path), `calendar_id: str | None = None`, `calendar_public_url: str | None = None`. Property `calendar_enabled -> bool`, true only when both JSON and `calendar_id` are set.

- [ ] **Step 1: Write the failing test.** `test_calendar_disabled_without_credentials` checks that `Settings(bot_token="x", database_url="postgresql+asyncpg://u:p@h/d").calendar_enabled is False`. `test_calendar_enabled_with_both` checks that it is True when both are set.
- [ ] **Step 2: Run it and confirm it fails.** Run: `pytest tests/test_config.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement `Settings`.** Use pydantic-settings, env prefix none, and `.env` support. Write `pyproject.toml` (deps from the Tech Stack, `[dev]` = pytest, pytest-asyncio, ruff, aiosqlite is NOT used, asyncpg only). Ruff line length is 100. `.env.example` and `deploy.env.example` (`DEPLOY_HOST=`, `DEPLOY_PATH=`) hold placeholders only.
- [ ] **Step 4: Write CI and pre-commit.** CI runs `ruff check`, `ruff format --check`, and `pytest` with a `postgres:16` service and `DATABASE_URL` set. A separate `gitleaks/gitleaks-action@v2` job runs on push and PR. The pre-commit config holds the gitleaks and ruff hooks. The README gets one paragraph: what the bot is, the link to the bot, and a pointer to CONTRIBUTING.
- [ ] **Step 5: Run it and confirm it passes.** Run: `pytest -v && ruff check .`. Expected: PASS.
- [ ] **Step 6: Commit.** `chore: scaffold project, config, CI with gitleaks`

### Task 2: Domain and date validation

**Files:**
- Create: `src/czekachiko/domain.py`, `src/czekachiko/dates.py`, `tests/test_dates.py`

**Interfaces:**
- Produces:
  - `Voivodeship(StrEnum)`: 16 values, slug names (`mazowieckie`, …). `Purpose(StrEnum)`: `praca, jdg, studia, rodzina, inne`. `Channel(StrEnum)`: `mos, paper`. `Milestone(StrEnum)`: `filed, case_number, braki, fingerprints, decision, card`.
  - `FORECAST_TARGETS = (fingerprints, decision, card)`, `ANCHORS = (filed, fingerprints, decision)`, `INTERVAL_PAIRS = [(filed,case_number),(filed,fingerprints),(filed,decision),(filed,card),(fingerprints,decision),(decision,card)]`.
  - `parse_date(text: str, today: date) -> date | None`
  - `validate_milestones(dates: Mapping[Milestone, date], today: date) -> list[str]`, which returns error codes: `future`, `before_2015`, `before_filed`, `order`, `filed_missing`.

- [ ] **Step 1: Write the failing tests.**
  - `parse_date("06.03.2026")`, `("6.3.2026")` and `("2026-03-06")` all return `date(2026,3,6)`. `parse_date("завтра")`, `("31.02.2026")` and `("")` return `None`.
  - `validate_milestones({filed: 2026-03-06, fingerprints: 2026-10-29}, today=2026-10-29) == []`.
  - A future date gives `["future"]`. `filed` 2014-12-31 gives `["before_2015"]`. `decision` < `fingerprints` gives `["order"]`.
  - `test_edit_filed_after_fingerprints_rejected`: `filed` 2026-11-01 with `fingerprints` 2026-10-29 (today 2026-11-05) gives `"before_filed"` in the result.
- [ ] **Step 2: Run them and confirm they fail.** Run: `pytest tests/test_dates.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the enums, the tuples and both functions.
- [ ] **Step 4: Run them and confirm they pass.** Run: `pytest tests/test_dates.py -v`.
- [ ] **Step 5: Commit.** `feat: domain enums and date validation`

### Task 3: Statistics engine (pure)

**Files:**
- Create: `src/czekachiko/stats.py`, `tests/test_stats.py`

**Interfaces:**
- Consumes: `domain` enums.
- Produces:
  - `percentile(values: Sequence[int], q: float) -> float` (linear interpolation, q in [0,1]).
  - `@dataclass(frozen=True) Aggregate(n:int, p10:float, median:float, p90:float, min:int, max:int)` and `aggregate(values) -> Aggregate | None` (None when empty).
  - `is_suspicious(value:int, values:Sequence[int]) -> bool`: False when `len(values) < 8`. The fence is `Q1 − 3·IQR … Q3 + 3·IQR`, and IQR is floored at `max(IQR, 0.1·median, 7)` days.
  - `@dataclass Forecast(kind: Literal["window","waited_longer","no_data"], anchor: Milestone, target: Milestone, start: date|None, likely: date|None, end: date|None, n:int, scope: Literal["voiv","voiv_filed","national"]|None, waited_longer_than:int|None, total:int|None, fastest:int|None, slowest:int|None)`.
  - `forecast(case_dates: Mapping[Milestone,date], today: date, lookup: Callable[[Literal["voiv","national"], Milestone, Milestone], Sequence[int]]) -> Forecast | None`. It returns None when all targets are reached.
  - `who_now(events: Sequence[tuple[date, date]], today: date) -> tuple[date, date] | None`, where each pair is (event_date, filed_date). It returns the min and max filing month among events in the last 30 days, or None if there are fewer than 3.
- Algorithm for `forecast` (from the spec): T is the first missing target. K is the latest anchor before T that is present, with date d. Try the scopes in order: `voiv` K→T, then `voiv` filed→T (anchor becomes filed), then `national` K→T. For a scope: elapsed `e = (today − d).days`; `pool = [v for v in values if v ≥ e]`. If `len(values) ≥ 5` and `len(pool) ≥ 5`, return a window from `d + p10/median/p90` of the pool. If `len(values) ≥ 5` and `len(pool) < 5`, return `waited_longer` with `waited_longer_than = len(values) − len(pool)` and `total = len(values)`. Otherwise go to the next scope. If no scope qualifies, return `no_data`. The fastest and slowest values come from the qualifying scope's full values.

- [ ] **Step 1: Write the failing tests.**
  - `percentile([1,2,3,4],0.5)==2.5`, `percentile([10],0.9)==10`.
  - `aggregate([])` is None. `aggregate([100,120,140,160,180])` gives median 140, min 100, max 180.
  - `is_suspicious(610, [90,100,120,150,170,190,210,240])` is True. `is_suspicious(260, same)` is False. With 7 values it is always False.
  - `test_outlier_zero_iqr_uses_floor`: `is_suspicious(150, [150]*10)` is False and `is_suspicious(400, [150]*10)` is True.
  - Forecast window: fingerprints→decision has 10 values 100..280 step 20, the case has fingerprints = today−50. The result has kind `window`, scope `voiv`, `start ≥ today`.
  - Waited longer: elapsed 300 against the same values gives kind `waited_longer`, `waited_longer_than == 10`, `total == 10`.
  - Fallback: voiv has 3 values and national has 6, so scope is `national`.
  - `no_data` when every lookup returns `[]`.
  - `who_now` with 3 events in the window returns the filing-month span. With 2 events it returns None.
- [ ] **Step 2: Run them and confirm they fail.** Run: `pytest tests/test_stats.py -v`.
- [ ] **Step 3: Implement** per the interfaces and algorithm above.
- [ ] **Step 4: Run them and confirm they pass.**
- [ ] **Step 5: Commit.** `feat: statistics, outlier and forecast engine`

### Task 4: Database, migrations and repository

**Files:**
- Create: `src/czekachiko/db/models.py`, `db/session.py`, `db/repo.py`, `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_initial.py`, `tests/conftest.py`, `tests/test_repo.py`

**Interfaces:**
- Consumes: `domain`, `stats.aggregate`.
- Tables:
  - `users(tg_id bigint pk, lang text default 'ru', reminders bool default false, created_at)`
  - `cases(id serial pk, tg_id fk→users on delete cascade, voivodeship, purpose, channel, created_at, client_token text unique)`
  - `milestones(case_id fk on delete cascade, milestone, date, confirmed_outlier bool default false, pk(case_id, milestone))`
  - `aggregates(voivodeship null=national, purpose, from_m, to_m, n, p10, median, p90, min, max, updated_at, unique(voivodeship, purpose, from_m, to_m) nulls not distinct)`
  - `fsm(key text pk, state text null, data jsonb)`
  - `calendar_events(case_id, milestone, event_id text null, pk(case_id, milestone))`
  - `calendar_outbox(id serial pk, op text check in ('upsert','delete'), case_id, milestone, payload jsonb, event_id text null, attempts int default 0, next_try_at timestamptz default now())`
- Produces (all `async`, taking `AsyncSession`):
  - `ensure_user(s, tg_id) -> User`, `set_lang(s, tg_id, lang)`, `set_reminders(s, tg_id, on: bool)`
  - `count_cases(s, tg_id) -> int`, `list_cases(s, tg_id) -> list[Case]`, `get_case(s, tg_id, case_id) -> Case | None` (owner-checked)
  - `create_case(s, tg_id, voiv, purpose, channel, filed: date, client_token: str) -> Case`. It is idempotent on `client_token` and raises `TooManyCases` when 5 already exist.
  - `set_milestone(s, case, milestone, d: date, confirmed_outlier=False)`, `clear_milestone(s, case, milestone)`
  - `delete_case(s, case)`, `delete_user(s, tg_id)`
  - `interval_values(s, scope: Literal["voiv","national"], voiv, purpose, from_m, to_m) -> list[int]`, `get_aggregate(...) -> Aggregate | None`
  - `recent_events(s, voiv, purpose, milestone, since: date) -> list[tuple[date, date]]`
  - `recompute_keys(s, keys: set[tuple[Voivodeship|None, Purpose, Milestone, Milestone]])`. Every write above calls it for the voivodeship key and the national key of each affected pair, in the same transaction.
  - `recompute_all(s)`
  - Every milestone write and delete enqueues an outbox row: `upsert` with payload `{title, date, description}`, or `delete` with the known event_id.

- [ ] **Step 1: Write the failing tests.** They use a real Postgres from `DATABASE_URL`, with a fresh schema per test via `alembic upgrade head` on a temp database.
  - `test_create_case_idempotent`: two `create_case` calls with the same `client_token` give one row.
  - `test_case_limit`: the 6th `create_case` raises `TooManyCases`.
  - `test_set_milestone_recomputes`: with 5 cases (`filed`, then `fingerprints` set), `get_aggregate(voiv, purpose, filed, fingerprints).n == 5` and the national n is 5.
  - `test_delete_case_enqueues_calendar_deletes_and_recomputes`: after `delete_case`, the aggregate n drops by 1 and the outbox holds a `delete` row for each milestone that had an event_id.
  - `test_delete_user_cascades`.
  - `test_outbox_payload_is_anonymous`: the payload title equals `"Mazowieckie · art. 142 · отпечатки"` for (mazowieckie, jdg, fingerprints), and the description contains only `"03.2026"`-style filing month text and no tg_id or case id.
- [ ] **Step 2: Run them and confirm they fail.** Run: `pytest tests/test_repo.py -v`.
- [ ] **Step 3: Implement** the models, the migration (hand-written, matching the tables above) and the repo. Calendar titles use the Russian labels from Task 5's locale file, so import the label table from `locales/ru.py`. This task creates the `VOIV_LABELS`, `PURPOSE_LABELS` and `MILESTONE_LABELS` constants there.
- [ ] **Step 4: Run them and confirm they pass.**
- [ ] **Step 5: Commit.** `feat: schema, migrations, repository with per-key recompute and calendar outbox`

### Task 5: i18n and UI building blocks (pure)

**Files:**
- Create: `src/czekachiko/i18n.py`, `locales/ru.py`, `locales/en.py`, `ui/keyboards.py`, `ui/screens.py`, `tests/test_i18n.py`, `tests/test_keyboards.py`, `tests/test_screens.py`

**Interfaces:**
- Consumes: `domain`, `stats.Forecast`, `stats.Aggregate`.
- Produces:
  - `t(lang: str, key: str, **kw) -> str`. It falls back to `ru` for an unknown lang and raises KeyError for an unknown key.
  - `CallbackData` classes (aiogram `CallbackData`): `Nav(to: str, case_id: int = 0)`, `Pick(field: str, value: str)`, `Day(y:int, m:int, d:int)`, `Month(y:int, m:int)`, `Confirm(answer: str)`.
  - `date_picker(lang, year, month, today) -> InlineKeyboardMarkup`: a 7-column grid. Future days render as `·` with a noop callback. `›` is hidden when the next month is after today's month. The last row holds "Today", "Yesterday" and Cancel.
  - `enum_picker(lang, field, values, labels, cols=2) -> InlineKeyboardMarkup` with Back and Cancel.
  - Screen renderers returning `(str, InlineKeyboardMarkup)`: `main_menu(lang)`, `privacy(lang)`, `cases_list(lang, cases)`, `case_view(lang, case, forecast)`, `stats_view(lang, voiv, purpose, aggregates, who_now_fp, who_now_dec)`, `settings_view(lang, user)`, `calendar_view(lang, url|None)`, `outlier_prompt(lang, voiv, from_m, to_m, typical: Aggregate, value: int)`.
  - Every non-root screen carries the ⬅️ Back and 🏠 Menu buttons.
- Copy rules: friendly, a 🐕 on the main menu, no jokes in errors. `case_view` always ends with the line meaning "the date in the letter is not a forecast; this is based on people's data, not official". `privacy` states what is stored (Telegram id, voivodeship, purpose, dates), that milestones appear anonymously in a public calendar, and how to delete.

- [ ] **Step 1: Write the failing tests.**
  - `test_locales_have_same_keys`: `set(ru.MESSAGES) == set(en.MESSAGES)`.
  - `test_date_picker_disables_future`: for today = 2026-10-29 in month 2026-10, the days 30 and 31 have the noop callback, and there is no `›` button.
  - `test_every_screen_has_menu_button`: every renderer except `main_menu` has a button whose callback data packs `Nav(to="menu")`.
  - `test_case_view_has_disclaimer` (ru and en).
  - `test_outlier_prompt_mentions_range`: the text contains `"90"`, `"240"` and `"610"` for typical p10 = 90, p90 = 240 and value 610.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them and confirm they pass.**
- [ ] **Step 5: Commit.** `feat: i18n (ru/en), date picker, screen renderers`

### Task 6: Handlers, FSM storage, wiring

**Files:**
- Create: `src/czekachiko/fsm_storage.py`, `handlers/*.py`, `src/czekachiko/__main__.py`, `tests/test_handlers.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `PgStorage(BaseStorage)` backed by the `fsm` table.
  - `build_dispatcher(settings, session_factory) -> Dispatcher`.
  - `async def main()`, which runs migrations (`alembic upgrade head` via the API), calls `set_my_commands` for ru and en (`start, cases, add, stats, calendar, settings, help, cancel`), starts the calendar worker if enabled, then starts polling.
- Behaviour:
  - A single live message: navigation calls `edit_text`. `TelegramBadRequest` "message is not modified" is swallowed. If the edit fails for any other reason, a new message is sent.
  - The add wizard states are `voiv → purpose → channel → filed → extra milestones (loop: pick milestone or Done → date)`. A `client_token` is generated when the wizard starts and is stored in FSM data.
  - When a milestone date is entered, run `validate_milestones`. Errors re-show the picker with the localised error. Then compute the interval for each affected pair and call `stats.is_suspicious` against `interval_values`. If it is suspicious, show `outlier_prompt`. ✅ saves with `confirmed_outlier=True`, ✏️ re-shows the picker.
  - On date steps, typed text goes to `parse_date`. On every other step, text gets "please use the buttons" plus a re-render.
  - `/cancel` and ✖️ clear the FSM and show the menu.
  - A callback for an unknown or deleted case, or an unparseable callback, shows the main menu.
  - Settings handle language (persisted, then re-render), the reminders toggle (persisted, unused) and "Delete all my data" with a confirmation step.
  - `ThrottleMiddleware(rate=5, per=3.0, ban_after_per_min=40, ban_seconds=600)` is an outer middleware with in-memory buckets keyed by tg_id. The dispatcher runs with `tasks_concurrency_limit=20` (or a semaphore).

- [ ] **Step 1: Write the failing tests.** Handler unit tests with aiogram `Bot` mocked (`AsyncMock`) and a real DB session:
  - `test_start_shows_menu_and_privacy` for a new user.
  - `test_add_wizard_creates_case`: drive callbacks voiv → purpose → channel → Day(2026,3,6) → Done. One case exists with `filed` 2026-03-06.
  - `test_text_on_button_step_is_rejected`: the text "Mazowieckie" at the voiv step creates nothing and the reply contains the localised "buttons" hint.
  - `test_typed_date_accepted`: "06.03.2026" at the filed step works like the Day button.
  - `test_stale_case_callback_shows_menu`: `Nav(to="case", case_id=999)` renders the main menu with no exception.
  - `test_throttle_drops_burst`: 6 updates within 1 s from one user means the 6th handler is not called. `test_throttle_bans_flooder`: 41 updates within a minute means updates are ignored until 600 s later (use a fake clock).
  - `test_outlier_confirm_flow`: with 8 seeded cases and a 610-day interval, the prompt appears. ✅ stores `confirmed_outlier=True`.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement** the storage, the routers, `build_dispatcher` and `main`.
- [ ] **Step 4: Run them and confirm they pass.**
- [ ] **Step 5: Commit.** `feat: bot handlers, Postgres FSM storage, entrypoint`

### Task 7: Calendar sync and admin

**Files:**
- Create: `src/czekachiko/calendar_sync.py`, `handlers/admin.py` (if not already present), `tests/test_calendar_sync.py`, `tests/test_admin.py`

**Interfaces:**
- Produces:
  - `class CalendarClient(Protocol)`: `async insert(calendar_id, title, day: date, description) -> str`, `async update(calendar_id, event_id, title, day, description)`, `async delete(calendar_id, event_id)`.
  - `GoogleCalendarClient(service_account_json_path)` implements it over the REST API with a `google.oauth2.service_account` token, scope `https://www.googleapis.com/auth/calendar`, and all-day events (`start.date`, `end.date` = day + 1).
  - `async drain_outbox(session_factory, client, calendar_id, now) -> int`: processes due rows, stores `event_id` in `calendar_events`, and deletes the outbox row on success. On failure it increments `attempts` and sets `next_try_at = now + min(2**attempts, 360) minutes`. A delete with no event_id is just dropped.
  - `async run_calendar_worker(...)`: loops `drain_outbox` every 30 s and never raises.
  - `/admin`, only for `admin_tg_id`, shows case counts per voivodeship and the 10 newest cases (id, voiv, purpose, filed month). `/admin recompute` calls `recompute_all`. Anyone else gets the main menu, with no hint that the command exists.
- Calendar disabled: the worker is not started, outbox rows still accumulate (so enabling later backfills), and `calendar_view` shows "coming soon".

- [ ] **Step 1: Write the failing tests** with a `FakeCalendarClient`:
  - `test_drain_inserts_and_records_event_id`
  - `test_drain_update_uses_existing_event_id`
  - `test_drain_failure_backs_off`: a client that raises gives `attempts == 1` and `next_try_at > now`.
  - `test_admin_hidden_for_others`, `test_admin_recompute`
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them and confirm they pass.**
- [ ] **Step 5: Commit.** `feat: Google Calendar outbox sync and admin commands`

### Task 8: Container, compose, deploy and backup scripts

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `scripts/deploy.sh`, `scripts/backup.sh`, `tests/test_compose.py`

**Interfaces:**
- Compose project name `czekachiko`. Services:
  - `bot`: built from the Dockerfile (python:3.12-slim, non-root user, `python -m czekachiko`), `env_file: .env`, networks `db` and `egress`, `mem_limit: 200m`, `read_only: true` with tmpfs `/tmp`, `restart: unless-stopped`, `security_opt: [no-new-privileges:true]`, and a mount of `./secrets/google-sa.json:/run/secrets/google-sa.json:ro` that is optional.
  - `db`: `postgres:16-alpine`, network `db` only, named volume, `mem_limit: 150m`, `restart: unless-stopped`, and a healthcheck using `pg_isready`.
  - Networks: `db: {internal: true}`, `egress: {}`.
  - **No `ports:` anywhere.** Both services set `cpus`, `pids_limit: 128` and `logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}`.
- `scripts/deploy.sh`:
  1. Source `deploy.env` (`DEPLOY_HOST`, `DEPLOY_PATH`) and fail if it is missing.
  2. Over ssh, read `MemAvailable` from `/proc/meminfo` and abort if it is below 500 MB.
  3. Snapshot `docker ps --format '{{.Names}} {{.Status}}'` for the containers that are not czekachiko.
  4. `rsync` the repo, excluding `.git`, `.env`, `deploy.env`, `secrets/` and `backups/`.
  5. `scp` the `.env` and set mode 600. Copy `secrets/google-sa.json` the same way if it exists.
  6. Run `docker compose -p czekachiko up -d --build`.
  7. Wait for health, then compare the other containers' snapshot. The names must be identical, and none may have restarted (the "Up …" duration did not reset). On mismatch, print it loudly.
  8. Install the backup cron line idempotently.

  It never prints `.env` contents.
- `scripts/backup.sh`: `docker compose -p czekachiko exec -T db pg_dump -U … | gzip` into `$DEPLOY_PATH/backups/YYYY-MM-DD.sql.gz`, then delete backups older than 14 days.

- [ ] **Step 1: Write the failing test.** `test_compose_has_no_published_ports_and_internal_db` parses `docker-compose.yml` with PyYAML: no service has a `ports` key, every service has `mem_limit`, `cpus`, `pids_limit` and log rotation, `networks.db.internal is True`, `db` is only on `db`, and `bot` is on `db` and `egress`.
- [ ] **Step 2: Run it and confirm it fails.**
- [ ] **Step 3: Implement** the Dockerfile, compose and both scripts (`set -euo pipefail`, shellcheck-clean).
- [ ] **Step 4: Verify.** Run `pytest tests/test_compose.py -v`, then `docker compose -p czekachiko-local config` (expected to be valid), then `docker compose -p czekachiko-local up -d db` followed by `pytest` against it. Run `gitleaks detect --no-banner`: no leaks.
- [ ] **Step 5: Commit.** `feat: container, compose with isolated network, deploy and backup scripts`

### Task 9: Publish, deploy, verify live

**Files:**
- Modify: none in the public repo. Host-specific notes go to the maintainer's private infrastructure docs.

- [ ] **Step 1: Pre-flight.** `gitleaks detect` over the full history. `git grep -nE '([0-9]{1,3}\.){3}[0-9]{1,3}'` finds nothing outside test fixtures. The local `.env` holds `BOT_TOKEN` (check that the key exists, never print the value).
- [ ] **Step 2: Host security check (read-only).** Over ssh, run `fail2ban-client status sshd`, `ufw status verbose` (or `nft list ruleset | head`) and `ss -tlnp`. Confirm that fail2ban is active and that the czekachiko containers added no listening port. Report gaps to the maintainer. **Do not change host firewall or fail2ban config in this plan**, because hardening the VPN host is separate work in its own repo.
- [ ] **Step 3: Push** to `origin master`.
- [ ] **Step 4: Deploy.** Run `scripts/deploy.sh`. Expected: memory check passes, containers healthy, other-container snapshot unchanged.
- [ ] **Step 5: Live check.** In Telegram, `/start` renders the menu and the privacy text. Add a test case, check the forecast shows "not enough data", delete the case, and check that `/admin` works for the admin.
- [ ] **Step 6: Record the host notes privately.** Note the location, compose project, backup path and rollback (`docker compose -p czekachiko down`, the volume is kept) in the maintainer's private infrastructure docs.
