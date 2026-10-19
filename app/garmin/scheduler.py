"""Synchronisation Garmin automatique (tous les N heures), dans le processus de l'application (un seul réplica)."""
import logging
import os
import threading
import time
from typing import Any

from app.garmin.api import sync_user

log = logging.getLogger("sport-coach.sync")


def run_once(repo: Any, gateway: Any) -> dict[str, int]:
    ok = failed = 0
    for uid in repo.list_garmin_users():
        try:
            sync_user(repo, gateway, uid)
            ok += 1
        except Exception as e:  # une erreur ne doit jamais arrêter les autres ; jamais d'identifiants dans les logs
            failed += 1
            log.warning("sync utilisateur %s : %s", uid, type(e).__name__)
        time.sleep(float(os.environ.get("SYNC_PAUSE_S", "2")))
    return {"ok": ok, "failed": failed}


def start(repo: Any, gateway: Any) -> threading.Thread | None:
    if os.environ.get("AUTO_SYNC", "") != "1":
        return None
    hours = max(1.0, float(os.environ.get("GARMIN_SYNC_HOURS", "6")))

    def loop() -> None:
        time.sleep(120)
        while True:
            try:
                r = run_once(repo, gateway)
                log.info("synchronisation Garmin : %s", r)
            except Exception as e:
                log.warning("cycle de synchronisation : %s", type(e).__name__)
            time.sleep(hours * 3600)

    t = threading.Thread(target=loop, name="garmin-sync", daemon=True)
    t.start()
    return t
