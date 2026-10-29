# Czekachiko | Karta Pobytu: design

*2026-10-29. Telegram bot that crowd-sources Polish residence-permit timelines and turns them into per-voivodeship forecasts.*

## Why

Applicants for *zezwolenie na pobyt czasowy* get no realistic timeline from the urząd. In Warsaw the decision date printed in the wezwanie (e.g. 25.01.2027) is not a forecast: staff themselves say it may slip by about a year. People keep their own guesses in Telegram chats and forums. This bot collects anonymous case milestones from applicants and answers two questions: *when will my next step come* and *who is being called right now*.

It is a public product, promoted in a legalization community channel on Telegram, so strangers will use it. It must be clear from the first screen, keep minimal and anonymous data, and stay up.

The name refers to Hachikō, the dog who waited years at a station. The name works in Russian (Хатико), English and Polish. Bot: **`@czekachiko_bot`**, display name *Czekachiko | Karta Pobytu*: Polish *czeka*, "waits", plus Hachiko. Repo: `github.com/lArtiquel/czekachiko` (public).

## Goals

- A user adds one or more of their own cases, marks milestones with dates, and edits them later.
- For every case the bot shows the next milestone's forecast window: p10–p90, median, and how many cases it is based on.
- A per-voivodeship view shows typical durations between milestones, plus "who is being called now" (which filing month is currently getting fingerprints or decisions).
- A public Google Calendar with anonymous events, listing voivodeship, purpose and milestone only.
- Russian by default, English switchable in settings.
- The maintainer's own case is the first record, entered through the bot like any other. No personal case data is ever committed to the repo.

## Non-goals (for now)

- Reminders or any message the user did not ask for. The setting exists but is off and does nothing yet. **The bot never writes first.**
- A website or our own iCal endpoint. Only the Google Calendar's own public link is used.
- Seeding the database from forums or official statistics. Possibly a later, separate step.
- Admin web panel or moderation UI.
- Languages beyond RU/EN.

## Anti-goals (a failure even if it works)

- Anything that collects identifying data: names, PESEL, case numbers, free text. **The bot has no free-text input at all**, only buttons and dates.
- Any impact on other services sharing the host: their data, their uptime, or a restart of their containers.
- Forecasts that pretend to precision. With too little data the bot says so instead of inventing a number.
- A chat that fills up with bot messages.
- The maintainer's personal email showing up anywhere public.
- A secret, a host address or a server path from the maintainer's infrastructure landing in this public repo.

## Domain model

**Voivodeship:** the 16 Polish voivodeships, chosen by buttons.

**Purpose:** `praca` (art. 114), `jdg` (art. 142, działalność gospodarcza), `studia`, `rodzina`, `inne`. These are the forecast grouping keys.

**Filing channel:** `mos` (online, the only channel for new residence applications since 27.04.2026) or `paper` (in person or by post, older cases). Stored, shown, and usable as a filter later. Not a grouping key in v1, because the data would split too thin.

**Milestones:** ordered. Each has an optional date. Fixed list for v1:

1. `filed`: application submitted (required)
2. `case_number`: case number or sygnatura received
3. `braki`: wezwanie to remedy formal defects received (optional, may not happen)
4. `fingerprints`: fingerprints given (in-person visit)
5. `decision`: decision issued
6. `card`: card collected

Order validation: each set milestone date is at or after `filed`, and `fingerprints ≤ decision ≤ card`. `braki` and `case_number` only need to be at or after `filed`. No date may be in the future. `filed` may not be earlier than 2015-01-01.

**Case:** belongs to a Telegram user id. At most 5 cases per user. It holds voivodeship, purpose, channel and milestone dates. Each date carries `confirmed_outlier: bool` (see below). Soft-delete is not needed: deleting a case removes it and triggers a recompute.

**User:** Telegram user id (stored as-is; it is not shown to anyone), language (`ru`/`en`, default `ru`), reminders flag (default off, unused). "Delete all my data" removes the user and their cases and recomputes.

## Statistics and forecasting

**Intervals.** For each case, compute the day count from `filed` to each later milestone it has, plus `fingerprints → decision` and `decision → card`. Each interval is keyed by **(voivodeship, purpose, from_milestone, to_milestone)**.

