"""Stockage des utilisateurs et des faits : version mémoire (dev/tests) et Postgres, découpé par domaine (voir docs/architecture.md)."""
from datetime import UTC, datetime

from app.repo.memory import MemoryRepo
from app.repo.postgres import PostgresRepo
from app.repo.protocol import Repo

__all__ = ["MemoryRepo", "PostgresRepo", "Repo", "utcnow"]


def utcnow() -> datetime:
    return datetime.now(UTC)
