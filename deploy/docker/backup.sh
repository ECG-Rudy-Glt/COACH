#!/bin/sh
# Daily logical dump of the database, kept BACKUP_KEEP_DAYS days. Runs inside the `backup` service (profile `backup`).
set -eu
: "${BACKUP_KEEP_DAYS:=14}"
export PGPASSWORD="$(cat /run/secrets/postgres_password)"
while true; do
  f="/backups/coach-$(date +%F).dump"
  pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$f.tmp" && mv "$f.tmp" "$f" && echo "backup ok: $f"
  find /backups -name 'coach-*.dump' -mtime "+$BACKUP_KEEP_DAYS" -delete
  sleep 86400
done
