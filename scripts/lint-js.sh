#!/bin/sh
# Contrôle statique du front : eslint (version épinglée, via npx) sur i18n.js + app.js + stats.js concaténés, car ils partagent la portée globale.
#   scripts/lint-js.sh        # nécessite Node 20+ ; télécharge eslint une fois (cache npm)
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "$root/.lint-js.XXXXXX")  # dans le dépôt : la config ne s'applique qu'aux fichiers sous son dossier
trap 'rm -rf "$tmp"' EXIT
line=1
: > "$tmp/bundle.js"
for f in i18n app stats; do
  echo "$f.js -> ligne $line du paquet"
  cat "$root/app/static/$f.js" >> "$tmp/bundle.js"
  echo >> "$tmp/bundle.js"
  line=$((line + $(wc -l < "$root/app/static/$f.js") + 1))
done
cd "$root"
npx --yes eslint@10.12.0 --config "$root/eslint.config.mjs" --no-config-lookup "$tmp/bundle.js"
echo "JS : aucune variable indéfinie ni redéclaration."
