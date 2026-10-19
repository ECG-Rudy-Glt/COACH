"""Import de la bibliothèque : `python -m app.exercises.importer [--dry-run] [--if-empty]` (réseau requis ; relançable, mise à jour sans doublon)."""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from app.config import database_url
from app.exercises.sources import custom_exercises, free_exercise, merge, wger_exercise
from app.repo import PostgresRepo

WGER = "https://wger.de/api/v2"
FREE = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
ROOT = Path(__file__).resolve().parent.parent.parent


def get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "sport-coach-importer/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 : URLs constantes ci-dessus
        return json.load(r)


def fetch_wger() -> list[dict[str, Any]]:
    licenses = {lic["id"]: (lic["short_name"], lic.get("url")) for lic in get_json(f"{WGER}/license/")["results"]}
    out, url = [], f"{WGER}/exerciseinfo/?limit=100"
    while url:
        page = get_json(url)
        out += page["results"]
        url = page["next"]
        time.sleep(0.4)  # courtoisie envers le serveur public
    return out, licenses


def main(dry: bool, if_empty: bool = False) -> None:
    if if_empty and not dry:
        dsn = database_url()
        if not dsn:
            sys.exit("DATABASE_URL manquant")
        repo = PostgresRepo(dsn)
        repo.migrate(Path(os.environ.get("MIGRATIONS_DIR", ROOT / "db" / "migrations")))
        if repo.search_exercises(None, None, None, None, 1, 0)[1]:
            print("bibliothèque déjà importée : rien à faire (relancer sans --if-empty pour la mettre à jour)")
            return
    raw, licenses = fetch_wger()
    wger = [e for e in (wger_exercise(r, licenses) for r in raw) if e]
    free = [free_exercise(r) for r in get_json(FREE)]
    custom = custom_exercises(ROOT / "data" / "custom_exercises.yaml")
    merged = merge(wger, free, custom)
    media = sum(len(e.media) for e in merged)
    print(f"wger={len(wger)} free-exercise-db={len(free)} maison={len(custom)} -> {len(merged)} exercices, "
          f"{media} médias")
    if dry:
        return
    dsn = database_url()
    if not dsn:
        sys.exit("DATABASE_URL manquant")
    repo = PostgresRepo(dsn)
    repo.migrate(Path(os.environ.get("MIGRATIONS_DIR", ROOT / "db" / "migrations")))
    print(f"{repo.replace_exercises(merged)} exercices enregistrés")


if __name__ == "__main__":
    main("--dry-run" in sys.argv, "--if-empty" in sys.argv)
