"""Mesures de la montre, mémoire et appels du coach IA : version mémoire et version Postgres du domaine (mêlées dans MemoryRepo / PostgresRepo par héritage)."""
import json
from datetime import UTC, date, datetime
from typing import Any


class CoachMemory:
    def list_garmin_users(self) -> list[int]:
        return list(self._g()[0])

    def mark_backfilled(self, user_id: int) -> None:
        self._g()[0][user_id]["backfilled_at"] = datetime.now(UTC)

    def prune_activities(self, user_id: int, before: date) -> None:
        for k in [k for k, a in self._g()[1].items() if k[0] == user_id and a["day"] < before]:
            del self._g()[1][k]
            self._streams().pop(k, None)
        for k in [k for k in self._metrics() if k[0] == user_id and k[2] < before]:
            del self._metrics()[k]

    def _metrics(self) -> dict[tuple[int, str, date], dict[str, Any]]:
        if not hasattr(self, "_gm"):
            self._gm: dict[tuple[int, str, date], dict[str, Any]] = {}
        return self._gm

    def upsert_metrics(self, user_id: int, rows: list[dict[str, Any]]) -> int:
        for r in rows:
            self._metrics()[(user_id, r["metric"], r["day"])] = {"user_id": user_id, "day": r["day"], "metric": r["metric"],
                                                                 "value": r.get("value"), "text": r.get("text")}
        return len(rows)

    def list_metrics(self, user_id: int, metric: str | None, since: date, until: date | None = None) -> list[dict[str, Any]]:
        rows = [m for m in self._metrics().values() if m["user_id"] == user_id and (metric is None or m["metric"] == metric)
                and m["day"] >= since and (until is None or m["day"] <= until)]
        return sorted(rows, key=lambda m: (m["metric"], m["day"]))

    def patch_planned(self, user_id: int, session_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        r = self._sess().get(session_id)
        if not r or r["user_id"] != user_id or r["status"] != "planned":
            return None
        r.update({k: v for k, v in changes.items() if k in ("duration_min", "day", "kind", "title", "details", "notes")})
        return r

    def _coach(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not hasattr(self, "_mem"):
            self._mem: list[dict[str, Any]] = []
            self._llm: list[dict[str, Any]] = []
        return self._mem, self._llm

    def add_memory(self, user_id: int, kind: str, period: tuple[date | None, date | None], body: str, data: dict[str, Any]) -> dict[str, Any]:
        row = {"id": len(self._coach()[0]) + 1, "user_id": user_id, "kind": kind, "period_start": period[0], "period_end": period[1],
               "body": body, "data": data, "created_at": datetime.now(UTC)}
        self._coach()[0].append(row)
        return row

    def list_memory(self, user_id: int, kind: str | None, limit: int) -> list[dict[str, Any]]:
        rows = [m for m in self._coach()[0] if m["user_id"] == user_id and (kind is None or m["kind"] == kind)]
        return sorted(rows, key=lambda m: m["id"], reverse=True)[:limit]

    def get_memory(self, user_id: int, memory_id: int) -> dict[str, Any] | None:
        return next((m for m in self._coach()[0] if m["id"] == memory_id and m["user_id"] == user_id), None)

    def update_memory_data(self, user_id: int, memory_id: int, data: dict[str, Any]) -> None:
        m = self.get_memory(user_id, memory_id)
        if m:
            m["data"] = data

    def log_llm_call(self, user_id: int | None, kind: str, model: str, tokens: tuple[int, int], cost: float, ok: bool, error: str | None) -> None:
        self._coach()[1].append({"user_id": user_id, "kind": kind, "model": model, "in": tokens[0], "out": tokens[1], "cost": cost,
                                 "ok": ok, "error": error, "created_at": datetime.now(UTC)})

    def llm_spend_month(self, month_start: date) -> float:
        return sum(c["cost"] for c in self._coach()[1] if c["created_at"].date() >= month_start)

    def llm_calls_since(self, user_id: int, kind: str, since: datetime) -> int:
        return sum(1 for c in self._coach()[1] if c["user_id"] == user_id and c["kind"] == kind and c["created_at"] >= since)

    def llm_usage_since(self, since: datetime, user_id: int) -> list[dict[str, Any]]:
        """Appels réussis depuis `since`, agrégés par (usage, modèle, appel du compte demandé ou non) : aucune identité d'autrui."""
        agg: dict[tuple[str, str, bool], list[float]] = {}
        for c in self._coach()[1]:
            if c["ok"] and c["created_at"] >= since:
                a = agg.setdefault((c["kind"], c["model"], c["user_id"] == user_id), [0, 0.0])
                a[0] += 1
                a[1] += c["cost"]
        return [{"kind": k, "model": m, "mine": mine, "calls": int(a[0]), "cost": a[1]} for (k, m, mine), a in agg.items()]


class CoachPostgres:
    def mark_backfilled(self, user_id: int) -> None:
        with self._conn() as c:
            c.execute("UPDATE garmin_accounts SET backfilled_at = now() WHERE user_id = %s", (user_id,))

    def prune_activities(self, user_id: int, before: date) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM garmin_activities WHERE user_id = %s AND day < %s", (user_id, before))
            c.execute("DELETE FROM garmin_metrics WHERE user_id = %s AND day < %s", (user_id, before))

    def upsert_metrics(self, user_id: int, rows: list[dict[str, Any]]) -> int:
        with self._conn() as c:
            for r in rows:
                c.execute("INSERT INTO garmin_metrics (user_id, day, metric, value, text) VALUES (%s, %s, %s, %s, %s) "
                          "ON CONFLICT (user_id, metric, day) DO UPDATE SET value = EXCLUDED.value, text = EXCLUDED.text",
                          (user_id, r["day"], r["metric"], r.get("value"), r.get("text")))
        return len(rows)

    def list_metrics(self, user_id: int, metric: str | None, since: date, until: date | None = None) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute("SELECT * FROM garmin_metrics WHERE user_id = %s AND (%s::text IS NULL OR metric = %s) AND day >= %s "
                             "AND (%s::date IS NULL OR day <= %s) ORDER BY metric, day", (user_id, metric, metric, since, until, until)).fetchall()

    def list_garmin_users(self) -> list[int]:
        with self._conn() as c:
            return [r["user_id"] for r in c.execute("SELECT user_id FROM garmin_accounts").fetchall()]

    def patch_planned(self, user_id: int, session_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        cols = {"duration_min", "day", "kind", "title", "details", "notes"}
        sets, args = ["updated_at = now()"], []
        for k, v in changes.items():
            if k in cols:
                sets.append(f"{k} = %s::jsonb" if k == "details" else f"{k} = %s")
                args.append(json.dumps(v) if k == "details" else v)
        with self._conn() as c:
            return c.execute(f"UPDATE planned_sessions SET {', '.join(sets)} WHERE id = %s AND user_id = %s AND status = 'planned' RETURNING *",
                             [*args, session_id, user_id]).fetchone()

    def add_memory(self, user_id: int, kind: str, period: tuple[date | None, date | None], body: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._conn() as c:
            return c.execute("INSERT INTO coach_memory (user_id, kind, period_start, period_end, body, data) "
                             "VALUES (%s, %s, %s, %s, %s, %s::jsonb) RETURNING *",
                             (user_id, kind, period[0], period[1], body, json.dumps(data))).fetchone()

    def list_memory(self, user_id: int, kind: str | None, limit: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute("SELECT * FROM coach_memory WHERE user_id = %s AND (%s::text IS NULL OR kind = %s) "
                             "ORDER BY id DESC LIMIT %s", (user_id, kind, kind, limit)).fetchall()

    def get_memory(self, user_id: int, memory_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute("SELECT * FROM coach_memory WHERE id = %s AND user_id = %s", (memory_id, user_id)).fetchone()

    def update_memory_data(self, user_id: int, memory_id: int, data: dict[str, Any]) -> None:
        with self._conn() as c:
            c.execute("UPDATE coach_memory SET data = %s::jsonb WHERE id = %s AND user_id = %s", (json.dumps(data), memory_id, user_id))

    def log_llm_call(self, user_id: int | None, kind: str, model: str, tokens: tuple[int, int], cost: float, ok: bool, error: str | None) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO llm_calls (user_id, kind, model, input_tokens, output_tokens, cost_eur, ok, error) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (user_id, kind, model, tokens[0], tokens[1], cost, ok, error))

    def llm_spend_month(self, month_start: date) -> float:
        with self._conn() as c:
            return float(c.execute("SELECT COALESCE(SUM(cost_eur), 0) AS s FROM llm_calls WHERE created_at >= %s", (month_start,)).fetchone()["s"])

    def llm_calls_since(self, user_id: int, kind: str, since: datetime) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) AS n FROM llm_calls WHERE user_id = %s AND kind = %s AND created_at >= %s",
                             (user_id, kind, since)).fetchone()["n"]

    def llm_usage_since(self, since: datetime, user_id: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT kind, model, (user_id IS NOT DISTINCT FROM %s) AS mine, count(*) AS calls, COALESCE(SUM(cost_eur), 0) AS cost "
                             "FROM llm_calls WHERE ok AND created_at >= %s GROUP BY kind, model, mine", (user_id, since)).fetchall()
        return [{"kind": r["kind"], "model": r["model"], "mine": bool(r["mine"]), "calls": int(r["calls"]), "cost": float(r["cost"])} for r in rows]
