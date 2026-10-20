"""Discussion avec le coach, préférences et notifications : version mémoire et version Postgres du domaine (mêlées dans MemoryRepo / PostgresRepo par héritage)."""
import json
from datetime import UTC, datetime
from typing import Any


class ChatMemory:
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


class ChatPostgres:
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