**Aggregates table.** For each key, store n, p10, median, p90, min, max and `updated_at`. **Recompute only the affected keys on every write**: create, edit, delete case or user. Reads use the stored aggregates, never raw recomputation. Every submission updates the shared numbers, and the next user sees them.

**Which intervals exist.** Forecast targets are `fingerprints`, `decision` and `card` only. `case_number` and `braki` are recorded and shown, but never forecast. Anchors are `filed`, `fingerprints` and `decision`. Computed pairs: filed→case_number, filed→fingerprints, filed→decision, filed→card, fingerprints→decision, decision→card.

**Forecast for a case.** Target T is the first of fingerprints, decision and card that the case does not have yet. Anchor K is the latest known milestone among filed, fingerprints and decision that comes before T, with date d. Use key (voiv, purpose, K→T) if n ≥ 5. Otherwise fall back to (voiv, purpose, filed→T). Otherwise use the national figure (all voivodeships, same purpose), labelled as such. Otherwise say "not enough data yet, add your case to help".

**Conditioning on time already waited**. Let e be the days elapsed since d. Use only completed intervals with value ≥ e, and show their p10–p90 and median from d as the window. Say "based on n cases that waited at least as long as you". If fewer than 5 such intervals exist, show "you have waited longer than X of Y completed cases in this group" and no window. This prevents windows that are already in the past. It also partly corrects the early bias toward fast cases. The screen says plainly that it is computed from completed cases. Raw min/max still appear as "fastest / slowest seen". The forecast screen always carries the line "the date in the letter is not a forecast; this is based on people's data, not official".

**"Who is being called now."** For voivodeship + purpose, take milestone events (fingerprints, decision) whose date falls in the last 30 days. Show the range of their cases' filing months, for example "fingerprints are currently going to people who filed ≈ March–April 2026". Require at least 3 events in the window, otherwise say there is too little data.

**Outliers.** There are two tiers, checked when a date is entered:

1. *Hard invalid*: future date, wrong order, before 2015. Rejected with a hint, the date picker is shown again.
2. *Suspicious*: the key has n ≥ 8, and the new interval is outside [Q1 − 3·IQR, Q3 + 3·IQR]. The bot asks: *"In Mazowieckie it usually takes 90–240 days from filing to fingerprints, yours is 610. Please check the dates: the forecast for everyone depends on it."* Buttons: ✅ Correct, ✏️ Change. On confirm the date is stored with `confirmed_outlier = true` and **is counted** in the aggregates. Percentile windows absorb single outliers, and min/max show them honestly.

## Bot UX

- **First screen privacy line**: what is stored (Telegram id, voivodeship, purpose, dates), that nothing else is collected, that the calendar shows no identity, and that Settings → Delete removes everything. One short paragraph, also reachable from `/help`.

- **Telegram command menu** via `setMyCommands`, localised RU/EN: `/start` (main menu), `/cases`, `/add`, `/stats`, `/calendar`, `/settings`, `/help`, `/cancel`.
- **One live message per screen.** Navigation edits the message instead of sending new ones. Stale buttons never error: pressing one re-renders the right screen.
- Every screen has ⬅️ Back and 🏠 Menu. Multi-step input also has ✖️ Cancel. An abandoned flow resumes where it stopped (FSM state persisted in the DB, not in memory, so a restart does not lose it).
- **Inputs are constrained.** Enumerations are buttons only. Dates use an inline calendar keyboard (month grid, ‹ › month navigation, future days disabled) plus "Today" / "Yesterday" shortcuts. Typed dates are accepted in `DD.MM.YYYY`, `D.M.YYYY` and `YYYY-MM-DD`. Any other text gets "This doesn't look like a date, pick a day in the calendar" and the calendar again. On button-only steps typed text is politely ignored with a pointer back to the buttons.
- Screens follow the reviewed mockups: [`docs/mockups/2026-10-29-bot-flow.html`](../../mockups/2026-10-29-bot-flow.html) (all data in them is fabricated and the numbers are illustrative). Screens: start menu, add case wizard (voivodeship → purpose → channel → filed date → optional earlier milestones), my case (milestones, forecast, actions), stats by voivodeship, calendar link, settings (language, reminders [off], delete all my data).
- Copy tone: friendly and plain, with a Hachiko 🐕 touch and no jokes in error messages.

## Public Google Calendar

