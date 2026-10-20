"""Stockage Postgres : le noyau (connexion, migrations, utilisateurs, faits) et les domaines assemblés."""
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.questionnaire.models import Fact
from app.repo.accounts import AccountsPostgres
from app.repo.chat import ChatPostgres
from app.repo.coach import CoachPostgres
from app.repo.exercises import ExercisesPostgres
from app.repo.garmin import GarminPostgres
from app.repo.goals import GoalsPostgres
from app.repo.nutrition import NutritionPostgres
from app.repo.plan import PlanPostgres


class PostgresRepo(AccountsPostgres, ExercisesPostgres, GoalsPostgres, PlanPostgres, GarminPostgres, CoachPostgres, ChatPostgres, NutritionPostgres):
    name = "postgres"

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def _conn(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def migrate(self, directory: Path) -> None:
        with self._conn() as c:
            for path in sorted(directory.glob("*.sql")):
                c.execute(path.read_text(encoding="utf-8"))

    def create_user(self, name: str) -> int:
        with self._conn() as c:
            row = c.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
            return row["id"]

    def user_exists(self, user_id: int) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM users WHERE id = %s", (user_id,)).fetchone() is not None

    def add_facts(self, user_id: int, facts: list[Fact]) -> None:
        with self._conn() as c:
            for f in facts:
                prev = c.execute(
                    "SELECT id FROM facts WHERE user_id = %s AND key = %s "
                    "ORDER BY observed_at DESC, id DESC LIMIT 1",
                    (user_id, f.key),
                ).fetchone()
                c.execute(
                    "INSERT INTO facts (user_id, key, value, source, confidence, observed_at, "
                    "supersedes_id) VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)",
                    (user_id, f.key, json.dumps(f.value), f.source, f.confidence,
                     f.observed_at, prev["id"] if prev else None),
                )

    def list_facts(self, user_id: int) -> list[Fact]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT key, value, source, confidence, observed_at FROM facts "
                "WHERE user_id = %s ORDER BY observed_at, id",
                (user_id,),
            ).fetchall()
        return [Fact(**r) for r in rows]
