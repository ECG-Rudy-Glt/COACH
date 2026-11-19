"""Stockage des utilisateurs et des faits : version mémoire (dev/tests), Postgres et SQLite (application de bureau), découpé par domaine (voir docs/architecture.md)."""
import os
from datetime import UTC, datetime
from pathlib import Path

from app.repo.memory import MemoryRepo
from app.repo.postgres import PostgresRepo
from app.repo.protocol import Repo
from app.repo.sqlite import SqliteRepo, is_sqlite_url, sqlite_path

__all__ = ["MemoryRepo", "PostgresRepo", "Repo", "SqliteRepo", "open_repo", "utcnow"]

ROOT = Path(__file__).resolve().parent.parent.parent


def open_repo(dsn: str) -> Repo:
    """Stockage choisi par `DATABASE_URL` : `sqlite:///chemin` (fichier local), URL Postgres, ou vide = mémoire. Les migrations sont appliquées."""
    if not dsn:
        return MemoryRepo()
    if is_sqlite_url(dsn):
        repo = SqliteRepo(sqlite_path(dsn))
        repo.migrate(Path(os.environ.get("SQLITE_MIGRATIONS_DIR", ROOT / "db" / "sqlite")))
        return repo
    repo = PostgresRepo(dsn)
    repo.migrate(Path(os.environ.get("MIGRATIONS_DIR", ROOT / "db" / "migrations")))
    return repo


def utcnow() -> datetime:
    return datetime.now(UTC)