- A **Google service account** owns a dedicated calendar, shared publicly as read-only (ACL `default: reader`). Events are created by the service account, so its email is the creator. **The maintainer's personal email never appears.** The maintainer creates the Cloud project and service account and keeps the JSON key outside the repo. That is the only manual step.
- **Every milestone of every case is published automatically**, with no opt-in and no checkbox. The maintainer decided this on 2026-10-29. The first-screen privacy line says so.
- Each set milestone produces one all-day event titled `<Voivodeship> · <purpose label> · <milestone>`, for example `Mazowieckie · art. 142 · отпечатки`. The description holds the filing month only, for example "filed 03.2026". No user id, no case id.
- Edits and deletions update or remove the event. The mapping event_id ↔ (case, milestone) is stored in our DB.
- Calendar writes are **asynchronous and best-effort**: a failure is logged and retried later and never blocks the bot's reply. If no credentials are configured, the calendar feature is disabled and the `/calendar` screen says "coming soon".
- `/calendar` shows the calendar's public URL.

## Architecture and deployment

- **Stack:** Python 3.11+, aiogram 3, SQLAlchemy 2 async + asyncpg, Alembic, pydantic-settings. Google Calendar uses `google-api-python-client` + `google-auth`, or plain REST with service-account JWT. Builder's choice.
- **Long polling**, no webhook. The only network traffic is the bot's outbound connections to the Telegram and Google APIs.
- **Own compose project** with **its own Postgres 16 container** and a named volume. It never shares a database or a compose file with anything else on the host.
- **Nothing is reachable from outside except through Telegram.** No container publishes a port. Postgres sits on an `internal: true` Docker network that only the bot joins. The bot is additionally on a normal network for outbound internet. To reach the database, the maintainer runs `ssh` to the host and then `docker exec`.
- **Host:** any small Linux box with Docker. Memory limits are about 200 MB for the bot and about 150 MB for Postgres. The deploy script checks free memory first and aborts if headroom is under about 500 MB.
- **Deploy:** `scripts/deploy.sh` reads the target host and remote path from a local, gitignored `deploy.env`. It rsyncs the code, copies the local `.env` to the server with mode 600, and runs `docker compose -p hachiko up -d --build`. Migrations run on container start. `restart: unless-stopped`. It touches nothing outside the `hachiko` compose project.
- **Backups:** a nightly `pg_dump` from host cron into a backups directory, keeping 14 days. Off-site copy is out of scope for v1.
- **Verification after deploy:** the hachiko containers are healthy, `/start` replies, and a test case can be created and deleted. Every other container on the host keeps the same uptime and status (`docker ps` before and after).

## Open source and secrets

- **Public GitHub repo, MIT licence.** Contributions are welcome.
- **Secrets never enter git.** `.env`, `deploy.env`, `*.json` keys and `backups/` are gitignored. `.env.example` and `deploy.env.example` hold placeholders only. The source of truth is the maintainer's machine, backed up in a password manager. The server holds a copy only because the bot needs it to run.
- **Guards:** a `gitleaks` pre-commit hook, a `gitleaks` GitHub Action on every push and PR, and GitHub secret scanning with push protection turned on.
- **No infrastructure details in the repo:** no IPs, hostnames, SSH users or server paths. Docs say "the host". Mockups, fixtures and test data use invented cases only.
- Host-specific operating notes live in the maintainer's private infrastructure docs, not here.

## Constraints

- The host may run other production services. Deploy and operations touch only the `hachiko` compose project.
- No free-text storage anywhere.
- The Telegram bot token comes from the maintainer. The bot cannot be tested live until it exists.

## Bogus data

v1 has no purge UI. `/admin` (maintainer only, by `ADMIN_TG_ID`) shows counts per voivodeship and the 10 most recent cases with internal ids. Removing bogus data means the maintainer runs SQL by hand, followed by a recompute command `/admin recompute`.

## Left to the builder

Module layout, FSM implementation detail, the exact calendar keyboard, i18n mechanism (a simple dict or gettext), percentile method (linear interpolation is fine), test strategy (unit tests for stats/outliers/date parsing/validation are the priority), retry mechanism for calendar sync, logging format.

## Open items

1. The bot token from BotFather, and the chosen username.
2. A Google Cloud project + service-account JSON key for the calendar. The bot ships without it, and the calendar switches on when the key arrives.

