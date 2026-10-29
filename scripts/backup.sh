#!/usr/bin/env bash
# Nightly dump of the czekachiko database; keeps 14 days.
set -euo pipefail
cd "${1:-$(dirname "$0")/..}"
mkdir -p backups
f="backups/$(date +%F).sql.gz"
docker compose -p czekachiko exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$f"
chmod 600 "$f"
find backups -name '*.sql.gz' -mtime +14 -delete
