"""Séances planifiées et réalisées : version mémoire et version Postgres du domaine (mêlées dans MemoryRepo / PostgresRepo par héritage)."""
import json
from datetime import date
from typing import Any


class PlanMemory:
    def _sess(self) -> dict[int, dict[str, Any]]:
        if not hasattr(self, "_session_rows"):
            self._session_rows: dict[int, dict[str, Any]] = {}
        return self._session_rows

    def add_sessions(self, user_id: int, rows: list[dict[str, Any]]) -> None:
        for r in rows:
            sid = max(self._sess(), default=0) + 1
            self._sess()[sid] = {"id": sid, "user_id": user_id, "status": "planned", "logged": None, **r}

    def list_sessions(self, user_id: int, start: date, end: date | None) -> list[dict[str, Any]]:
        rows = [r for r in self._sess().values() if r["user_id"] == user_id and r["day"] >= start and (end is None or r["day"] < end)]
        return sorted(rows, key=lambda r: (r["day"], r["id"]))

    def delete_planned_from(self, user_id: int, day: date) -> None:
        for sid in [i for i, r in self._sess().items() if r["user_id"] == user_id and r["status"] == "planned" and r["day"] >= day]:
            del self._sess()[sid]

    def update_session(self, user_id: int, session_id: int, status: str, logged: dict[str, Any] | None) -> dict[str, Any] | None:
        r = self._sess().get(session_id)
        if not r or r["user_id"] != user_id:
            return None
        r["status"] = status
        if logged is not None:
            r["logged"] = logged
        return r


class PlanPostgres:
    def add_sessions(self, user_id: int, rows: list[dict[str, Any]]) -> None:
        with self._conn() as c:
            for r in rows:
                c.execute("INSERT INTO planned_sessions (user_id, day, kind, title, duration_min, details, rules, notes) "
                          "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
                          (user_id, r["day"], r["kind"], r["title"], r["duration_min"], json.dumps(r["details"]), r["rules"], r["notes"]))

    def list_sessions(self, user_id: int, start: date, end: date | None) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute("SELECT * FROM planned_sessions WHERE user_id = %s AND day >= %s AND (%s::date IS NULL OR day < %s) "
                             "ORDER BY day, id", (user_id, start, end, end)).fetchall()

    def delete_planned_from(self, user_id: int, day: date) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM planned_sessions WHERE user_id = %s AND status = 'planned' AND day >= %s", (user_id, day))

    def update_session(self, user_id: int, session_id: int, status: str, logged: dict[str, Any] | None) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute("UPDATE planned_sessions SET status = %s, logged = COALESCE(%s::jsonb, logged), updated_at = now() "
                             "WHERE id = %s AND user_id = %s RETURNING *",
                             (status, json.dumps(logged) if logged is not None else None, session_id, user_id)).fetchone()
