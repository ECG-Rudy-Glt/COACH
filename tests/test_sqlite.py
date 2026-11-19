"""Stockage SQLite : choix par DATABASE_URL, persistance, migrations rejouables, atomicité, accès concurrents, chemins Windows."""
import os
import re
import sqlite3
import stat
import subprocess
import sys
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.repo as repo_pkg
from app.main import app, get_repo
from app.questionnaire.models import Fact
from app.repo import SqliteRepo, open_repo
from app.repo.sqlite import is_sqlite_url, sqlite_path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "db" / "sqlite"
PW = "un-mot-de-passe-solide"


def url(path: Path) -> str:
    return f"sqlite:///{path}"


@pytest.fixture
def repo(tmp_path):
    r = open_repo(url(tmp_path / "coach.db"))
    yield r
    r.close()


# ---- choix du stockage et chemins ------------------------------------------------------------------------------------------------------------------


def test_database_url_selects_the_storage(tmp_path, monkeypatch):
    if os.environ.get("COACH_TEST_REPO") != "sqlite":  # dans ce mode, MemoryRepo est remplacé par SQLite pour toute la suite
        assert open_repo("").name == "memory"
    r = open_repo(url(tmp_path / "x.db"))
    assert r.name == "sqlite" and (tmp_path / "x.db").exists()
    r.close()
    monkeypatch.setenv("DATABASE_URL", url(tmp_path / "env.db"))
    from app.config import database_url

    assert database_url().startswith("sqlite:///")
    assert is_sqlite_url("sqlite:///a.db") and is_sqlite_url("SQLITE:///a.db") and not is_sqlite_url("postgresql://u@h/db")


@pytest.mark.parametrize("raw,expected", [
    ("sqlite:///coach.db", "coach.db"),
    ("sqlite:///data/sub/coach.db", "data/sub/coach.db"),
    ("sqlite:////var/lib/coach/coach.db", "/var/lib/coach/coach.db"),
    ("sqlite:///C:/Users/x/coach.db", "C:/Users/x/coach.db"),
    (r"sqlite:///C:\Users\x\AppData\Roaming\COACH\coach.db", r"C:\Users\x\AppData\Roaming\COACH\coach.db"),
    ("sqlite:///C:/Users/Jean Dupont/é à/coach.db", "C:/Users/Jean Dupont/é à/coach.db"),
])
def test_windows_and_posix_paths(raw, expected):
    assert sqlite_path(raw) == expected


def test_home_is_expanded_and_bad_urls_are_refused(monkeypatch):
    monkeypatch.setenv("HOME", "/home/u")
    assert sqlite_path("sqlite:///~/coach.db") == "/home/u/coach.db"
    for bad in ("sqlite:///", "sqlite:///:memory:", "sqlite://coach.db", "postgresql://x/y"):
        with pytest.raises(ValueError):
            sqlite_path(bad)


def test_windows_style_path_with_spaces_and_accents_really_opens(tmp_path):
    d = tmp_path / "Jean Dupont" / "é à" / "COACH"
    r = open_repo(url(d / "coach.db"))
    uid = r.create_user("x")
    r.close()
    assert open_repo(url(d / "coach.db")).user_exists(uid)


def test_parent_directory_is_created_and_file_is_private(tmp_path):
    p = tmp_path / "a" / "b" / "coach.db"
    r = open_repo(url(p))
    r.create_user("x")
    assert p.exists()
    if os.name == "posix":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
        for side in (Path(f"{p}-wal"), Path(f"{p}-shm")):
            if side.exists():
                assert stat.S_IMODE(side.stat().st_mode) & 0o077 == 0
    r.close()


def test_a_file_that_is_not_a_database_fails_clearly(tmp_path):
    p = tmp_path / "bad.db"
    p.write_bytes(b"ceci n'est pas une base SQLite" * 20)
    with pytest.raises(sqlite3.DatabaseError):
        open_repo(url(p))


# ---- pragmas ---------------------------------------------------------------------------------------------------------------------------------------


def test_pragmas(repo):
    c = repo._connection()
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []


def test_foreign_keys_and_cascade(repo):
    u = repo.create_account("A", "a@example.org", "h")
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_meal(u + 99, date(2026, 10, 1), "déjeuner", "x", None)  # utilisateur inexistant
    repo.add_facts(u, [Fact(key="k", value=1)])
    repo.add_meal(u, date(2026, 10, 1), "déjeuner", "x", None)
    repo.create_session(u, "t", datetime.now(UTC) + timedelta(days=1))
    repo.log_llm_call(u, "chat", "m", (1, 1), 0.1, True, None)
    with repo._tx() as c:
        c.execute("DELETE FROM users WHERE id = ?", (u,))
    c = repo._connection()
    assert all(c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] == 0 for t in ("facts", "meals", "sessions"))
    assert c.execute("SELECT user_id FROM llm_calls").fetchone()[0] is None  # ON DELETE SET NULL


