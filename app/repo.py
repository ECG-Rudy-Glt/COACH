"""Stockage des utilisateurs et des faits : version mémoire (dev/tests) et Postgres."""
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

from app.exercises.models import Exercise, Media
from app.questionnaire.models import Fact


class Repo(Protocol):
    name: str

    def create_user(self, name: str) -> int: ...
    def user_exists(self, user_id: int) -> bool: ...
    def add_facts(self, user_id: int, facts: list[Fact]) -> None: ...
    def list_facts(self, user_id: int) -> list[Fact]: ...
    def create_account(self, name: str, email: str, password_hash: str) -> int: ...
    def get_account(self, email: str) -> dict[str, Any] | None: ...
    def list_legacy_users(self) -> list[dict[str, Any]]: ...
    def has_accounts(self) -> bool: ...
    def adopt_legacy_user(self, user_id: int, name: str, email: str, password_hash: str) -> bool: ...
    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> None: ...
    def get_session_user(self, token_hash: str) -> dict[str, Any] | None: ...
    def delete_session(self, token_hash: str) -> None: ...
    def set_password(self, user_id: int, password_hash: str, keep_session: str | None) -> None: ...
    def replace_exercises(self, exercises: list[Exercise]) -> int: ...
    def search_exercises(self, q: str | None, muscle: str | None, equipment: str | None, kind: str | None,
                         limit: int, offset: int) -> tuple[list[Exercise], int]: ...
    def get_exercise(self, exercise_id: int) -> Exercise | None: ...
    def get_media(self, media_id: int) -> Media | None: ...
    def add_meal(self, user_id: int, day: date, slot: str, description: str, photo_path: str | None) -> dict[str, Any]: ...
    def list_meals(self, user_id: int, start: date, end: date) -> list[dict[str, Any]]: ...
    def get_meal(self, user_id: int, meal_id: int) -> dict[str, Any] | None: ...
    def set_meal_analysis(self, user_id: int, meal_id: int, analysis: dict[str, Any]) -> None: ...
    def delete_meal(self, user_id: int, meal_id: int) -> str | None: ...
    def upsert_weight(self, user_id: int, day: date, kg: float, waist_cm: float | None) -> None: ...
    def list_weights(self, user_id: int, since: date) -> list[dict[str, Any]]: ...
    def list_goals(self, user_id: int, status: str | None) -> list[dict[str, Any]]: ...
    def create_goal(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]: ...
    def update_goal(self, user_id: int, goal_id: int, changes: dict[str, Any]) -> dict[str, Any] | None: ...
    def delete_goal(self, user_id: int, goal_id: int) -> bool: ...
    def add_sessions(self, user_id: int, rows: list[dict[str, Any]]) -> None: ...
    def list_sessions(self, user_id: int, start: date, end: date | None) -> list[dict[str, Any]]: ...
    def delete_planned_from(self, user_id: int, day: date) -> None: ...
    def update_session(self, user_id: int, session_id: int, status: str, logged: dict[str, Any] | None) -> dict[str, Any] | None: ...
    def get_garmin(self, user_id: int) -> dict[str, Any] | None: ...
    def save_garmin(self, user_id: int, email: str, tokens_enc: str) -> None: ...
    def touch_garmin(self, user_id: int, tokens_enc: str | None, error: str | None) -> None: ...
    def delete_garmin(self, user_id: int, purge: bool) -> None: ...
    def upsert_activities(self, user_id: int, rows: list[dict[str, Any]]) -> int: ...
    def list_activities(self, user_id: int, since: date, limit: int) -> list[dict[str, Any]]: ...
    def list_garmin_users(self) -> list[int]: ...
    def mark_backfilled(self, user_id: int) -> None: ...
    def prune_activities(self, user_id: int, before: date) -> None: ...
    def upsert_metrics(self, user_id: int, rows: list[dict[str, Any]]) -> int: ...
    def list_metrics(self, user_id: int, metric: str | None, since: date, until: date | None = None) -> list[dict[str, Any]]: ...
    def patch_planned(self, user_id: int, session_id: int, changes: dict[str, Any]) -> dict[str, Any] | None: ...
    def add_memory(self, user_id: int, kind: str, period: tuple[date | None, date | None], body: str, data: dict[str, Any]) -> dict[str, Any]: ...
    def list_memory(self, user_id: int, kind: str | None, limit: int) -> list[dict[str, Any]]: ...
    def get_memory(self, user_id: int, memory_id: int) -> dict[str, Any] | None: ...
    def update_memory_data(self, user_id: int, memory_id: int, data: dict[str, Any]) -> None: ...
    def log_llm_call(self, user_id: int | None, kind: str, model: str, tokens: tuple[int, int], cost: float, ok: bool, error: str | None) -> None: ...
    def llm_spend_month(self, month_start: date) -> float: ...
    def llm_calls_since(self, user_id: int, kind: str, since: datetime) -> int: ...
    def add_message(self, user_id: int, role: str, body: str, meta: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def list_messages(self, user_id: int, limit: int) -> list[dict[str, Any]]: ...
    def get_prefs(self, user_id: int) -> dict[str, Any]: ...
    def set_prefs(self, user_id: int, prefs: dict[str, Any]) -> dict[str, Any]: ...
    def list_notify_users(self) -> list[int]: ...
    def add_notify_log(self, user_id: int, kind: str, channel: str, title: str, body: str, ok: bool, error: str | None) -> None: ...
    def last_notify(self, user_id: int, kind: str | None = None, ok_only: bool = True) -> datetime | None: ...
    def add_subscription(self, user_id: int, endpoint: str, p256dh: str, auth: str) -> None: ...
    def list_subscriptions(self, user_id: int) -> list[dict[str, Any]]: ...
    def delete_subscription(self, user_id: int, endpoint: str) -> None: ...


class MemoryRepo:
    name = "memory"

    def __init__(self) -> None:
        self._users: dict[int, str] = {}
        self._facts: dict[int, list[Fact]] = {}

    def create_user(self, name: str) -> int:
        uid = len(self._users) + 1
        self._users[uid] = name
        self._facts[uid] = []
        return uid

    def user_exists(self, user_id: int) -> bool:
        return user_id in self._users

    def add_facts(self, user_id: int, facts: list[Fact]) -> None:
        self._facts[user_id].extend(facts)

    def list_facts(self, user_id: int) -> list[Fact]:
        return list(self._facts[user_id])

    # --- comptes ---
    def _acct(self) -> dict[int, dict[str, Any]]:
        if not hasattr(self, "_accounts"):
            self._accounts: dict[int, dict[str, Any]] = {}
            self._sessions: dict[str, tuple[int, datetime]] = {}
        return self._accounts

    def create_account(self, name: str, email: str, password_hash: str) -> int:
        uid = self.create_user(name)
        self._acct()[uid] = {"email": email, "password_hash": password_hash}
        return uid

    def get_account(self, email: str) -> dict[str, Any] | None:
        for uid, a in self._acct().items():
            if a["email"] == email:
                return {"id": uid, "name": self._users[uid], "password_hash": a["password_hash"]}
        return None

    def has_accounts(self) -> bool:
        return bool(self._acct())

    def list_legacy_users(self) -> list[dict[str, Any]]:
        return [{"id": u, "name": n, "answers": len(self._facts[u])}
                for u, n in self._users.items() if u not in self._acct()]

    def adopt_legacy_user(self, user_id: int, name: str, email: str, password_hash: str) -> bool:
        if user_id not in self._users or user_id in self._acct():
            return False
        self._users[user_id] = name
        self._acct()[user_id] = {"email": email, "password_hash": password_hash}
        return True

    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self._acct()
        self._sessions[token_hash] = (user_id, expires_at)

    def get_session_user(self, token_hash: str) -> dict[str, Any] | None:
        self._acct()
        row = self._sessions.get(token_hash)
        if not row or row[1] < datetime.now(UTC):
            return None
        uid = row[0]
        return {"id": uid, "name": self._users[uid], "email": self._accounts[uid]["email"]}

    def delete_session(self, token_hash: str) -> None:
        self._acct()
        self._sessions.pop(token_hash, None)

    def set_password(self, user_id: int, password_hash: str, keep_session: str | None) -> None:
        self._acct()[user_id]["password_hash"] = password_hash
        self._sessions = {t: v for t, v in self._sessions.items() if v[0] != user_id or t == keep_session}

    # --- exercices ---
    def replace_exercises(self, exercises: list[Exercise]) -> int:
        self._ex: list[Exercise] = []
        self._media: dict[int, Media] = {}
        for i, e in enumerate(exercises, 1):
            e = e.model_copy(deep=True)
            e.id = i
            for m in e.media:
                m.id = len(self._media) + 1
                self._media[m.id] = m
            self._ex.append(e)
        return len(self._ex)

    def search_exercises(self, q, muscle, equipment, kind, limit, offset):
        rows = [e for e in getattr(self, "_ex", []) if _matches(e, q, muscle, equipment, kind)]
        rows.sort(key=lambda e: (not any(m.kind == "image" for m in e.media), e.name.lower()))
        return rows[offset: offset + limit], len(rows)

    def get_exercise(self, exercise_id: int) -> Exercise | None:
        return next((e for e in getattr(self, "_ex", []) if e.id == exercise_id), None)

    def get_media(self, media_id: int) -> Media | None:
        return getattr(self, "_media", {}).get(media_id)

    # --- objectifs ---
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

    # --- plan ---
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

    # --- garmin ---
    def _g(self) -> tuple[dict[int, dict[str, Any]], dict[tuple[int, str], dict[str, Any]]]:
        if not hasattr(self, "_garmin"):
            self._garmin: dict[int, dict[str, Any]] = {}
            self._acts: dict[tuple[int, str], dict[str, Any]] = {}
        return self._garmin, self._acts

    def get_garmin(self, user_id: int) -> dict[str, Any] | None:
        return self._g()[0].get(user_id)

    def save_garmin(self, user_id: int, email: str, tokens_enc: str) -> None:
        self._g()[0][user_id] = {"user_id": user_id, "email": email, "tokens_enc": tokens_enc, "last_sync_at": None, "last_error": None,
                                  "backfilled_at": None}

    def touch_garmin(self, user_id: int, tokens_enc: str | None, error: str | None) -> None:
        acct = self._g()[0][user_id]
        if tokens_enc:
            acct["tokens_enc"] = tokens_enc
        if error is None:
            acct["last_sync_at"] = datetime.now(UTC)
        acct["last_error"] = error

    def delete_garmin(self, user_id: int, purge: bool) -> None:
        self._g()[0].pop(user_id, None)
        if purge:
            for k in [k for k in self._g()[1] if k[0] == user_id]:
                del self._g()[1][k]
            for k in [k for k in self._metrics() if k[0] == user_id]:
                del self._metrics()[k]

    def upsert_activities(self, user_id: int, rows: list[dict[str, Any]]) -> int:
        new = 0
        for r in rows:
            key = (user_id, r["garmin_id"])
            new += key not in self._g()[1]
            self._g()[1][key] = {"user_id": user_id, **r}
        return new

    def list_activities(self, user_id: int, since: date, limit: int) -> list[dict[str, Any]]:
        rows = [a for (u, _), a in self._g()[1].items() if u == user_id and a["day"] >= since]
        return sorted(rows, key=lambda a: a["started_at"], reverse=True)[:limit]

    # --- coach ---
    def list_garmin_users(self) -> list[int]:
        return list(self._g()[0])

    def mark_backfilled(self, user_id: int) -> None:
        self._g()[0][user_id]["backfilled_at"] = datetime.now(UTC)

    def prune_activities(self, user_id: int, before: date) -> None:
        for k in [k for k, a in self._g()[1].items() if k[0] == user_id and a["day"] < before]:
            del self._g()[1][k]
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

    # --- discussion et notifications ---
    def _chat(self) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], list[dict[str, Any]]]:
        if not hasattr(self, "_msgs"):
            self._msgs: list[dict[str, Any]] = []
            self._prefs: dict[int, dict[str, Any]] = {}
            self._nlog: list[dict[str, Any]] = []
        return self._msgs, self._prefs, self._nlog

    def add_message(self, user_id: int, role: str, body: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        row = {"id": len(self._chat()[0]) + 1, "user_id": user_id, "role": role, "body": body, "meta": meta or {}, "created_at": datetime.now(UTC)}
        self._chat()[0].append(row)
        return row

    def list_messages(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        return [m for m in self._chat()[0] if m["user_id"] == user_id][-limit:]

    def get_prefs(self, user_id: int) -> dict[str, Any]:
        return self._chat()[1].get(user_id) or {"user_id": user_id, "ntfy_topic": None, "email": None, "push_enabled": False, "email_enabled": False}

    def set_prefs(self, user_id: int, prefs: dict[str, Any]) -> dict[str, Any]:
        self._chat()[1][user_id] = {**self.get_prefs(user_id), **prefs, "user_id": user_id}
        return self._chat()[1][user_id]

    def list_notify_users(self) -> list[int]:
        return [u for u, p in self._chat()[1].items() if p["push_enabled"] or p["email_enabled"]]

    def add_notify_log(self, user_id: int, kind: str, channel: str, title: str, body: str, ok: bool, error: str | None) -> None:
        self._chat()[2].append({"user_id": user_id, "kind": kind, "channel": channel, "title": title, "body": body, "ok": ok, "error": error,
                                "created_at": datetime.now(UTC)})

    def last_notify(self, user_id: int, kind: str | None = None, ok_only: bool = True) -> datetime | None:
        rows = [n["created_at"] for n in self._chat()[2] if n["user_id"] == user_id and (kind is None or n["kind"] == kind) and (n["ok"] or not ok_only)]
        return max(rows) if rows else None

    def _subs(self) -> dict[str, dict[str, Any]]:
        if not hasattr(self, "_push"):
            self._push: dict[str, dict[str, Any]] = {}
        return self._push

    def add_subscription(self, user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
        self._subs()[endpoint] = {"user_id": user_id, "endpoint": endpoint, "p256dh": p256dh, "auth": auth}

    def list_subscriptions(self, user_id: int) -> list[dict[str, Any]]:
        return [s for s in self._subs().values() if s["user_id"] == user_id]

    def delete_subscription(self, user_id: int, endpoint: str) -> None:
        if self._subs().get(endpoint, {}).get("user_id") == user_id:
            del self._subs()[endpoint]

    # --- nutrition ---
    def _nut(self) -> tuple[dict[int, dict[str, Any]], dict[tuple[int, date], dict[str, Any]]]:
        if not hasattr(self, "_meals"):
            self._meals: dict[int, dict[str, Any]] = {}
            self._weights: dict[tuple[int, date], dict[str, Any]] = {}
        return self._meals, self._weights

    def add_meal(self, user_id: int, day: date, slot: str, description: str, photo_path: str | None) -> dict[str, Any]:
        mid = max(self._nut()[0], default=0) + 1
        row = {"id": mid, "user_id": user_id, "day": day, "slot": slot, "description": description, "photo_path": photo_path, "analysis": None,
               "created_at": datetime.now(UTC)}
        self._nut()[0][mid] = row
        return row

    def list_meals(self, user_id: int, start: date, end: date) -> list[dict[str, Any]]:
        rows = [m for m in self._nut()[0].values() if m["user_id"] == user_id and start <= m["day"] <= end]
        return sorted(rows, key=lambda m: (m["day"], m["id"]))

    def get_meal(self, user_id: int, meal_id: int) -> dict[str, Any] | None:
        m = self._nut()[0].get(meal_id)
        return m if m and m["user_id"] == user_id else None

    def set_meal_analysis(self, user_id: int, meal_id: int, analysis: dict[str, Any]) -> None:
        m = self.get_meal(user_id, meal_id)
        if m:
            m["analysis"] = analysis

    def delete_meal(self, user_id: int, meal_id: int) -> str | None:
        m = self.get_meal(user_id, meal_id)
        if not m:
            return None
        del self._nut()[0][meal_id]
        return m["photo_path"] or ""

    def upsert_weight(self, user_id: int, day: date, kg: float, waist_cm: float | None) -> None:
        self._nut()[1][(user_id, day)] = {"user_id": user_id, "day": day, "kg": kg, "waist_cm": waist_cm}

    def list_weights(self, user_id: int, since: date) -> list[dict[str, Any]]:
        return sorted((w for (u, d), w in self._nut()[1].items() if u == user_id and d >= since), key=lambda w: w["day"])


def _matches(e: Exercise, q: str | None, muscle: str | None, equipment: str | None, kind: str | None) -> bool:
    if q and q.lower() not in e.name.lower() and q.lower() not in (e.name_en or "").lower():
        return False
    if muscle and muscle not in e.muscles_primary + e.muscles_secondary:
        return False
    if equipment and equipment not in e.equipment:
        return False
    return not kind or e.kind == kind


class PostgresRepo:
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

    # --- comptes ---
    def create_account(self, name: str, email: str, password_hash: str) -> int:
        with self._conn() as c:
            row = c.execute("INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                            (name, email, password_hash)).fetchone()
            return row["id"]

    def get_account(self, email: str) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute("SELECT id, name, password_hash FROM users WHERE email = %s", (email,)).fetchone()

    def has_accounts(self) -> bool:
        with self._conn() as c:
            return bool(c.execute("SELECT EXISTS (SELECT 1 FROM users WHERE email IS NOT NULL) AS x").fetchone()["x"])

    def list_legacy_users(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute(
                "SELECT u.id, u.name, (SELECT count(*) FROM facts f WHERE f.user_id = u.id) AS answers "
                "FROM users u WHERE u.email IS NULL ORDER BY u.id").fetchall()

    def adopt_legacy_user(self, user_id: int, name: str, email: str, password_hash: str) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE users SET name = %s, email = %s, password_hash = %s "
                            "WHERE id = %s AND email IS NULL", (name, email, password_hash, user_id))
            return cur.rowcount == 1

    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < now()")
            c.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                      (token_hash, user_id, expires_at))

    def get_session_user(self, token_hash: str) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute(
                "SELECT u.id, u.name, u.email FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > now()", (token_hash,)).fetchone()

    def delete_session(self, token_hash: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    def set_password(self, user_id: int, password_hash: str, keep_session: str | None) -> None:
        """Change le mot de passe et ferme les autres sessions de l'utilisateur."""
        with self._conn() as c:
            c.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
            c.execute("DELETE FROM sessions WHERE user_id = %s AND token_hash IS DISTINCT FROM %s",
                      (user_id, keep_session))

    # --- exercices ---
    def replace_exercises(self, exercises: list[Exercise]) -> int:
        """Upsert par (source, source_id) ; les médias d'un exercice sont remplacés."""
        with self._conn() as c:
            for e in exercises:
                row = c.execute(
                    "INSERT INTO exercises (source, source_id, sources, name, name_en, kind, region, "
                    "muscles_primary, muscles_secondary, equipment, level, instructions, instructions_lang, "
                    "license, license_url, author) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (source, source_id) DO UPDATE SET sources=EXCLUDED.sources, name=EXCLUDED.name, "
                    "name_en=EXCLUDED.name_en, kind=EXCLUDED.kind, region=EXCLUDED.region, "
                    "muscles_primary=EXCLUDED.muscles_primary, muscles_secondary=EXCLUDED.muscles_secondary, "
                    "equipment=EXCLUDED.equipment, level=EXCLUDED.level, instructions=EXCLUDED.instructions, "
                    "instructions_lang=EXCLUDED.instructions_lang, license=EXCLUDED.license, "
                    "license_url=EXCLUDED.license_url, author=EXCLUDED.author RETURNING id",
                    (e.source, e.source_id, e.sources, e.name, e.name_en, e.kind, e.region, e.muscles_primary,
                     e.muscles_secondary, e.equipment, e.level, e.instructions, e.instructions_lang, e.license,
                     e.license_url, e.author)).fetchone()
                c.execute("DELETE FROM exercise_media WHERE exercise_id = %s", (row["id"],))
                for m in e.media:
                    c.execute("INSERT INTO exercise_media (exercise_id, kind, url, thumb_url, is_main, license, "
                              "license_url, author) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                              (row["id"], m.kind, m.url, m.thumb_url, m.is_main, m.license, m.license_url, m.author))
        return len(exercises)

    def _load(self, c: psycopg.Connection, rows: list[dict[str, Any]]) -> list[Exercise]:
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        media: dict[int, list[Media]] = {i: [] for i in ids}
        for m in c.execute("SELECT * FROM exercise_media WHERE exercise_id = ANY(%s) "
                           "ORDER BY is_main DESC, id", (ids,)).fetchall():
            media[m.pop("exercise_id")].append(Media(**m))
        return [Exercise(**r, media=media[r["id"]]) for r in rows]

    def search_exercises(self, q, muscle, equipment, kind, limit, offset):
        where, args = ["TRUE"], []
        if q:
            where.append("(name ILIKE %s OR name_en ILIKE %s)")
            args += [f"%{q}%", f"%{q}%"]
        if muscle:
            where.append("(%s = ANY(muscles_primary) OR %s = ANY(muscles_secondary))")
            args += [muscle, muscle]
        if equipment:
            where.append("%s = ANY(equipment)")
            args.append(equipment)
        if kind:
            where.append("kind = %s")
            args.append(kind)
        cond = " AND ".join(where)
        with self._conn() as c:
            total = c.execute(f"SELECT count(*) AS n FROM exercises WHERE {cond}", args).fetchone()["n"]
            rows = c.execute(
                f"SELECT * FROM exercises WHERE {cond} ORDER BY "
                "(NOT EXISTS (SELECT 1 FROM exercise_media m WHERE m.exercise_id = exercises.id "
                "AND m.kind = 'image')), lower(name) LIMIT %s OFFSET %s", [*args, limit, offset]).fetchall()
            return self._load(c, rows), total

    def get_exercise(self, exercise_id: int) -> Exercise | None:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM exercises WHERE id = %s", (exercise_id,)).fetchall()
            found = self._load(c, rows)
            return found[0] if found else None

    def get_media(self, media_id: int) -> Media | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM exercise_media WHERE id = %s", (media_id,)).fetchone()
            if not row:
                return None
            row.pop("exercise_id")
            return Media(**row)

    # --- objectifs ---
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

    # --- plan ---
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

    # --- garmin ---
    def get_garmin(self, user_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute("SELECT * FROM garmin_accounts WHERE user_id = %s", (user_id,)).fetchone()

    def save_garmin(self, user_id: int, email: str, tokens_enc: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO garmin_accounts (user_id, email, tokens_enc) VALUES (%s, %s, %s) "
                      "ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email, tokens_enc = EXCLUDED.tokens_enc, "
                      "connected_at = now(), last_sync_at = NULL, last_error = NULL, backfilled_at = NULL", (user_id, email, tokens_enc))

    def touch_garmin(self, user_id: int, tokens_enc: str | None, error: str | None) -> None:
        with self._conn() as c:
            c.execute("UPDATE garmin_accounts SET tokens_enc = COALESCE(%s, tokens_enc), last_error = %s, "
                      "last_sync_at = CASE WHEN %s::text IS NULL THEN now() ELSE last_sync_at END WHERE user_id = %s",
                      (tokens_enc, error, error, user_id))

    def delete_garmin(self, user_id: int, purge: bool) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM garmin_accounts WHERE user_id = %s", (user_id,))
            if purge:
                c.execute("DELETE FROM garmin_activities WHERE user_id = %s", (user_id,))
                c.execute("DELETE FROM garmin_metrics WHERE user_id = %s", (user_id,))

    def upsert_activities(self, user_id: int, rows: list[dict[str, Any]]) -> int:
        new = 0
        with self._conn() as c:
            for r in rows:
                cur = c.execute(
                    "INSERT INTO garmin_activities (user_id, garmin_id, day, started_at, sport, type_key, name, duration_s, "
                    "distance_m, elevation_m, avg_hr, max_hr, calories, training_load) VALUES (%(u)s, %(garmin_id)s, "
                    "%(day)s, %(started_at)s, %(sport)s, "
                    "%(type_key)s, %(name)s, %(duration_s)s, %(distance_m)s, %(elevation_m)s, %(avg_hr)s, %(max_hr)s, %(calories)s, "
                    "%(training_load)s) ON CONFLICT (user_id, garmin_id) DO UPDATE SET day = EXCLUDED.day, "
                    "sport = EXCLUDED.sport, "
                    "name = EXCLUDED.name, duration_s = EXCLUDED.duration_s, distance_m = EXCLUDED.distance_m, "
                    "elevation_m = EXCLUDED.elevation_m, avg_hr = EXCLUDED.avg_hr, max_hr = EXCLUDED.max_hr, "
                    "calories = EXCLUDED.calories, training_load = EXCLUDED.training_load RETURNING (xmax = 0) AS inserted",
                    {**r, "u": user_id}).fetchone()
                new += bool(cur["inserted"])
        return new

    def list_activities(self, user_id: int, since: date, limit: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute("SELECT * FROM garmin_activities WHERE user_id = %s AND day >= %s ORDER BY started_at DESC LIMIT %s",
                             (user_id, since, limit)).fetchall()

    # --- coach ---
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

    # --- discussion et notifications ---
    def add_message(self, user_id: int, role: str, body: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._conn() as c:
            return c.execute("INSERT INTO coach_messages (user_id, role, body, meta) VALUES (%s, %s, %s, %s::jsonb) RETURNING *",
                             (user_id, role, body, json.dumps(meta or {}))).fetchone()

    def list_messages(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM coach_messages WHERE user_id = %s ORDER BY id DESC LIMIT %s", (user_id, limit)).fetchall()
        return rows[::-1]

    def get_prefs(self, user_id: int) -> dict[str, Any]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM notify_prefs WHERE user_id = %s", (user_id,)).fetchone()
        return row or {"user_id": user_id, "ntfy_topic": None, "email": None, "push_enabled": False, "email_enabled": False}

    def set_prefs(self, user_id: int, prefs: dict[str, Any]) -> dict[str, Any]:
        cur = {**self.get_prefs(user_id), **prefs}
        with self._conn() as c:
            return c.execute("INSERT INTO notify_prefs (user_id, ntfy_topic, email, push_enabled, email_enabled) VALUES (%s, %s, %s, %s, %s) "
                             "ON CONFLICT (user_id) DO UPDATE SET ntfy_topic = EXCLUDED.ntfy_topic, email = EXCLUDED.email, "
                             "push_enabled = EXCLUDED.push_enabled, email_enabled = EXCLUDED.email_enabled, updated_at = now() RETURNING *",
                             (user_id, cur["ntfy_topic"], cur["email"], cur["push_enabled"], cur["email_enabled"])).fetchone()

    def list_notify_users(self) -> list[int]:
        with self._conn() as c:
            return [r["user_id"] for r in c.execute("SELECT user_id FROM notify_prefs WHERE push_enabled OR email_enabled").fetchall()]

    def add_notify_log(self, user_id: int, kind: str, channel: str, title: str, body: str, ok: bool, error: str | None) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO notify_log (user_id, kind, channel, title, body, ok, error) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                      (user_id, kind, channel, title, body, ok, error))

    def last_notify(self, user_id: int, kind: str | None = None, ok_only: bool = True) -> datetime | None:
        with self._conn() as c:
            row = c.execute("SELECT max(created_at) AS t FROM notify_log WHERE user_id = %s AND (%s::text IS NULL OR kind = %s) "
                            "AND (NOT %s OR ok)", (user_id, kind, kind, ok_only)).fetchone()
        return row["t"]

    def add_subscription(self, user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (%s, %s, %s, %s) "
                      "ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id, p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth",
                      (user_id, endpoint, p256dh, auth))

    def list_subscriptions(self, user_id: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute("SELECT * FROM push_subscriptions WHERE user_id = %s ORDER BY id", (user_id,)).fetchall()

    def delete_subscription(self, user_id: int, endpoint: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s", (user_id, endpoint))

    # --- nutrition ---
    def add_meal(self, user_id: int, day: date, slot: str, description: str, photo_path: str | None) -> dict[str, Any]:
        with self._conn() as c:
            return c.execute("INSERT INTO meals (user_id, day, slot, description, photo_path) VALUES (%s, %s, %s, %s, %s) RETURNING *",
                             (user_id, day, slot, description, photo_path)).fetchone()

    def list_meals(self, user_id: int, start: date, end: date) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute("SELECT * FROM meals WHERE user_id = %s AND day BETWEEN %s AND %s ORDER BY day, id", (user_id, start, end)).fetchall()

    def get_meal(self, user_id: int, meal_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute("SELECT * FROM meals WHERE id = %s AND user_id = %s", (meal_id, user_id)).fetchone()

    def set_meal_analysis(self, user_id: int, meal_id: int, analysis: dict[str, Any]) -> None:
        with self._conn() as c:
            c.execute("UPDATE meals SET analysis = %s::jsonb WHERE id = %s AND user_id = %s", (json.dumps(analysis), meal_id, user_id))

    def delete_meal(self, user_id: int, meal_id: int) -> str | None:
        with self._conn() as c:
            row = c.execute("DELETE FROM meals WHERE id = %s AND user_id = %s RETURNING photo_path", (meal_id, user_id)).fetchone()
            return None if row is None else (row["photo_path"] or "")

    def upsert_weight(self, user_id: int, day: date, kg: float, waist_cm: float | None) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO weight_log (user_id, day, kg, waist_cm) VALUES (%s, %s, %s, %s) "
                      "ON CONFLICT (user_id, day) DO UPDATE SET kg = EXCLUDED.kg, waist_cm = EXCLUDED.waist_cm", (user_id, day, kg, waist_cm))

    def list_weights(self, user_id: int, since: date) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute("SELECT day, kg::float AS kg, waist_cm::float AS waist_cm FROM weight_log WHERE user_id = %s AND day >= %s ORDER BY day",
                             (user_id, since)).fetchall()


def utcnow() -> datetime:
    return datetime.now(UTC)
