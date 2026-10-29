# Archive: the button-based bot UI (v1)

Until 2026-10-29 everything in Czekachiko ran on Telegram bot buttons. The code of that version is preserved under the tag **`v1-bot-ui`** and the branch **`archive/bot-ui`**:

```bash
git checkout v1-bot-ui   # browse or deploy the old version
```

On 2026-10-30 the button screens were removed from `src/`. The bot now keeps `/start` with the app launcher, feedback, `/admin` and inline mode; buttons left in old chats answer with a short "open the app" notice.

## What the bot UI did

| Area | How it worked in the bot |
|---|---|
| **Start and navigation** | `/start` gave one short message with a persistent reply keyboard (➕ Add case, 📂 My cases, 📊 Timelines, 📅 Calendar, ⚙️ Settings, ❓ How it works, 📣 Share, ✉️ Contact us), plus the Telegram command menu with emoji descriptions. One live screen was edited in place, and the bot deleted the user's inputs and its previous screens so the chat stayed clean. |
| **Adding a case** | A 4-step wizard: voivodeship, purpose, channel (MOS / paper), filing date. Dates came from an inline calendar of buttons (month paging, future days disabled, Today/Yesterday) or were typed as `DD.MM.YYYY`. Idempotent against double taps. At most 5 cases per user. |
| **Case card** | The full milestone chain (filed → case number → fingerprint appointment letter → fingerprints given → decision → card): own date, days since filing, and the typical mean/min/max with the case count. Below it, a forecast window for the next milestone, adjusted for time already waited, plus the disclaimer. Buttons: mark a milestone, documents, send to chat, delete. |
| **Validation** | No future dates, nothing before 2015, nothing before filing, fingerprints ≤ decision ≤ card. Outliers (IQR fence, n ≥ 8) prompted "please check the dates" with a confirm option. |
| **Documents checklist** | A typical list per purpose of stay (tick + date), plus up to 15 custom documents (name ≤ 60 characters) per case, with rename and delete. Visible to the owner only. |
| **Timelines** | Per voivodeship + purpose: the chain with mean/min/max and counts, and "who is being called now". Compare up to 6 voivodeships with checkboxes. |
| **Sharing** | «📤 Send to chat» opened Telegram's chat picker with an inline card: stats, a comparison, or your own case (owner-checked). Inline mode in any chat: `@czekachiko_bot` + voivodeship or city names (RU/PL aliases). |
| **Public calendars** | 16 Google calendars, one per voivodeship, owned by a service account. Each milestone became an anonymous all-day event carrying the case's full timeline. Synced through a DB outbox with retries. |
| **Feedback** | «✉️ Contact us» took one text message (≤ 1000 characters, 5 per hour) and delivered it to the maintainer. A reply to it reached only that user. A disappearing confirmation. |
| **Settings** | RU/EN (with a disappearing toast and keyboard refresh), the reminders toggle (inactive by design: the bot never writes first), delete all my data. |
| **Protection** | Per-user flood control (5 updates per 3 s, mute after 40 per minute), per-user event isolation, container limits, no published ports. |

## Why it changed

The bot outgrew its buttons. Cases, a timeline, forecasts, a document checklist with custom items, comparisons, 16 calendars and sharing all had to fit into inline keyboards. Every tap is a round trip to the server, so picking a date six months back meant paging month by month (and rapid paging hit the flood limit), and screens got cramped.

A Telegram Mini App renders the same features natively: a real date input, lists and the Telegram theme. It still identifies people by their signed Telegram account, so no logins. The bot keeps what it is good at: support, replies, inline cards and the button that opens the app.

Full decision record: [`docs/decisions/2026-10-29-mini-app-replaces-bot-ui.md`](../../docs/decisions/2026-10-29-mini-app-replaces-bot-ui.md). Original design: [`docs/superpowers/specs/2026-10-29-czekachiko-bot-design.md`](../../docs/superpowers/specs/2026-10-29-czekachiko-bot-design.md). Mockups: [`docs/mockups/2026-10-29-bot-flow.html`](../../docs/mockups/2026-10-29-bot-flow.html).
