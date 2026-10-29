#!/usr/bin/env bash
# Deploy to the host named in deploy.env. Touches only the "czekachiko" compose project.
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f deploy.env ]] || { echo "deploy.env missing (copy deploy.env.example)"; exit 1; }
# shellcheck disable=SC1091
source deploy.env
: "${DEPLOY_HOST:?set in deploy.env}" "${DEPLOY_PATH:?set in deploy.env}"
bash scripts/lib/validate-path.sh "$DEPLOY_PATH"
[[ -f .env ]] || { echo ".env missing (copy .env.example)"; exit 1; }
grep -q '^BOT_TOKEN=.' .env || { echo ".env has no BOT_TOKEN"; exit 1; }

SSH=(ssh -o BatchMode=yes "$DEPLOY_HOST")

avail=$("${SSH[@]}" "awk '/MemAvailable/ {print int(\$2/1024)}' /proc/meminfo")
echo "host MemAvailable: ${avail} MB"
(( avail >= 500 )) || { echo "ABORT: less than 500 MB available on the host"; exit 1; }

others() {
  "${SSH[@]}" "docker ps -q | xargs -r docker inspect -f '{{.Name}} {{.State.StartedAt}}' \
    | grep -v '^/czekachiko-' | sort" || true
}
before=$(others)

"${SSH[@]}" "mkdir -p '$DEPLOY_PATH/secrets' '$DEPLOY_PATH/backups' && chmod 700 '$DEPLOY_PATH'"
rsync -az --delete \
  --exclude .git --exclude .venv --exclude .env --exclude deploy.env --exclude db.env \
  --exclude runtime.env --exclude secrets/ --exclude backups/ --exclude .superpowers/ \
  --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
  ./ "$DEPLOY_HOST:$DEPLOY_PATH/"
scp -q .env "$DEPLOY_HOST:$DEPLOY_PATH/.env"
if [[ -f secrets/google-sa.json ]]; then
  scp -q secrets/google-sa.json "$DEPLOY_HOST:$DEPLOY_PATH/secrets/google-sa.json"
fi

"${SSH[@]}" bash -s -- "$DEPLOY_PATH" "${ADMIN_TG_ID:-}" "${CALENDAR_ID:-}" \
  "${CALENDAR_PUBLIC_URL:-}" <<'REMOTE'
set -euo pipefail
cd "$1"
chmod 600 .env
# The bot runs as uid 10001 inside the container; give it the key, nobody else.
chown -R 10001:10001 secrets
chmod 700 secrets
find secrets -type f -exec chmod 600 {} +
if [[ ! -f db.env ]]; then
  pw=$(openssl rand -hex 24)
  printf 'POSTGRES_USER=czekachiko\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=czekachiko\nDATABASE_URL=postgresql+asyncpg://czekachiko:%s@db:5432/czekachiko\n' \
    "$pw" "$pw" > db.env
  chmod 600 db.env
fi
{
  echo "ADMIN_TG_ID=${2:-}"
  echo "CALENDAR_ID=${3:-}"
  echo "CALENDAR_PUBLIC_URL=${4:-}"
  if [[ -f secrets/google-sa.json ]]; then
    echo "GOOGLE_SERVICE_ACCOUNT_JSON=/run/secrets/google-sa.json"
  fi
} > runtime.env
chmod 600 runtime.env
chmod +x scripts/backup.sh
docker compose -p czekachiko up -d --build --remove-orphans
for _ in $(seq 1 30); do
  if docker compose -p czekachiko logs bot 2>&1 | grep -q "Start polling"; then
    echo "bot is polling"; break
  fi
  sleep 2
done
docker compose -p czekachiko ps
cron="17 3 * * * $1/scripts/backup.sh $1 >> $1/backups/backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'czekachiko.*backup.sh' || true; echo "$cron" ) | crontab -
REMOTE

after=$(others)
if [[ "$before" == "$after" ]]; then
  echo "OK: other containers untouched ($(wc -l <<<"$after" | tr -d ' ') checked)"
else
  echo "!!! WARNING: other containers changed during deploy:"
  diff <(echo "$before") <(echo "$after") || true
  exit 2
fi
