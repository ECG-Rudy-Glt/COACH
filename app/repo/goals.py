"""Objectifs vivants : version mémoire et version Postgres du domaine (mêlées dans MemoryRepo / PostgresRepo par héritage)."""
import json
from datetime import UTC, date, datetime
from typing import Any


class GoalsMemory:
    def _goals(self) -> dict[int, dict[str, Any]]:
        if not hasattr(self, "_goal_rows"):
            self._goal_rows: dict[int, dict[str, Any]] = {}
        return self._goal_rows

    def list_goals(self, user_id: int, status: str | None) -> list[dict[str, Any]]:
        rows = [g for g in self._goals().values()
                if g["user_id"] == user_id and (status is None or g["status"] == status)]
        return sorted(rows, key=lambda g: (g["target_date"] is None, g["target_date"] or date.max, g["id"]))

    def create_goal(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        gid = len(self._goals()) + 1
        row = {"id": gid, "user_id": user_id, "status": "active", "created_at": datetime.now(UTC), **data}
        self._goals()[gid] = row
        return row

    def update_goal(self, user_id: int, goal_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        g = self._goals().get(goal_id)
        if not g or g["user_id"] != user_id:
            return None
        g.update({k: v for k, v in changes.items() if v is not None or k == "target_date"})
        return g

    def delete_goal(self, user_id: int, goal_id: int) -> bool:
        g = self._goals().get(goal_id)
        if not g or g["user_id"] != user_id:
            return False
        del self._goals()[goal_id]
        return True


class GoalsPostgres:
    def list_goals(self, user_id: int, status: str | None) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute(
                "SELECT * FROM goals WHERE user_id = %s AND (%s::text IS NULL OR status = %s) "
                "ORDER BY target_date NULLS LAST, id", (user_id, status, status)).fetchall()

    def create_goal(self, user_id: int, d: dict[str, Any]) -> dict[str, Any]:
        with self._conn() as c:
            return c.execute(
                "INSERT INTO goals (user_id, title, kind, target_date, priority, success, details) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb) RETURNING *",
                (user_id, d["title"], d["kind"], d["target_date"], d["priority"], d["success"],
                 json.dumps(d["details"]))).fetchone()

    def update_goal(self, user_id: int, goal_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        cols = {"title", "kind", "target_date", "priority", "success", "details", "status"}
        sets, args = ["updated_at = now()"], []
        for k, v in changes.items():
            if k not in cols or (v is None and k != "target_date"):
                continue
            sets.append(f"{k} = %s::jsonb" if k == "details" else f"{k} = %s")
            args.append(json.dumps(v) if k == "details" else v)
        if changes.get("status") in ("done", "dropped"):
            sets.append("closed_at = now()")
        elif changes.get("status") == "active":
            sets.append("closed_at = NULL")
        with self._conn() as c:
            return c.execute(f"UPDATE goals SET {', '.join(sets)} WHERE id = %s AND user_id = %s RETURNING *",
                             [*args, goal_id, user_id]).fetchone()

    def delete_goal(self, user_id: int, goal_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM goals WHERE id = %s AND user_id = %s", (goal_id, user_id)).rowcount == 1
