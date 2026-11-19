"""Stockage SQLite : un fichier local, aucun serveur (application de bureau, essai local).

Mêmes méthodes et mêmes types Python rendus que `PostgresRepo` (dates, datetimes aware en UTC, listes, dicts, booléens).
Choix de conception :
- une connexion par thread (FastAPI exécute les routes synchrones dans un pool) ; aucune connexion n'est jamais partagée ;
- mode WAL (lecteurs et écrivain ne se bloquent pas) + `busy_timeout` : les écrivains concurrents s'attendent au lieu d'échouer ;
- chaque écriture est une transaction `BEGIN IMMEDIATE` (verrou pris d'emblée, donc pas d'échec « database is locked » en cours de route) ;
- `PRAGMA foreign_keys=ON` : les cascades de Postgres (`ON DELETE CASCADE`) existent aussi ici ;
- schéma versionné dans `db/sqlite/*.sql`, appliqué au démarrage (table `schema_migrations`), rejouable sans effet.
"""
import json
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.exercises.models import Exercise, Media
from app.questionnaire.models import Fact

log = logging.getLogger(__name__)

URL_PREFIX = "sqlite:"
_MIN_SQLITE = (3, 35, 0)  # RETURNING
BUSY_TIMEOUT_MS = 10_000

# Colonnes à convertir au rendu (les noms sont uniques en sémantique dans le schéma).
_DATES = {"day", "target_date", "period_start", "period_end"}
_TS_UTC = {"created_at", "updated_at", "closed_at", "connected_at", "last_sync_at", "backfilled_at", "observed_at", "recorded_at", "expires_at"}
_TS_NAIVE = {"started_at"}  # TIMESTAMP sans fuseau côté Postgres
_JSON = {"details", "logged", "data", "meta", "analysis", "splits", "sources", "muscles_primary", "muscles_secondary", "equipment", "rules", "notes",
         "t", "dist", "hr", "speed", "alt", "cad", "power"}
_BOOLS = {"is_main", "ok", "push_enabled", "email_enabled"}
STREAM_FIELDS = ("n", "duration_s", "t", "dist", "hr", "speed", "alt", "cad", "power", "splits")
_STREAM_ARRAYS = ("t", "dist", "hr", "speed", "alt", "cad", "power")
_DEFAULT_PREFS = {"ntfy_topic": None, "email": None, "push_enabled": False, "email_enabled": False}


def sqlite_path(url: str) -> str:
    """Chemin du fichier d'une URL `sqlite:///chemin` (relatif) ou `sqlite:////abs` / `sqlite:///C:/abs` (absolu). `~` est développé."""
    if not url.startswith("sqlite:///"):
        raise ValueError("URL SQLite attendue : sqlite:///chemin/vers/coach.db")
    path = url[len("sqlite:///"):]
    if not path or path == ":memory:":
        raise ValueError("sqlite:/// exige un chemin de fichier (la base en mémoire n'est pas persistante : utiliser le stockage mémoire)")
    return os.path.expanduser(path)


def is_sqlite_url(url: str) -> bool:
    return url.lower().startswith(URL_PREFIX)


def _ts(dt: datetime) -> str:
    """Horodatage UTC à largeur fixe : l'ordre du texte est l'ordre du temps. Un datetime naïf est lu comme UTC."""
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _ts_naive(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _now() -> str:
    return _ts(datetime.now(UTC))


def _day(d: date | None) -> str | None:
    return None if d is None else d.isoformat()


def _js(v: Any) -> str | None:
    return None if v is None else json.dumps(v, ensure_ascii=False, allow_nan=False)


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    for k, v in row.items():
        if v is None:
            continue
        if k in _DATES:
            row[k] = date.fromisoformat(v)
        elif k in _TS_UTC:
            d = datetime.fromisoformat(v)
            row[k] = d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)
        elif k in _TS_NAIVE:
            row[k] = datetime.fromisoformat(v).replace(tzinfo=None)
        elif k in _JSON:
            row[k] = json.loads(v)
        elif k in _BOOLS:
            row[k] = bool(v)
    return row


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    names = [d[0] for d in cur.description]
    return [_decode(dict(zip(names, r, strict=True))) for r in cur.fetchall()]


def _row(cur: sqlite3.Cursor) -> dict[str, Any] | None:
    rows = _rows(cur)
    return rows[0] if rows else None


def _py_lower(s: str | None) -> str:
    return (s or "").lower()


