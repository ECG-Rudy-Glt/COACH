#!/usr/bin/env bash
# Resets an account password (server administrator). Réinitialise le mot de passe d'un compte : génère un mot de passe temporaire sans caractères ambigus,
# ferme les sessions du compte et affiche le mot de passe une seule fois. Usage : scripts/reset_password.sh email@exemple.fr
set -euo pipefail
EMAIL="${1:?usage: $0 email}"
# COACH_EXEC picks how to reach the app container (default: Docker Compose; k8s: "kubectl -n sport-coach exec -i deploy/sport-coach --")
COACH_EXEC="${COACH_EXEC:-docker compose exec -T app}"
# shellcheck disable=SC2086
$COACH_EXEC env TARGET_EMAIL="$EMAIL" python - <<'PY'
import os, secrets
from app.auth import hash_password
from app.main import app

repo = app.state.repo
acct = repo.get_account(os.environ["TARGET_EMAIL"].strip().lower())
if not acct:
    raise SystemExit("compte introuvable")
alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
pw = "".join(secrets.choice(alphabet) for _ in range(14))
repo.set_password(acct["id"], hash_password(pw), None)  # ferme aussi toutes les sessions
print("Mot de passe temporaire :", pw)
print("Changez-le dans Profil, Compte, Changer mon mot de passe.")
PY
