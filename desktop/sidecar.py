"""Serveur COACH embarqué dans l'application de bureau (figé avec PyInstaller, voir build-sidecar.py).

Deux modes :
  coach-sidecar serve  --port N --data-dir D   lance l'application sur 127.0.0.1 uniquement
  coach-sidecar backup --data-dir D --dest FICHIER.zip   archive : copie cohérente de la base SQLite + dossier media/

Les secrets (clé LLM, clé de chiffrement Garmin) arrivent par variables d'environnement, posées par la coque
depuis le trousseau de l'OS : ce programme ne les écrit nulle part et ne les journalise pas.
Si le canal d'entrée standard se ferme (la coque s'est arrêtée, même brutalement), le serveur s'arrête aussi.
"""
import argparse
import os
import sqlite3
import sys
import tempfile
import threading
import zipfile
from pathlib import Path


def sqlite_path(data_dir: Path) -> Path:
    return data_dir / "coach.db"


def configure_environment(data_dir: Path) -> None:
    """Réglages imposés : aucune exposition réseau, premier compte seul, stockage dans le dossier utilisateur."""
    data_dir.mkdir(parents=True, exist_ok=True)
    media = data_dir / "media"
    media.mkdir(exist_ok=True)
    # COACH_DESKTOP_DATABASE_URL : surcharge réservée aux tests (valeur vide = stockage en mémoire).
    db_url = os.environ.get("COACH_DESKTOP_DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{sqlite_path(data_dir).as_posix()}" if db_url is None else db_url
    os.environ.update({
        "COOKIE_SECURE": "0",  # http local : un cookie Secure ne serait jamais renvoyé
        "ALLOWED_HOSTS": "127.0.0.1,localhost",
        "REGISTRATION": "first",
        "TRUST_PROXY": "0",
        "ENABLE_DOCS": "0",
        "MEDIA_DIR": str(media),
    })
    # Un `NOM_FILE` hérité de l'environnement de l'utilisateur ne doit pas primer sur ce que la coque a décidé.
    for name in ("LLM_API_KEY", "SECRETS_KEY", "DATABASE_URL"):
        os.environ.pop(f"{name}_FILE", None)


def watch_parent() -> None:
    """Quitte quand la coque disparaît : stdin est un tube dont elle détient l'autre bout."""
    def wait() -> None:
        try:
            while os.read(0, 4096):  # lecture non tamponnée : pas de verrou tenu à l'arrêt de l'interpréteur
                pass
        except OSError:  # stdin absent : on ne surveille pas
            return
        os._exit(0)

    threading.Thread(target=wait, daemon=True, name="parent-watch").start()


def serve(port: int, data_dir: Path) -> int:
    configure_environment(data_dir)
    watch_parent()
    import uvicorn

    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    return 0


def backup(data_dir: Path, dest: Path) -> int:
    """Archive .zip : copie cohérente de la base (API de sauvegarde de SQLite, sûre pendant que l'application tourne) + dossier media/."""
    db = sqlite_path(data_dir)
    if not db.is_file():
        print("Base introuvable : rien à sauvegarder.", file=sys.stderr)
        return 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "coach.db"
        src = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            out = sqlite3.connect(copy)
            try:
                src.backup(out)
            finally:
                out.close()
        finally:
            src.close()
        tmp_zip = dest.with_name(dest.name + ".part")
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copy, "coach.db")
            media = data_dir / "media"
            for f in sorted(media.rglob("*")) if media.is_dir() else []:
                if f.is_file() and not f.is_symlink():
                    z.write(f, "media/" + f.relative_to(media).as_posix())
        tmp_zip.replace(dest)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coach-sidecar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--data-dir", type=Path, required=True)
    b = sub.add_parser("backup")
    b.add_argument("--data-dir", type=Path, required=True)
    b.add_argument("--dest", type=Path, required=True)
    a = ap.parse_args(argv)
    return serve(a.port, a.data_dir) if a.cmd == "serve" else backup(a.data_dir, a.dest)


if __name__ == "__main__":
    sys.exit(main())
