"""Repas et poids : version mémoire et version Postgres du domaine (mêlées dans MemoryRepo / PostgresRepo par héritage)."""
import json
from datetime import UTC, date, datetime
from typing import Any


class NutritionMemory:
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


class NutritionPostgres:
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
