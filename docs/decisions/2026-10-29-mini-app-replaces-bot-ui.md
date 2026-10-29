# 2026-10-29: the Mini App replaces the button-based bot UI

**Decision.** The main interface moves from bot buttons to a Telegram Mini App (`web/`, GitHub Pages) backed by an HTTP API (`czekachiko.api`). The bot keeps three jobs: support (feedback and replies), inline cards (`@czekachiko_bot …`), and the button that opens the app.

**Why.** The bot grew past what inline keyboards handle well: cases, a milestone timeline, forecasts, a document checklist with custom items, comparing voivodeships, 16 calendars and sharing. Each tap is a server round-trip, so date picking means paging month by month and screens get cramped. A Mini App renders all of this natively, with a real date input, lists and the Telegram theme, and still identifies people by their signed Telegram account.

**The old UI is archived, not lost.**
- Tag `v1-bot-ui` and branch `archive/bot-ui` point to the last version where everything ran on bot buttons.
- Branch `archive/bot-picker-wip` keeps an unfinished speed-up for the button date picker (a month grid and a separate throttle budget for navigation).
- The button screens also stay in the code for now, reachable through their commands and callbacks, until the Mini App has proven itself.

**Cost.** One more moving part: a public API behind a Cloudflare Tunnel (`czekachiko-api.artware.me`), with Telegram initData auth, rate limits and strict CORS. The design and API contract are in `docs/superpowers/specs/2026-10-29-mini-app-design.md`.