def test_constraints_mirror_postgres(repo):
    u = repo.create_account("A", "a@example.org", "h")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_account("B", "a@example.org", "h")  # email unique
    with pytest.raises(sqlite3.IntegrityError):
        repo.set_language(u, "de")
    with pytest.raises(sqlite3.IntegrityError):
        repo.upsert_weight(u, date(2026, 1, 1), 5.0, None)
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_memory(u, "inconnu", (None, None), "x", {})
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_facts(u, [Fact(key="k", value=1, source="test")])


def test_ids_are_never_reused(repo):
    u = repo.create_user("a")
    m = repo.add_meal(u, date(2026, 10, 1), "dîner", "x", None)
    repo.delete_meal(u, m["id"])
    assert repo.add_meal(u, date(2026, 10, 1), "dîner", "y", None)["id"] > m["id"]


# ---- atomicité -------------------------------------------------------------------------------------------------------------------------------------


def test_a_failed_write_leaves_nothing_behind(repo):
    u = repo.create_user("a")
    with pytest.raises(sqlite3.IntegrityError):  # la 2e est refusée : la 1re ne doit pas rester
        repo.add_facts(u, [Fact(key="ok", value=1), Fact(key="ko", value=2, source="inconnue")])
    assert repo.list_facts(u) == []
    rows = [{"day": date(2026, 10, 1), "kind": "run", "title": "A", "duration_min": 30, "details": {}, "rules": [], "notes": []},
            {"day": date(2026, 10, 2), "kind": "run", "title": "B", "duration_min": 30, "details": {}, "rules": [], "notes": [], "status": "inconnu"}]
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_sessions(u, rows)
    assert repo.list_sessions(u, date(2026, 1, 1), None) == []
    assert repo._connection().in_transaction is False  # rien de laissé ouvert


def test_an_error_in_the_caller_rolls_back_the_transaction(repo):
    with pytest.raises(RuntimeError), repo._tx() as c:
        c.execute("INSERT INTO users (name, created_at) VALUES ('x', 'y')")
        raise RuntimeError
    assert repo._connection().execute("SELECT count(*) FROM users").fetchone()[0] == 0


# ---- persistance ------------------------------------------------------------------------------------------------------------------------------------


def test_data_survives_closing_and_reopening_the_file(tmp_path):
    p = tmp_path / "coach.db"
    r = open_repo(url(p))
    uid = r.create_account("Rudy", "r@example.org", "hash")
    r.add_facts(uid, [Fact(key="body.weight_kg", value=80.5), Fact(key="sports", value=["course", "force"])])
    r.add_sessions(uid, [{"day": date(2026, 10, 12), "kind": "run", "title": "Footing", "duration_min": 40, "details": {"z": [1, 2]}, "rules": ["C1"], "notes": []}])
    r.upsert_weight(uid, date(2026, 10, 12), 80.5, 90.0)
    r.close()
    r2 = open_repo(url(p))  # nouvelle ouverture = nouveau processus du point de vue des données
    assert r2.get_account("r@example.org")["id"] == uid
    assert {f.key: f.value for f in r2.list_facts(uid)} == {"body.weight_kg": 80.5, "sports": ["course", "force"]}
    s = r2.list_sessions(uid, date(2026, 10, 1), None)[0]
    assert s["details"] == {"z": [1, 2]} and s["day"] == date(2026, 10, 12) and s["created_at"].tzinfo is not None
    assert r2.list_weights(uid, date(2026, 10, 1))[0]["waist_cm"] == 90.0
    assert r2.create_user("suivant") > uid  # la séquence continue
    r2.close()


