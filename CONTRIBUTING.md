# Contributing to Czekachiko

Thanks for helping! Czekachiko is a Telegram bot ([@czekachiko_bot](https://t.me/czekachiko_bot)) that forecasts Polish residence-permit timelines from anonymous data people share.

## How contributions work

Only the maintainer can push to this repository. Everyone else contributes through forks and pull requests:

1. **Open an issue first** for anything bigger than a typo, so we can agree on the approach before you spend time on it.
2. **Fork** the repo and create a branch from `master`.
3. Make your change, with tests where it makes sense (see below).
4. **Open a pull request** against `master`. Describe what changed and why, and how you checked it.
5. The maintainer reviews it. CI must pass before anything is merged, and only the maintainer merges.

Workflows from forked PRs run only after the maintainer approves them.

## Ground rules

- **Never commit secrets.** No bot tokens, passwords, API keys or service-account JSON. Real values live in `.env`, which is gitignored. Add new settings to `.env.example` with a placeholder value. A `gitleaks` check runs on every push and PR, and a PR that trips it will not be merged.
- **No real personal data**, anywhere: code, tests, fixtures, screenshots or issues. That means no names, PESEL, case numbers or real case dates. Use invented examples.
- **No infrastructure details.** Leave out IP addresses, hostnames and server paths. Docs refer to "the host".
- **Keep the privacy model.** The bot must never accept free-text input from users and must never message anyone first. Changes that weaken either will not be accepted.
- Forecasts must stay honest. When there is too little data, the bot says so instead of guessing.

## Development setup

```bash
cp .env.example .env          # fill in your own test bot token from @BotFather
docker compose up --build     # bot + Postgres locally
```

Use **your own test bot** from [@BotFather](https://t.me/BotFather), never the production one.

## Tests and style

```bash
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

Priority areas for tests are date parsing and validation, statistics and percentiles, outlier detection and forecasts.

## Translations

User-facing text is available in Russian (default) and English. If you add or change text, update both languages. Help with Polish or Ukrainian is welcome. Open an issue first.

## Reporting a security problem

Please **don't open a public issue**. Use GitHub's private vulnerability reporting instead: the **Security** tab, then **Report a vulnerability**.

## Licence

By contributing you agree that your contribution is licensed under the [MIT Licence](LICENSE).
