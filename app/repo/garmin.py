"""Montre : compte, activités : version mémoire et version Postgres du domaine (mêlées dans MemoryRepo / PostgresRepo par héritage)."""
import json
from datetime import UTC, date, datetime
from typing import Any

STREAM_FIELDS = ("n", "duration_s", "t", "dist", "hr", "speed", "alt", "cad", "power", "splits")
ARRAY_TYPES = {"t": "int[]", "dist": "real[]", "hr": "smallint[]", "speed": "real[]", "alt": "real[]", "cad": "smallint[]", "power": "smallint[]"}


class GarminMemory:
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
            for k in [k for k, a in self._g()[1].items() if k[0] == user_id and a["source"] == "garmin"]:  # les fichiers importés restent
                del self._g()[1][k]
                self._streams().pop(k, None)  # les courbes suivent l'activité (cascade côté Postgres)
            for k in [k for k in self._metrics() if k[0] == user_id]:
                del self._metrics()[k]

    def upsert_activities(self, user_id: int, rows: list[dict[str, Any]]) -> int:
        new = 0
        for r in rows:
            key = (user_id, r["garmin_id"])
            new += key not in self._g()[1]
            self._g()[1][key] = {"user_id": user_id, "source": "garmin", **r}
        return new

    def list_activities(self, user_id: int, since: date, limit: int) -> list[dict[str, Any]]:
        rows = [a for (u, _), a in self._g()[1].items() if u == user_id and a["day"] >= since]
        return sorted(rows, key=lambda a: a["started_at"], reverse=True)[:limit]


    def _streams(self) -> dict[tuple[int, str], dict[str, Any]]:
        if not hasattr(self, "_st"):
            self._st: dict[tuple[int, str], dict[str, Any]] = {}
        return self._st

    def save_streams(self, user_id: int, garmin_id: str, streams: dict[str, Any]) -> bool:
        if (user_id, garmin_id) not in self._g()[1]:
            return False  # des courbes sans activité n'existent pas (clé étrangère côté Postgres)
        self._streams()[(user_id, garmin_id)] = {k: streams[k] for k in STREAM_FIELDS}
        return True

    def get_streams(self, user_id: int, garmin_id: str) -> dict[str, Any] | None:
        s = self._streams().get((user_id, garmin_id))
        return {**s} if s else None


class GarminPostgres:
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
                c.execute("DELETE FROM garmin_activities WHERE user_id = %s AND source = 'garmin'", (user_id,))
                c.execute("DELETE FROM garmin_metrics WHERE user_id = %s", (user_id,))

    def upsert_activities(self, user_id: int, rows: list[dict[str, Any]]) -> int:
        new = 0
        with self._conn() as c:
            for r in rows:
                cur = c.execute(
                    "INSERT INTO garmin_activities (user_id, source, garmin_id, day, started_at, sport, type_key, name, duration_s, "
                    "distance_m, elevation_m, avg_hr, max_hr, calories, training_load) VALUES (%(u)s, %(source)s, %(garmin_id)s, "
                    "%(day)s, %(started_at)s, %(sport)s, "
                    "%(type_key)s, %(name)s, %(duration_s)s, %(distance_m)s, %(elevation_m)s, %(avg_hr)s, %(max_hr)s, %(calories)s, "
                    "%(training_load)s) ON CONFLICT (user_id, garmin_id) DO UPDATE SET day = EXCLUDED.day, "
                    "sport = EXCLUDED.sport, "
                    "name = EXCLUDED.name, duration_s = EXCLUDED.duration_s, distance_m = EXCLUDED.distance_m, "
                    "elevation_m = EXCLUDED.elevation_m, avg_hr = EXCLUDED.avg_hr, max_hr = EXCLUDED.max_hr, "
                    "calories = EXCLUDED.calories, training_load = EXCLUDED.training_load RETURNING (xmax = 0) AS inserted",
                    {"source": "garmin", **r, "u": user_id}).fetchone()
                new += bool(cur["inserted"])
        return new

    def list_activities(self, user_id: int, since: date, limit: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute("SELECT * FROM garmin_activities WHERE user_id = %s AND day >= %s ORDER BY started_at DESC LIMIT %s",
                             (user_id, since, limit)).fetchall()

    def save_streams(self, user_id: int, garmin_id: str, streams: dict[str, Any]) -> bool:
        cols = ", ".join(ARRAY_TYPES)
        marks = ", ".join(f"%({k})s::{ty}" for k, ty in ARRAY_TYPES.items())
        sets = ", ".join(f"{k} = EXCLUDED.{k}" for k in ("n", "duration_s", "splits", *ARRAY_TYPES))
        with self._conn() as c:
            if not c.execute("SELECT 1 FROM garmin_activities WHERE user_id = %s AND garmin_id = %s", (user_id, garmin_id)).fetchone():
                return False
            c.execute(f"INSERT INTO activity_streams (user_id, garmin_id, n, duration_s, {cols}, splits) VALUES (%(u)s, %(g)s, %(n)s, %(duration_s)s, {marks}, %(splits)s::jsonb) "
                      f"ON CONFLICT (user_id, garmin_id) DO UPDATE SET {sets}",
                      {**{k: streams[k] for k in STREAM_FIELDS if k != "splits"}, "splits": json.dumps(streams["splits"]), "u": user_id, "g": garmin_id})
        return True

    def get_streams(self, user_id: int, garmin_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT n, duration_s, t, dist, hr, speed, alt, cad, power, splits FROM activity_streams WHERE user_id = %s AND garmin_id = %s", (user_id, garmin_id)).fetchone()
        return dict(row) if row else None
