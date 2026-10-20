"""Bibliothèque d'exercices : version mémoire et version Postgres du domaine (mêlées dans MemoryRepo / PostgresRepo par héritage)."""
from typing import Any

import psycopg

from app.exercises.models import Exercise, Media


def _matches(e: Exercise, q: str | None, muscle: str | None, equipment: str | None, kind: str | None) -> bool:
    if q and q.lower() not in e.name.lower() and q.lower() not in (e.name_en or "").lower():
        return False
    if muscle and muscle not in e.muscles_primary + e.muscles_secondary:
        return False
    if equipment and equipment not in e.equipment:
        return False
    return not kind or e.kind == kind


class ExercisesMemory:
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


class ExercisesPostgres:
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
