# Czekachiko 🐕 | Karta Pobytu

[@czekachiko_bot](https://t.me/czekachiko_bot) is a Telegram bot that estimates when your Polish residence-permit case (*karta pobytu*) will reach its next step: the fingerprint appointment, the decision, or the card itself. Its forecasts come from anonymous milestones that other applicants share, grouped by voivodeship and the purpose of stay. Every milestone also appears anonymously in a public calendar.

The bot speaks Russian by default, and English is available in settings. Case data is entered with buttons and dates only. Free text exists in two places: names of your own checklist documents, which only you see, and the feedback form, which only the maintainer sees. Neither feeds statistics, the calendar or share cards. The bot never messages you first.

## Mini App

Czekachiko runs as a Telegram Mini App: a React + TypeScript app in [`web/`](web/) that talks to the bot's HTTP API and identifies people by the `initData` Telegram signs. The bot itself opens the app, takes feedback, and answers inline queries (`@czekachiko_bot …`) with cards to share in any chat. Outside Telegram the app only shows a link to the bot. Every push to `master` that touches `web/` runs its tests and publishes it to GitHub Pages at `https://lartiquel.github.io/czekachiko/` ([workflow](.github/workflows/pages.yml)).

```bash
cd web
npm ci
npm test -- --run   # Vitest
npm run build       # type-check, then build to web/dist
```

`VITE_API_URL` sets the API address at build time and defaults to the production one. The production API accepts only the Pages origin and the production bot's signature, so trying changes end to end needs your own test bot and API: point `VITE_API_URL` at it, serve `npm run dev` over HTTPS and open that URL from the test bot. A normal browser only shows the open-in-Telegram screen.

Want to help? See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