class SqliteRepo:
    name = "sqlite"

    def __init__(self, path: str | os.PathLike[str]) -> None:
        if sqlite3.sqlite_version_info < _MIN_SQLITE:
            raise RuntimeError(f"SQLite {'.'.join(map(str, _MIN_SQLITE))} minimum requis (version présente : {sqlite3.sqlite_version})")
        self.path = Path(path)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._conns: list[tuple[threading.Thread, sqlite3.Connection]] = []  # pour fermer celles des threads terminés et à l'arrêt
        self._prepare_file()
        with self._tx() as c:  # échoue tôt et clairement si JSON1 manque ou si le fichier n'est pas une base
            c.execute("SELECT count(*) FROM json_each('[1]')").fetchone()
        self._wal()

    # ---- connexion et transactions ----------------------------------------------------------------------------------------------------------------

    def _prepare_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            try:  # création en 0600 : le fichier contient des données de santé et des hachages de mot de passe ; -wal et -shm héritent de ses droits
                os.close(os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600))
            except OSError:
                log.warning("droits du fichier SQLite non restreints : %s", self.path)

    def _wal(self) -> None:
        c = self._connection()
        if c.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
            log.warning("mode WAL indisponible pour %s (système de fichiers réseau ?) : performances et concurrence réduites", self.path)

    def _connection(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None, check_same_thread=False)  # autocommit, transactions explicites
            # check_same_thread=False : seulement pour fermer, depuis un autre thread, la connexion d'un thread terminé ; jamais d'usage partagé
            c.execute("PRAGMA foreign_keys=ON")
            c.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            c.execute("PRAGMA synchronous=NORMAL")  # sûr en WAL : au pire la dernière transaction est perdue sur coupure de courant, jamais corrompue
            c.create_function("py_lower", 1, _py_lower, deterministic=True)  # minuscules Unicode comme MemoryRepo (LOWER de SQLite ne gère que l'ASCII)
            self._local.conn = c
            self._register(c)
        return c

    def _register(self, c: sqlite3.Connection) -> None:
        with self._lock:
            alive = []
            for t, old in self._conns:
                if t.is_alive():
                    alive.append((t, old))
                else:  # le thread du pool est mort : sa connexion ne servira plus
                    old.close()
            alive.append((threading.current_thread(), c))
            self._conns = alive

    @contextmanager
    def _tx(self, write: bool = True) -> Iterator[sqlite3.Connection]:
        c = self._connection()
        c.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield c
        except BaseException:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        c.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            conns, self._conns = self._conns, []
        for _, c in conns:
            try:
                c.close()
            except sqlite3.Error:
                pass
        self._local = threading.local()

    # ---- migrations -------------------------------------------------------------------------------------------------------------------------------

    def migrate(self, directory: Path) -> None:
        """Applique dans l'ordre les `*.sql` pas encore enregistrés dans `schema_migrations`, chacun dans une transaction (tout ou rien)."""
        files = sorted(Path(directory).glob("*.sql"))
        if not files:
            raise RuntimeError(f"aucune migration SQLite dans {directory}")
        with self._tx() as c:
            c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        known = {p.stem for p in files}
        for path in files:
            with self._tx() as c:  # verrou d'écriture : deux processus qui démarrent ensemble ne rejouent pas la même migration
                if c.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (path.stem,)).fetchone():
                    continue
                buf = ""
                for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
                    buf += line
                    if sqlite3.complete_statement(buf):
                        c.execute(buf)
                        buf = ""
                if buf.strip() and any(not ln.strip().startswith("--") for ln in buf.splitlines() if ln.strip()):
                    raise RuntimeError(f"{path.name} : instruction incomplète à la fin du fichier")
                c.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (path.stem, _now()))
        with self._tx(write=False) as c:
            extra = {r[0] for r in c.execute("SELECT version FROM schema_migrations")} - known
        if extra:
            log.warning("la base contient des migrations inconnues de cette version (%s) : base créée par une version plus récente ?", ", ".join(sorted(extra)))

    # ---- utilisateurs et faits --------------------------------------------------------------------------------------------------------------------

    def create_user(self, name: str) -> int:
        with self._tx() as c:
            return c.execute("INSERT INTO users (name, created_at) VALUES (?, ?) RETURNING id", (name, _now())).fetchone()[0]

    def user_exists(self, user_id: int) -> bool:
        with self._tx(write=False) as c:
            return c.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is not None

    def add_facts(self, user_id: int, facts: list[Fact]) -> None:
        with self._tx() as c:
            for f in facts:
                prev = c.execute("SELECT id FROM facts WHERE user_id = ? AND key = ? ORDER BY observed_at DESC, id DESC LIMIT 1", (user_id, f.key)).fetchone()
                c.execute("INSERT INTO facts (user_id, key, value, source, confidence, observed_at, recorded_at, supersedes_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (user_id, f.key, json.dumps(f.value, ensure_ascii=False), f.source, f.confidence, _ts(f.observed_at), _now(), prev[0] if prev else None))

    def list_facts(self, user_id: int) -> list[Fact]:
        with self._tx(write=False) as c:
            rows = _rows(c.execute("SELECT key, value, source, confidence, observed_at FROM facts WHERE user_id = ? ORDER BY observed_at, id", (user_id,)))
        for r in rows:
            r["value"] = json.loads(r["value"])
        return [Fact(**r) for r in rows]

    # ---- comptes et sessions ----------------------------------------------------------------------------------------------------------------------

    def create_account(self, name: str, email: str, password_hash: str) -> int:
        with self._tx() as c:
            return c.execute("INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?) RETURNING id", (name, email, password_hash, _now())).fetchone()[0]

    def get_account(self, email: str) -> dict[str, Any] | None:
        with self._tx(write=False) as c:
            return _row(c.execute("SELECT id, name, password_hash, lang FROM users WHERE email = ?", (email,)))

    def list_legacy_users(self) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT u.id, u.name, (SELECT count(*) FROM facts f WHERE f.user_id = u.id) AS answers FROM users u WHERE u.email IS NULL ORDER BY u.id"))

    def has_accounts(self) -> bool:
        with self._tx(write=False) as c:
            return c.execute("SELECT EXISTS (SELECT 1 FROM users WHERE email IS NOT NULL)").fetchone()[0] == 1

    def adopt_legacy_user(self, user_id: int, name: str, email: str, password_hash: str) -> bool:
        with self._tx() as c:
            return c.execute("UPDATE users SET name = ?, email = ?, password_hash = ? WHERE id = ? AND email IS NULL", (name, email, password_hash, user_id)).rowcount == 1

    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
            c.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)", (token_hash, user_id, _now(), _ts(expires_at)))

    def get_session_user(self, token_hash: str) -> dict[str, Any] | None:
        with self._tx(write=False) as c:
            return _row(c.execute("SELECT u.id, u.name, u.email, u.lang FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
                                  (token_hash, _now())))

    def delete_session(self, token_hash: str) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def set_password(self, user_id: int, password_hash: str, keep_session: str | None) -> None:
        """Change le mot de passe et ferme les autres sessions de l'utilisateur."""
        with self._tx() as c:
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
            c.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash IS NOT ?", (user_id, keep_session))

    def set_language(self, user_id: int, lang: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, user_id))

    def get_language(self, user_id: int) -> str | None:
        with self._tx(write=False) as c:
            row = c.execute("SELECT lang FROM users WHERE id = ?", (user_id,)).fetchone()
        return row[0] if row else None

    # ---- exercices --------------------------------------------------------------------------------------------------------------------------------

    def replace_exercises(self, exercises: list[Exercise]) -> int:
        """Upsert par (source, source_id) ; les médias d'un exercice sont remplacés."""
        with self._tx() as c:
            for e in exercises:
                eid = c.execute(
                    "INSERT INTO exercises (source, source_id, sources, name, name_en, kind, region, muscles_primary, muscles_secondary, equipment, level, instructions, "
                    "instructions_lang, license, license_url, author) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT (source, source_id) DO UPDATE SET sources=excluded.sources, name=excluded.name, name_en=excluded.name_en, kind=excluded.kind, "
                    "region=excluded.region, muscles_primary=excluded.muscles_primary, muscles_secondary=excluded.muscles_secondary, equipment=excluded.equipment, "
                    "level=excluded.level, instructions=excluded.instructions, instructions_lang=excluded.instructions_lang, license=excluded.license, "
                    "license_url=excluded.license_url, author=excluded.author RETURNING id",
                    (e.source, e.source_id, _js(e.sources), e.name, e.name_en, e.kind, e.region, _js(e.muscles_primary), _js(e.muscles_secondary), _js(e.equipment),
                     e.level, e.instructions, e.instructions_lang, e.license, e.license_url, e.author)).fetchone()[0]
                c.execute("DELETE FROM exercise_media WHERE exercise_id = ?", (eid,))
                for m in e.media:
                    c.execute("INSERT INTO exercise_media (exercise_id, kind, url, thumb_url, is_main, license, license_url, author) VALUES (?,?,?,?,?,?,?,?)",
                              (eid, m.kind, m.url, m.thumb_url, int(m.is_main), m.license, m.license_url, m.author))
        return len(exercises)

    @staticmethod
    def _load_exercises(c: sqlite3.Connection, rows: list[dict[str, Any]]) -> list[Exercise]:
        if not rows:
            return []
        media: dict[int, list[Media]] = {r["id"]: [] for r in rows}
        marks = ",".join("?" * len(media))
        for m in _rows(c.execute(f"SELECT * FROM exercise_media WHERE exercise_id IN ({marks}) ORDER BY is_main DESC, id", list(media))):
            media[m.pop("exercise_id")].append(Media(**m))
        return [Exercise(**r, media=media[r["id"]]) for r in rows]

    def search_exercises(self, q: str | None, muscle: str | None, equipment: str | None, kind: str | None, limit: int, offset: int) -> tuple[list[Exercise], int]:
        where, args = ["1"], []
        if q:  # sous-chaîne sans caractères génériques, insensible à la casse Unicode (comme MemoryRepo)
            where.append("(instr(py_lower(name), ?) > 0 OR instr(py_lower(name_en), ?) > 0)")
            args += [q.lower(), q.lower()]
        if muscle:
            where.append("(EXISTS (SELECT 1 FROM json_each(muscles_primary) WHERE value = ?) OR EXISTS (SELECT 1 FROM json_each(muscles_secondary) WHERE value = ?))")
            args += [muscle, muscle]
        if equipment:
            where.append("EXISTS (SELECT 1 FROM json_each(equipment) WHERE value = ?)")
            args.append(equipment)
        if kind:
            where.append("kind = ?")
            args.append(kind)
        cond = " AND ".join(where)
        with self._tx(write=False) as c:
            total = c.execute(f"SELECT count(*) FROM exercises WHERE {cond}", args).fetchone()[0]
            rows = _rows(c.execute(f"SELECT * FROM exercises WHERE {cond} ORDER BY (NOT EXISTS (SELECT 1 FROM exercise_media m WHERE m.exercise_id = exercises.id "
                                   "AND m.kind = 'image')), py_lower(name), id LIMIT ? OFFSET ?", [*args, limit, offset]))
            return self._load_exercises(c, rows), total

    def get_exercise(self, exercise_id: int) -> Exercise | None:
        with self._tx(write=False) as c:
            found = self._load_exercises(c, _rows(c.execute("SELECT * FROM exercises WHERE id = ?", (exercise_id,))))
        return found[0] if found else None

    def get_media(self, media_id: int) -> Media | None:
        with self._tx(write=False) as c:
            row = _row(c.execute("SELECT * FROM exercise_media WHERE id = ?", (media_id,)))
        if not row:
            return None
        row.pop("exercise_id")
        return Media(**row)

    # ---- repas et poids ---------------------------------------------------------------------------------------------------------------------------

    def add_meal(self, user_id: int, day: date, slot: str, description: str, photo_path: str | None) -> dict[str, Any]:
        with self._tx() as c:
            return _row(c.execute("INSERT INTO meals (user_id, day, slot, description, photo_path, created_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
                                  (user_id, _day(day), slot, description, photo_path, _now())))

    def list_meals(self, user_id: int, start: date, end: date) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT * FROM meals WHERE user_id = ? AND day BETWEEN ? AND ? ORDER BY day, id", (user_id, _day(start), _day(end))))

    def get_meal(self, user_id: int, meal_id: int) -> dict[str, Any] | None:
        with self._tx(write=False) as c:
            return _row(c.execute("SELECT * FROM meals WHERE id = ? AND user_id = ?", (meal_id, user_id)))

    def set_meal_analysis(self, user_id: int, meal_id: int, analysis: dict[str, Any]) -> None:
        with self._tx() as c:
            c.execute("UPDATE meals SET analysis = ? WHERE id = ? AND user_id = ?", (_js(analysis), meal_id, user_id))

    def delete_meal(self, user_id: int, meal_id: int) -> str | None:
        with self._tx() as c:
            row = c.execute("DELETE FROM meals WHERE id = ? AND user_id = ? RETURNING photo_path", (meal_id, user_id)).fetchone()
        return None if row is None else (row[0] or "")

    def upsert_weight(self, user_id: int, day: date, kg: float, waist_cm: float | None) -> None:
        with self._tx() as c:
            c.execute("INSERT INTO weight_log (user_id, day, kg, waist_cm) VALUES (?, ?, ?, ?) ON CONFLICT (user_id, day) DO UPDATE SET kg = excluded.kg, waist_cm = excluded.waist_cm",
                      (user_id, _day(day), kg, waist_cm))

    def list_weights(self, user_id: int, since: date) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT day, kg, waist_cm FROM weight_log WHERE user_id = ? AND day >= ? ORDER BY day", (user_id, _day(since))))

    # ---- objectifs --------------------------------------------------------------------------------------------------------------------------------

    def list_goals(self, user_id: int, status: str | None) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT * FROM goals WHERE user_id = ? AND (? IS NULL OR status = ?) ORDER BY target_date NULLS LAST, id", (user_id, status, status)))

    def create_goal(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        with self._tx() as c:
            return _row(c.execute("INSERT INTO goals (user_id, title, kind, target_date, priority, success, details, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?) RETURNING *",
                                  (user_id, data["title"], data.get("kind", "other"), _day(data.get("target_date")), data.get("priority", "important"), data.get("success"),
                                   _js(data.get("details", {})), now, now)))

    def update_goal(self, user_id: int, goal_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        cols = {"title", "kind", "target_date", "priority", "success", "details", "status"}
        now = _now()
        sets, args = ["updated_at = ?"], [now]
        for k, v in changes.items():
            if k not in cols or (v is None and k != "target_date"):
                continue
            sets.append(f"{k} = ?")
            args.append(_js(v) if k == "details" else _day(v) if k == "target_date" else v)
        if changes.get("status") in ("done", "dropped"):
            sets.append("closed_at = ?")
            args.append(now)
        elif changes.get("status") == "active":
            sets.append("closed_at = NULL")
        with self._tx() as c:
            return _row(c.execute(f"UPDATE goals SET {', '.join(sets)} WHERE id = ? AND user_id = ? RETURNING *", [*args, goal_id, user_id]))

    def delete_goal(self, user_id: int, goal_id: int) -> bool:
        with self._tx() as c:
            return c.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id)).rowcount == 1

    # ---- séances ----------------------------------------------------------------------------------------------------------------------------------

    def add_sessions(self, user_id: int, rows: list[dict[str, Any]]) -> None:
        now = _now()
        with self._tx() as c:
            for r in rows:
                c.execute("INSERT INTO planned_sessions (user_id, day, kind, title, duration_min, details, rules, notes, status, logged, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (user_id, _day(r["day"]), r["kind"], r["title"], r["duration_min"], _js(r["details"]), _js(r["rules"]), _js(r["notes"]),
                           r.get("status", "planned"), _js(r.get("logged")), now, now))  # `status`/`logged` facultatifs, comme MemoryRepo

    def list_sessions(self, user_id: int, start: date, end: date | None) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT * FROM planned_sessions WHERE user_id = ? AND day >= ? AND (? IS NULL OR day < ?) ORDER BY day, id",
                                   (user_id, _day(start), _day(end), _day(end))))

    def delete_planned_from(self, user_id: int, day: date) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM planned_sessions WHERE user_id = ? AND status = 'planned' AND day >= ?", (user_id, _day(day)))

    def update_session(self, user_id: int, session_id: int, status: str, logged: dict[str, Any] | None) -> dict[str, Any] | None:
        with self._tx() as c:
            return _row(c.execute("UPDATE planned_sessions SET status = ?, logged = COALESCE(?, logged), updated_at = ? WHERE id = ? AND user_id = ? RETURNING *",
                                  (status, _js(logged), _now(), session_id, user_id)))

    def move_session(self, user_id: int, session_id: int, day: date) -> dict[str, Any] | None:
        with self._tx() as c:
            cur = _row(c.execute("SELECT * FROM planned_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)))
            if not cur:
                return None
            details = cur["details"]
            if cur["day"] != day:  # le jour d'origine est conservé au premier déplacement
                details = {**details, "moved_from": details.get("moved_from") or cur["day"].isoformat()}
            return _row(c.execute("UPDATE planned_sessions SET details = ?, day = ?, updated_at = ? WHERE id = ? AND user_id = ? RETURNING *",
                                  (_js(details), _day(day), _now(), session_id, user_id)))

    def add_session(self, user_id: int, row: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        with self._tx() as c:
            return _row(c.execute("INSERT INTO planned_sessions (user_id, day, kind, title, duration_min, details, rules, notes, status, logged, created_at, updated_at) "
                                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *",
                                  (user_id, _day(row["day"]), row["kind"], row["title"], row["duration_min"], _js(row["details"]), _js(row["rules"]), _js(row["notes"]),
                                   row.get("status", "planned"), _js(row.get("logged")), now, now)))

    def remove_session(self, user_id: int, session_id: int) -> bool:
        with self._tx() as c:
            return c.execute("DELETE FROM planned_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)).rowcount > 0

    def patch_planned(self, user_id: int, session_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        sets, args = ["updated_at = ?"], [_now()]
        for k, v in changes.items():
            if k in {"duration_min", "day", "kind", "title", "details", "notes"}:
                sets.append(f"{k} = ?")
                args.append(_js(v) if k in ("details", "notes") else _day(v) if k == "day" else v)
        with self._tx() as c:
            return _row(c.execute(f"UPDATE planned_sessions SET {', '.join(sets)} WHERE id = ? AND user_id = ? AND status = 'planned' RETURNING *", [*args, session_id, user_id]))

    # ---- montre -----------------------------------------------------------------------------------------------------------------------------------

    def get_garmin(self, user_id: int) -> dict[str, Any] | None:
        with self._tx(write=False) as c:
            return _row(c.execute("SELECT * FROM garmin_accounts WHERE user_id = ?", (user_id,)))

    def save_garmin(self, user_id: int, email: str, tokens_enc: str) -> None:
        with self._tx() as c:
            c.execute("INSERT INTO garmin_accounts (user_id, email, tokens_enc, connected_at) VALUES (?, ?, ?, ?) "
                      "ON CONFLICT (user_id) DO UPDATE SET email = excluded.email, tokens_enc = excluded.tokens_enc, connected_at = excluded.connected_at, "
                      "last_sync_at = NULL, last_error = NULL, backfilled_at = NULL", (user_id, email, tokens_enc, _now()))

    def touch_garmin(self, user_id: int, tokens_enc: str | None, error: str | None) -> None:
        with self._tx() as c:
            c.execute("UPDATE garmin_accounts SET tokens_enc = COALESCE(?, tokens_enc), last_error = ?, last_sync_at = CASE WHEN ? IS NULL THEN ? ELSE last_sync_at END WHERE user_id = ?",
                      (tokens_enc, error, error, _now(), user_id))

    def delete_garmin(self, user_id: int, purge: bool) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM garmin_accounts WHERE user_id = ?", (user_id,))
            if purge:  # les fichiers importés restent ; les courbes suivent l'activité (cascade)
                c.execute("DELETE FROM garmin_activities WHERE user_id = ? AND source = 'garmin'", (user_id,))
                c.execute("DELETE FROM garmin_metrics WHERE user_id = ?", (user_id,))

    def upsert_activities(self, user_id: int, rows: list[dict[str, Any]]) -> int:
        new = 0
        with self._tx() as c:
            for r in rows:
                p = {"source": "garmin", **r, "u": user_id}
                p["day"], p["started_at"] = _day(p["day"]), None if p["started_at"] is None else _ts_naive(p["started_at"])
                new += c.execute("SELECT 1 FROM garmin_activities WHERE user_id = ? AND garmin_id = ?", (user_id, p["garmin_id"])).fetchone() is None
                c.execute("INSERT INTO garmin_activities (user_id, source, garmin_id, day, started_at, sport, type_key, name, duration_s, distance_m, elevation_m, avg_hr, max_hr, "
                          "calories, training_load) VALUES (:u, :source, :garmin_id, :day, :started_at, :sport, :type_key, :name, :duration_s, :distance_m, :elevation_m, "
                          ":avg_hr, :max_hr, :calories, :training_load) ON CONFLICT (user_id, garmin_id) DO UPDATE SET day = excluded.day, sport = excluded.sport, "
                          "name = excluded.name, duration_s = excluded.duration_s, distance_m = excluded.distance_m, elevation_m = excluded.elevation_m, "
                          "avg_hr = excluded.avg_hr, max_hr = excluded.max_hr, calories = excluded.calories, training_load = excluded.training_load", p)
        return new

    def list_activities(self, user_id: int, since: date, limit: int) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT * FROM garmin_activities WHERE user_id = ? AND day >= ? ORDER BY started_at DESC LIMIT ?", (user_id, _day(since), limit)))

    def save_streams(self, user_id: int, garmin_id: str, streams: dict[str, Any]) -> bool:
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM garmin_activities WHERE user_id = ? AND garmin_id = ?", (user_id, garmin_id)).fetchone():
                return False  # des courbes sans activité n'existent pas (clé étrangère)
            sets = ", ".join(f"{k} = excluded.{k}" for k in ("n", "duration_s", "splits", *_STREAM_ARRAYS))
            c.execute(f"INSERT INTO activity_streams (user_id, garmin_id, n, duration_s, {', '.join(_STREAM_ARRAYS)}, splits, created_at) "
                      f"VALUES (?, ?, ?, ?, {', '.join('?' * len(_STREAM_ARRAYS))}, ?, ?) ON CONFLICT (user_id, garmin_id) DO UPDATE SET {sets}",
                      (user_id, garmin_id, streams["n"], streams["duration_s"], *(_js(streams[k]) for k in _STREAM_ARRAYS), _js(streams["splits"]), _now()))
        return True

    def get_streams(self, user_id: int, garmin_id: str) -> dict[str, Any] | None:
        with self._tx(write=False) as c:
            return _row(c.execute(f"SELECT {', '.join(STREAM_FIELDS)} FROM activity_streams WHERE user_id = ? AND garmin_id = ?", (user_id, garmin_id)))

    def list_garmin_users(self) -> list[int]:
        with self._tx(write=False) as c:
            return [r[0] for r in c.execute("SELECT user_id FROM garmin_accounts")]

    def mark_backfilled(self, user_id: int) -> None:
        with self._tx() as c:
            c.execute("UPDATE garmin_accounts SET backfilled_at = ? WHERE user_id = ?", (_now(), user_id))

    def prune_activities(self, user_id: int, before: date) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM garmin_activities WHERE user_id = ? AND day < ?", (user_id, _day(before)))
            c.execute("DELETE FROM garmin_metrics WHERE user_id = ? AND day < ?", (user_id, _day(before)))

    def upsert_metrics(self, user_id: int, rows: list[dict[str, Any]]) -> int:
        with self._tx() as c:
            for r in rows:
                c.execute("INSERT INTO garmin_metrics (user_id, day, metric, value, text) VALUES (?, ?, ?, ?, ?) "
                          "ON CONFLICT (user_id, metric, day) DO UPDATE SET value = excluded.value, text = excluded.text",
                          (user_id, _day(r["day"]), r["metric"], r.get("value"), r.get("text")))
        return len(rows)

    def list_metrics(self, user_id: int, metric: str | None, since: date, until: date | None = None) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT * FROM garmin_metrics WHERE user_id = ? AND (? IS NULL OR metric = ?) AND day >= ? AND (? IS NULL OR day <= ?) ORDER BY metric, day",
                                   (user_id, metric, metric, _day(since), _day(until), _day(until))))

    # ---- mémoire du coach et appels LLM -----------------------------------------------------------------------------------------------------------

    def add_memory(self, user_id: int, kind: str, period: tuple[date | None, date | None], body: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._tx() as c:
            return _row(c.execute("INSERT INTO coach_memory (user_id, kind, period_start, period_end, body, data, created_at) VALUES (?,?,?,?,?,?,?) RETURNING *",
                                  (user_id, kind, _day(period[0]), _day(period[1]), body, _js(data), _now())))

    def list_memory(self, user_id: int, kind: str | None, limit: int) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT * FROM coach_memory WHERE user_id = ? AND (? IS NULL OR kind = ?) ORDER BY id DESC LIMIT ?", (user_id, kind, kind, limit)))

    def get_memory(self, user_id: int, memory_id: int) -> dict[str, Any] | None:
        with self._tx(write=False) as c:
            return _row(c.execute("SELECT * FROM coach_memory WHERE id = ? AND user_id = ?", (memory_id, user_id)))

    def update_memory_data(self, user_id: int, memory_id: int, data: dict[str, Any]) -> None:
        with self._tx() as c:
            c.execute("UPDATE coach_memory SET data = ? WHERE id = ? AND user_id = ?", (_js(data), memory_id, user_id))

    def log_llm_call(self, user_id: int | None, kind: str, model: str, tokens: tuple[int, int], cost: float, ok: bool, error: str | None) -> None:
        with self._tx() as c:
            c.execute("INSERT INTO llm_calls (user_id, kind, model, input_tokens, output_tokens, cost_eur, ok, error, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                      (user_id, kind, model, tokens[0], tokens[1], cost, int(ok), error, _now()))

    def llm_spend_month(self, month_start: date) -> float:
        with self._tx(write=False) as c:
            return float(c.execute("SELECT COALESCE(SUM(cost_eur), 0) FROM llm_calls WHERE created_at >= ?", (_day(month_start),)).fetchone()[0])

    def llm_calls_since(self, user_id: int, kind: str, since: datetime) -> int:
        with self._tx(write=False) as c:
            return c.execute("SELECT count(*) FROM llm_calls WHERE user_id = ? AND kind = ? AND created_at >= ?", (user_id, kind, _ts(since))).fetchone()[0]

    def llm_usage_since(self, since: datetime, user_id: int) -> list[dict[str, Any]]:
        """Appels réussis depuis `since`, agrégés par (usage, modèle, appel du compte demandé ou non) : aucune identité d'autrui."""
        with self._tx(write=False) as c:
            rows = c.execute("SELECT kind, model, (user_id IS ?) AS mine, count(*), COALESCE(SUM(cost_eur), 0) FROM llm_calls WHERE ok = 1 AND created_at >= ? "
                             "GROUP BY kind, model, mine", (user_id, _ts(since))).fetchall()
        return [{"kind": r[0], "model": r[1], "mine": bool(r[2]), "calls": int(r[3]), "cost": float(r[4])} for r in rows]

    # ---- discussion, préférences, notifications ---------------------------------------------------------------------------------------------------

    def add_message(self, user_id: int, role: str, body: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._tx() as c:
            return _row(c.execute("INSERT INTO coach_messages (user_id, role, body, meta, created_at) VALUES (?, ?, ?, ?, ?) RETURNING *",
                                  (user_id, role, body, _js(meta or {}), _now())))

    def list_messages(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT * FROM coach_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)))[::-1]

    @staticmethod
    def _prefs(c: sqlite3.Connection, user_id: int) -> dict[str, Any]:
        return _row(c.execute("SELECT * FROM notify_prefs WHERE user_id = ?", (user_id,))) or {"user_id": user_id, **_DEFAULT_PREFS}

    def get_prefs(self, user_id: int) -> dict[str, Any]:
        with self._tx(write=False) as c:
            return self._prefs(c, user_id)

    def set_prefs(self, user_id: int, prefs: dict[str, Any]) -> dict[str, Any]:
        with self._tx() as c:
            cur = {**self._prefs(c, user_id), **prefs}
            return _row(c.execute("INSERT INTO notify_prefs (user_id, ntfy_topic, email, push_enabled, email_enabled, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                                  "ON CONFLICT (user_id) DO UPDATE SET ntfy_topic = excluded.ntfy_topic, email = excluded.email, push_enabled = excluded.push_enabled, "
                                  "email_enabled = excluded.email_enabled, updated_at = excluded.updated_at RETURNING *",
                                  (user_id, cur["ntfy_topic"], cur["email"], int(bool(cur["push_enabled"])), int(bool(cur["email_enabled"])), _now())))

    def list_notify_users(self) -> list[int]:
        with self._tx(write=False) as c:
            return [r[0] for r in c.execute("SELECT user_id FROM notify_prefs WHERE push_enabled OR email_enabled")]

    def add_notify_log(self, user_id: int, kind: str, channel: str, title: str, body: str, ok: bool, error: str | None) -> None:
        with self._tx() as c:
            c.execute("INSERT INTO notify_log (user_id, kind, channel, title, body, ok, error, created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (user_id, kind, channel, title, body, int(ok), error, _now()))

    def last_notify(self, user_id: int, kind: str | None = None, ok_only: bool = True) -> datetime | None:
        with self._tx(write=False) as c:
            row = _row(c.execute("SELECT max(created_at) AS created_at FROM notify_log WHERE user_id = ? AND (? IS NULL OR kind = ?) AND (NOT ? OR ok)",
                                 (user_id, kind, kind, int(ok_only))))
        return row["created_at"]

    def add_subscription(self, user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
        with self._tx() as c:
            c.execute("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?, ?) "
                      "ON CONFLICT (endpoint) DO UPDATE SET user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth",
                      (user_id, endpoint, p256dh, auth, _now()))

    def list_subscriptions(self, user_id: int) -> list[dict[str, Any]]:
        with self._tx(write=False) as c:
            return _rows(c.execute("SELECT * FROM push_subscriptions WHERE user_id = ? ORDER BY id", (user_id,)))

    def delete_subscription(self, user_id: int, endpoint: str) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))