def test_data_written_in_another_process_is_visible(tmp_path):
    p = tmp_path / "coach.db"
    open_repo(url(p)).close()
    code = ("import sys; from app.repo import open_repo; r = open_repo(sys.argv[1]); print(r.create_account('P', 'p@example.org', 'h')); r.close()")
    out = subprocess.run([sys.executable, "-c", code, url(p)], cwd=ROOT, capture_output=True, text=True, check=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
    r = open_repo(url(p))
    assert r.get_account("p@example.org")["id"] == int(out.stdout.strip())


def test_the_app_restarts_on_the_same_file_and_keeps_the_account(tmp_path):
    from app.auth import reset_rate_limits

    p = tmp_path / "coach.db"
    reset_rate_limits()
    first = open_repo(url(p))
    app.dependency_overrides[get_repo] = lambda: first
    try:
        c = TestClient(app)
        uid = c.post("/auth/register", json={"name": "R", "email": "r@example.org", "password": PW}).json()["id"]
        assert c.post(f"/users/{uid}/answers", json={"question_id": "goal.sports", "value": ["running"]}).status_code in (200, 201)
        first.close()
        second = open_repo(url(p))  # « redémarrage »
        app.dependency_overrides[get_repo] = lambda: second
        c2 = TestClient(app)
        r = c2.post("/auth/login", json={"email": "r@example.org", "password": PW})
        assert r.status_code == 200 and r.json()["id"] == uid
        assert c.get("/auth/me").status_code == 200  # la session (cookie) a survécu au redémarrage
        assert second.list_facts(uid) and second.list_facts(uid)[0].value == ["running"]
        assert c.get("/version").json()["storage"] == "sqlite"
        second.close()
    finally:
        app.dependency_overrides.clear()


# ---- migrations ------------------------------------------------------------------------------------------------------------------------------------


def test_migrations_are_replayable_and_recorded(tmp_path):
    r = SqliteRepo(tmp_path / "c.db")
    r.migrate(MIGRATIONS)
    r.create_user("x")
    r.migrate(MIGRATIONS)
    r.migrate(MIGRATIONS)
    c = r._connection()
    versions = [v for (v,) in c.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert versions == [p.stem for p in sorted(MIGRATIONS.glob("*.sql"))] and len(versions) == len(set(versions))
    assert c.execute("SELECT count(*) FROM users").fetchone()[0] == 1  # un rejeu ne touche pas aux données
    r.close()


def test_new_migrations_apply_in_order_and_a_broken_one_rolls_back(tmp_path):
    d = tmp_path / "mig"
    d.mkdir()
    (d / "0001_a.sql").write_text("-- commentaire\nCREATE TABLE a (id INTEGER PRIMARY KEY);\nINSERT INTO a VALUES (1);\n", encoding="utf-8")
    r = SqliteRepo(tmp_path / "c.db")
    r.migrate(d)
    (d / "0002_b.sql").write_text("CREATE TABLE b (id INTEGER PRIMARY KEY);\nCREATE TABLE boom (;\n", encoding="utf-8")
    with pytest.raises(sqlite3.OperationalError):
        r.migrate(d)
    c = r._connection()
    assert c.execute("SELECT name FROM sqlite_master WHERE name = 'b'").fetchone() is None  # tout ou rien
    assert [v for (v,) in c.execute("SELECT version FROM schema_migrations")] == ["0001_a"]
    (d / "0002_b.sql").write_text("CREATE TABLE b (id INTEGER PRIMARY KEY);\n", encoding="utf-8")
    r.migrate(d)
    assert c.execute("SELECT count(*) FROM a").fetchone()[0] == 1  # 0001 non rejouée
    assert [v for (v,) in c.execute("SELECT version FROM schema_migrations ORDER BY version")] == ["0001_a", "0002_b"]


def test_no_migration_directory_content_is_an_error(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(RuntimeError):
        SqliteRepo(tmp_path / "c.db").migrate(tmp_path / "empty")


def test_unknown_versions_in_the_database_only_warn(tmp_path, caplog):
    r = SqliteRepo(tmp_path / "c.db")
    r.migrate(MIGRATIONS)
    with r._tx() as c:
        c.execute("INSERT INTO schema_migrations VALUES ('9999_future', 'x')")
    r.migrate(MIGRATIONS)
    assert "9999_future" in caplog.text


def test_concurrent_first_start_applies_each_migration_once(tmp_path):
    p = tmp_path / "c.db"
    errors = []

    def start():
        try:
            r = SqliteRepo(p)
            r.migrate(MIGRATIONS)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=start) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == []
    c = sqlite3.connect(p)
    assert c.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == len(list(MIGRATIONS.glob("*.sql")))


# ---- schéma équivalent à Postgres ------------------------------------------------------------------------------------------------------------------


def _pg_schema() -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    skip = {"UNIQUE", "PRIMARY", "FOREIGN", "CHECK", "CONSTRAINT"}
    for f in sorted((ROOT / "db" / "migrations").glob("*.sql")):
        sql = re.sub(r"--[^\n]*", "", f.read_text(encoding="utf-8"))
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", sql, re.S):
            cols = set()
            for line in m.group(2).splitlines():
                w = line.strip().split(" ")[0]
                if w and w.upper() not in skip and re.fullmatch(r"\w+", w):
                    cols.add(w)
            tables[m.group(1)] = cols
        for m in re.finditer(r"ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+)", sql):
            tables[m.group(1)].add(m.group(2))
    return tables


def test_sqlite_schema_has_the_same_tables_and_columns_as_postgres(repo):
    pg = _pg_schema()
    assert len(pg) >= 15
    c = repo._connection()
    lite = {t: {r[1] for r in c.execute(f"PRAGMA table_info({t})")} for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
    lite.pop("schema_migrations")
    lite.pop("sqlite_sequence", None)
    assert lite == pg


# ---- accès concurrents -----------------------------------------------------------------------------------------------------------------------------


def test_each_thread_gets_its_own_connection_and_dead_threads_are_cleaned(repo):
    seen = []

    def work():
        repo.create_user("t")
        seen.append(repo._connection())

    for _ in range(3):
        t = threading.Thread(target=work)
        t.start()
        t.join()
    assert len({id(c) for c in seen}) == 3 and repo._connection() not in seen
    repo.create_user("main")  # le prochain accès nettoie les connexions des threads terminés
    with pytest.raises(sqlite3.ProgrammingError):
        seen[0].execute("SELECT 1")  # fermée


def test_many_threads_writing_and_reading_lose_nothing(repo):
    users = [repo.create_user(f"u{i}") for i in range(8)]
    per, errors = 40, []

    def writer(uid):
        try:
            for i in range(per):
                repo.add_message(uid, "user", f"m{i}")
                repo.upsert_weight(uid, date(2026, 1, 1) + timedelta(days=i), 70 + i / 10, None)
                repo.add_facts(uid, [Fact(key="k", value=i)])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def reader():
        try:
            for _ in range(60):
                for uid in users:
                    assert len(repo.list_messages(uid, 1000)) <= per
                    repo.list_facts(uid)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=writer, args=(u,)) for u in users] + [threading.Thread(target=reader) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == []
    for uid in users:
        assert [m["body"] for m in repo.list_messages(uid, 1000)] == [f"m{i}" for i in range(per)]  # aucun message perdu, ordre conservé
        assert len(repo.list_weights(uid, date(2026, 1, 1))) == per
        facts = repo.list_facts(uid)
        assert len(facts) == per and facts[-1].value == per - 1


def test_concurrent_upserts_of_the_same_row_stay_consistent(repo):
    u = repo.create_user("u")

    def work(i):
        for _ in range(30):
            repo.upsert_weight(u, date(2026, 1, 1), 60 + i, None)
            repo.set_prefs(u, {"ntfy_topic": f"t{i}"})

    ts = [threading.Thread(target=work, args=(i,)) for i in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(repo.list_weights(u, date(2026, 1, 1))) == 1
    assert repo.get_prefs(u)["ntfy_topic"].startswith("t")


def test_two_processes_write_the_same_file_at_once(tmp_path):
    p = tmp_path / "coach.db"
    r = open_repo(url(p))
    uid = r.create_user("shared")
    code = ("import sys; from app.repo import open_repo; r = open_repo(sys.argv[1]); [r.add_message(int(sys.argv[2]), 'user', f'{sys.argv[3]}-{i}') for i in range(60)]")
    procs = [subprocess.Popen([sys.executable, "-c", code, url(p), str(uid), tag], cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, stderr=subprocess.PIPE) for tag in ("a", "b", "c")]
    for i in range(60):
        r.add_message(uid, "user", f"main-{i}")
    for pr in procs:
        assert pr.wait(60) == 0, pr.stderr.read().decode()
    bodies = [m["body"] for m in r.list_messages(uid, 1000)]
    assert len(bodies) == 240 and len(set(bodies)) == 240
    for tag in ("a", "b", "c", "main"):  # l'ordre propre à chaque écrivain est conservé
        mine = [b for b in bodies if b.startswith(tag)]
        assert mine == [f"{tag}-{i}" for i in range(60)]
    assert r._connection().execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_the_api_serves_parallel_requests_on_sqlite(tmp_path):
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = open_repo(url(tmp_path / "coach.db"))
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        c = TestClient(app)
        uid = c.post("/auth/register", json={"name": "R", "email": "r@example.org", "password": PW}).json()["id"]
        statuses = []

        def hit():
            for _ in range(5):
                statuses.append(c.get(f"/users/{uid}/goals").status_code)
                statuses.append(c.post(f"/users/{uid}/goals", json={"title": "g"}).status_code)

        ts = [threading.Thread(target=hit) for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert set(statuses) <= {200, 201} and len(repo.list_goals(uid, None)) == 15  # 3 fils x 5, sous la limite de 20 objectifs actifs
    finally:
        app.dependency_overrides.clear()
        repo.close()


def test_importer_and_main_use_the_same_factory():
    import inspect

    import app.exercises.importer as imp
    import app.main as main

    assert "open_repo" in inspect.getsource(imp.main) and "open_repo" in inspect.getsource(main.build_state)
    assert repo_pkg.open_repo is open_repo
