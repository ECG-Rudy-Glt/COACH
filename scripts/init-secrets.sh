#!/usr/bin/env bash
# Creates ./secrets/* (directory 700, files 644, never committed) and .env from .env.example. Idempotent: existing files are kept.
#   scripts/init-secrets.sh            database password + Garmin token encryption key
#   scripts/init-secrets.sh --vapid    also generate Web Push (VAPID) keys (needs Docker; downloads `cryptography` once)
# You put your LLM API key in secrets/llm_api_key yourself (or leave it empty to run without AI).
set -euo pipefail
cd "$(dirname "$0")/.."
# Docker mounts file secrets with the host file's mode and the app runs as an unprivileged uid, so the files must be
# world-readable; the 700 directory is what keeps other host users out.
umask 022
mkdir -p secrets && chmod 700 secrets
make() { [ -s "secrets/$1" ] || { printf '%s' "$2" > "secrets/$1"; echo "created secrets/$1"; }; }
touch_empty() { [ -e "secrets/$1" ] || { : > "secrets/$1"; echo "created secrets/$1 (empty, optional)"; }; }

make postgres_password "$(openssl rand -base64 33 | tr -d '/+=\n' | cut -c1-32)"
make secrets_key "$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')"   # Fernet key: 32 random bytes, url-safe base64
for f in llm_api_key smtp_password ntfy_token vapid_private_key; do touch_empty "$f"; done
if [ "${1:-}" = "--vapid" ]; then
  read -r priv pub < <(docker run --rm python:3.12-slim sh -c 'pip install -q cryptography >/dev/null 2>&1 && python -' < scripts/gen_vapid.py)
  printf '%s' "$priv" > secrets/vapid_private_key
  if grep -q '^VAPID_PUBLIC_KEY=' .env 2>/dev/null; then sed -i "s|^VAPID_PUBLIC_KEY=.*|VAPID_PUBLIC_KEY=$pub|" .env; else echo "VAPID_PUBLIC_KEY=$pub" >> .env; fi
  echo "VAPID keys generated (public key written to .env)"
fi
[ -e .env ] || { cp .env.example .env; echo "created .env — review it"; }
chmod 644 secrets/*
chmod 600 .env
