"""Contrat du stockage : mêmes comportements et mêmes types Python rendus par MemoryRepo et SqliteRepo (Postgres : tests/test_postgres.py)."""
import inspect
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.exercises.models import Exercise, Media
from app.questionnaire.models import Fact, current_facts
from app.repo import SqliteRepo
from app.repo.protocol import Repo

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        # `MemoryRepo` peut être remplacé par SQLite quand toute la suite est rejouée (COACH_TEST_REPO=sqlite) : on veut ici la vraie classe mémoire.
        import app.repo.memory as m

        yield m.MemoryRepo()
        return
    r = SqliteRepo(tmp_path / "c.db")
    r.migrate(ROOT / "db" / "sqlite")
    yield r
    r.close()


def sess(day, kind="run_easy", title="Footing", **kw):
    return {"day": day, "kind": kind, "title": title, "duration_min": 30, "details": {"zone": "z2"}, "rules": ["C1"], "notes": ["n"], **kw}


def test_every_protocol_method_is_implemented_with_the_same_parameters():
    for name, fn in inspect.getmembers(Repo, inspect.isfunction):
        if name.startswith("__"):
            continue
        got = getattr(SqliteRepo, name, None)
        assert got is not None, f"SqliteRepo.{name} manquante"
        assert list(inspect.signature(got).parameters) == list(inspect.signature(fn).parameters), name
    assert SqliteRepo.name == "sqlite"


def test_facts_supersede_and_keep_json_types(repo):
    uid = repo.create_user("a")
    assert repo.user_exists(uid) and not repo.user_exists(uid + 5)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    repo.add_facts(uid, [Fact(key="k", value=1, observed_at=t0), Fact(key="n", value=None), Fact(key="l", value=["a", {"é": 1.5}])])
    repo.add_facts(uid, [Fact(key="k", value=2, observed_at=t0 + timedelta(days=1), source="manual", confidence=0.5)])
    facts = repo.list_facts(uid)
    cur = current_facts(facts)
    assert cur["k"] == 2 and cur["n"] is None and cur["l"] == ["a", {"é": 1.5}]
    assert all(f.observed_at.tzinfo is not None for f in facts)
    newest_k = [f for f in facts if f.key == "k"][-1]
    assert newest_k.value == 2 and newest_k.confidence == 0.5 and newest_k.source == "manual"


def test_accounts_sessions_language_and_legacy(repo):
    legacy = repo.create_user("ancien")
    repo.add_facts(legacy, [Fact(key="k", value=1)])
    assert repo.list_legacy_users() == [{"id": legacy, "name": "ancien", "answers": 1}]
    assert not repo.has_accounts()
    uid = repo.create_account("R", "r@example.org", "h")
    assert repo.has_accounts() and repo.get_account("r@example.org") == {"id": uid, "name": "R", "password_hash": "h", "lang": None}
    assert repo.get_account("absent@example.org") is None
    assert repo.adopt_legacy_user(legacy, "L", "l@example.org", "h2") and not repo.adopt_legacy_user(legacy, "L", "x@example.org", "h2")
    assert repo.list_legacy_users() == []
    assert repo.get_language(uid) is None
    repo.set_language(uid, "en")
    assert repo.get_language(uid) == "en" and repo.get_account("r@example.org")["lang"] == "en"
    future, past = datetime.now(UTC) + timedelta(days=1), datetime.now(UTC) - timedelta(days=1)
    repo.create_session(uid, "t1", future)
    repo.create_session(uid, "t2", future)
    repo.create_session(uid, "old", past)
    assert repo.get_session_user("t1") == {"id": uid, "name": "R", "email": "r@example.org", "lang": "en"}
    assert repo.get_session_user("old") is None
    repo.set_password(uid, "h3", "t1")  # garde la session courante, ferme les autres
    assert repo.get_session_user("t1") and repo.get_session_user("t2") is None
    assert repo.get_account("r@example.org")["password_hash"] == "h3"
    repo.delete_session("t1")
    assert repo.get_session_user("t1") is None


def test_exercises_upsert_search_and_media(repo):
    def ex(n, sid, **kw):
        return Exercise(source="t", source_id=sid, sources=["t"], name=n, name_en=kw.pop("name_en", None), license="L", **kw)
    repo.replace_exercises([ex("Squat", "1", name_en="Back squat", muscles_primary=["quadriceps"], equipment=["barbell"], kind="strength",
                               media=[Media(kind="image", url="https://e/a.webp", is_main=True, license="CC", author="a"), Media(kind="video", url="https://e/b.mp4", license="CC")]),
                            ex("Écrasement", "2", muscles_secondary=["triceps"]), ex("Pompes", "3", muscles_primary=["chest"], equipment=["none"])])
    rows, total = repo.search_exercises(None, None, None, None, 10, 0)
    assert total == 3 and rows[0].name == "Squat"  # avec image d'abord
    assert [e.name for e in repo.search_exercises("ÉCRAS", None, None, None, 10, 0)[0]] == ["Écrasement"]  # casse Unicode
    assert [e.name for e in repo.search_exercises("back", None, None, None, 10, 0)[0]] == ["Squat"]  # nom anglais
    assert [e.name for e in repo.search_exercises("%", None, None, None, 10, 0)[0]] == []  # pas de caractère générique
    assert [e.name for e in repo.search_exercises(None, "triceps", None, None, 10, 0)[0]] == ["Écrasement"]
    assert [e.name for e in repo.search_exercises(None, None, "barbell", "strength", 10, 0)[0]] == ["Squat"]
    assert repo.search_exercises(None, None, None, None, 1, 1)[1] == 3
    got = repo.get_exercise(rows[0].id)
    assert got.muscles_primary == ["quadriceps"] and [m.kind for m in got.media] == ["image", "video"] and got.media[0].is_main is True
    assert repo.get_media(got.media[1].id).url == "https://e/b.mp4" and repo.get_media(9999) is None and repo.get_exercise(9999) is None
    repo.replace_exercises([ex("Squat v2", "1", media=[])])  # même clé : mise à jour, médias remplacés
    again = repo.search_exercises("v2", None, None, None, 10, 0)[0]
    assert len(again) == 1 and again[0].media == []


def test_meals_and_weights(repo):
    u = repo.create_user("m")
    d = date(2026, 10, 5)
    m = repo.add_meal(u, d, "déjeuner", "pâtes", None)
    assert m["day"] == d and m["analysis"] is None and m["created_at"].tzinfo is not None
    repo.set_meal_analysis(u, m["id"], {"kcal": 700, "items": ["a"]})
    assert repo.get_meal(u, m["id"])["analysis"] == {"kcal": 700, "items": ["a"]}
    assert repo.get_meal(u + 1, m["id"]) is None
    assert [x["id"] for x in repo.list_meals(u, d, d)] == [m["id"]] and repo.list_meals(u, d + timedelta(days=1), d + timedelta(days=2)) == []
    assert repo.delete_meal(u + 1, m["id"]) is None
    assert repo.delete_meal(u, m["id"]) == "" and repo.delete_meal(u, m["id"]) is None
    repo.upsert_weight(u, d, 80.5, None)
    repo.upsert_weight(u, d, 80.0, 90.5)
    repo.upsert_weight(u, d + timedelta(days=1), 79.5, None)
    ws = repo.list_weights(u, d)
    assert [(w["day"], w["kg"], w["waist_cm"]) for w in ws] == [(d, 80.0, 90.5), (d + timedelta(days=1), 79.5, None)]
    assert repo.list_weights(u, d + timedelta(days=1))[0]["kg"] == 79.5


def test_goals_lifecycle(repo):
    u = repo.create_user("g")
    a = repo.create_goal(u, {"title": "Trail", "kind": "event", "target_date": date(2027, 6, 12), "priority": "principal", "success": "finir", "details": {"km": 50}})
    b = repo.create_goal(u, {"title": "Sans date", "kind": "habit", "target_date": None, "priority": "important", "success": None, "details": {}})
    assert a["status"] == "active" and a["target_date"] == date(2027, 6, 12) and a["details"] == {"km": 50} and a["created_at"].tzinfo is not None
    assert [g["id"] for g in repo.list_goals(u, None)] == [a["id"], b["id"]]  # sans date en dernier
    upd = repo.update_goal(u, a["id"], {"status": "done", "title": None, "success": "ok", "details": {"km": 60}})
    assert upd["status"] == "done" and upd["title"] == "Trail" and upd["success"] == "ok" and upd["details"] == {"km": 60}
    assert [g["id"] for g in repo.list_goals(u, "done")] == [a["id"]]
    assert repo.update_goal(u, a["id"], {"target_date": None})["target_date"] is None  # target_date peut être vidé
    assert repo.update_goal(u + 1, a["id"], {"title": "x"}) is None and repo.update_goal(u, 999, {"title": "x"}) is None
    assert repo.delete_goal(u + 1, b["id"]) is False and repo.delete_goal(u, b["id"]) is True and repo.delete_goal(u, b["id"]) is False


def test_planned_sessions(repo):
    u = repo.create_user("p")
    d = date(2026, 10, 12)
    repo.add_sessions(u, [sess(d), sess(d + timedelta(days=2), "run_long", "Sortie")])
    rows = repo.list_sessions(u, d, None)
    assert [r["title"] for r in rows] == ["Footing", "Sortie"] and rows[0]["status"] == "planned" and rows[0]["logged"] is None
    assert rows[0]["details"] == {"zone": "z2"} and rows[0]["rules"] == ["C1"] and rows[0]["notes"] == ["n"]
    assert [r["title"] for r in repo.list_sessions(u, d, d + timedelta(days=2))] == ["Footing"]  # fin exclue
    sid = rows[0]["id"]
    done = repo.update_session(u, sid, "done", {"minutes": 28})
    assert done["status"] == "done" and done["logged"] == {"minutes": 28}
    assert repo.update_session(u, sid, "skipped", None)["logged"] == {"minutes": 28}  # logged conservé
    assert repo.update_session(u + 1, sid, "done", None) is None
    sid2 = rows[1]["id"]
    assert repo.move_session(u, sid2, d + timedelta(days=2))["details"] == {"zone": "z2"}
    mv = repo.move_session(u, sid2, d + timedelta(days=4))
    assert mv["day"] == d + timedelta(days=4) and mv["details"]["moved_from"] == (d + timedelta(days=2)).isoformat()
    assert repo.move_session(u, sid2, d + timedelta(days=5))["details"]["moved_from"] == (d + timedelta(days=2)).isoformat()
    assert repo.move_session(u + 1, sid2, d) is None
    p = repo.patch_planned(u, sid2, {"duration_min": 45, "notes": ["x", "y"], "details": {"a": 1}, "ignored": 1})
    assert p["duration_min"] == 45 and p["notes"] == ["x", "y"] and p["details"] == {"a": 1}
    assert repo.patch_planned(u, sid, {"duration_min": 1}) is None  # plus « planned »
    man = repo.add_session(u, sess(d, status="done", logged={"source": "manual"}))
    assert man["status"] == "done" and man["logged"] == {"source": "manual"}
    repo.delete_planned_from(u, d)  # seules les séances encore « planned » partent
    assert sorted(r["id"] for r in repo.list_sessions(u, d, None)) == sorted([sid, man["id"]])
    assert repo.remove_session(u + 1, man["id"]) is False and repo.remove_session(u, man["id"]) is True


def activity(**kw):
    return {"garmin_id": "1", "day": date(2026, 10, 1), "started_at": datetime(2026, 10, 1, 7, 0), "sport": "run", "type_key": "running", "name": "Sortie",
            "duration_s": 3000, "distance_m": 9000.0, "elevation_m": 50.0, "avg_hr": 150, "max_hr": 170, "calories": 500, "training_load": 80.0, **kw}


def test_garmin_activities_streams_and_metrics(repo):
    u = repo.create_user("w")
    assert repo.get_garmin(u) is None
    repo.save_garmin(u, "g@x.fr", "enc")
    repo.touch_garmin(u, "enc2", None)
    a = repo.get_garmin(u)
    assert a["tokens_enc"] == "enc2" and a["last_sync_at"] is not None and a["backfilled_at"] is None and repo.list_garmin_users() == [u]
    repo.mark_backfilled(u)
    assert repo.get_garmin(u)["backfilled_at"].tzinfo is not None
    repo.touch_garmin(u, None, "expiré")
    assert repo.get_garmin(u)["last_error"] == "expiré" and repo.get_garmin(u)["tokens_enc"] == "enc2"
    assert repo.upsert_activities(u, [activity(), activity(garmin_id="2", day=date(2026, 9, 1), started_at=datetime(2026, 9, 1, 8, 0))]) == 2
    assert repo.upsert_activities(u, [activity(distance_m=9100.0)]) == 0
    acts = repo.list_activities(u, date(2026, 9, 1), 10)
    assert [x["garmin_id"] for x in acts] == ["1", "2"] and acts[0]["distance_m"] == 9100.0 and acts[0]["started_at"] == datetime(2026, 10, 1, 7, 0)
    assert acts[0]["day"] == date(2026, 10, 1) and acts[0]["source"] == "garmin" and len(repo.list_activities(u, date(2026, 9, 1), 1)) == 1
    imp = activity(garmin_id="fit:abc")
    imp["source"] = "fit"
    repo.upsert_activities(u, [imp])
    streams = {"n": 3, "duration_s": 2, "t": [0, 1, 2], "dist": [0.0, 3.5, 7.0], "hr": [140, None, 142], "speed": None, "alt": [10.5, 10.5, 11.0], "cad": None, "power": None,
               "splits": {"km": [{"i": 1, "dur_s": 300}], "laps": []}}
    assert repo.save_streams(u, "1", streams) is True and repo.save_streams(u, "inconnue", streams) is False
    assert repo.get_streams(u, "1") == streams
    assert repo.save_streams(u, "1", {**streams, "hr": [150, 151, 152]}) and repo.get_streams(u, "1")["hr"] == [150, 151, 152]
    assert repo.get_streams(u, "2") is None
    rows = [{"day": date(2026, 10, 1), "metric": "rhr", "value": 50.0, "text": None}, {"day": date(2026, 10, 2), "metric": "rhr", "value": 51.0},
            {"day": date(2026, 10, 1), "metric": "status", "value": None, "text": "productive"}]
    assert repo.upsert_metrics(u, rows) == 3
    repo.upsert_metrics(u, [{"day": date(2026, 10, 1), "metric": "rhr", "value": 49.0, "text": None}])
    ms = repo.list_metrics(u, None, date(2026, 10, 1))
    assert [(m["metric"], m["day"], m["value"], m["text"]) for m in ms] == [("rhr", date(2026, 10, 1), 49.0, None), ("rhr", date(2026, 10, 2), 51.0, None),
                                                                           ("status", date(2026, 10, 1), None, "productive")]
    assert len(repo.list_metrics(u, "rhr", date(2026, 10, 1), date(2026, 10, 1))) == 1
    repo.prune_activities(u, date(2026, 9, 15))  # supprime « 2 » (sept.), garde le reste
    assert {x["garmin_id"] for x in repo.list_activities(u, date(2026, 1, 1), 10)} == {"1", "fit:abc"} and repo.get_streams(u, "1") is not None
    repo.prune_activities(u, date(2026, 12, 1))
    assert repo.get_streams(u, "1") is None and repo.list_metrics(u, None, date(2026, 1, 1)) == []
    repo.upsert_activities(u, [activity(), imp])
    repo.upsert_metrics(u, rows)
    repo.delete_garmin(u, True)  # les fichiers importés restent
    assert repo.get_garmin(u) is None and [x["garmin_id"] for x in repo.list_activities(u, date(2026, 1, 1), 10)] == ["fit:abc"]
    assert repo.list_metrics(u, None, date(2026, 1, 1)) == []


def test_coach_memory_llm_calls_chat_and_notifications(repo):
    u, v = repo.create_user("c"), repo.create_user("d")
    m = repo.add_memory(u, "advice", (date(2026, 10, 1), None), "texte", {"a": [1, 2]})
    assert m["period_start"] == date(2026, 10, 1) and m["period_end"] is None and m["data"] == {"a": [1, 2]} and m["created_at"].tzinfo is not None
    m2 = repo.add_memory(u, "decision", (None, None), "t2", {})
    assert [x["id"] for x in repo.list_memory(u, None, 10)] == [m2["id"], m["id"]] and [x["id"] for x in repo.list_memory(u, "advice", 10)] == [m["id"]]
    repo.update_memory_data(u, m["id"], {"b": 1})
    assert repo.get_memory(u, m["id"])["data"] == {"b": 1} and repo.get_memory(v, m["id"]) is None
    now = datetime.now(UTC)
    repo.log_llm_call(u, "chat", "m", (10, 5), 0.5, True, None)
    repo.log_llm_call(v, "chat", "m", (10, 5), 0.25, True, None)
    repo.log_llm_call(v, "meal", "m", (1, 1), 0.1, False, "boom")
    repo.log_llm_call(None, "chat", "m", (1, 1), 0.05, True, None)
    assert repo.llm_spend_month(now.date().replace(day=1)) == pytest.approx(0.9)
    assert repo.llm_spend_month(now.date() + timedelta(days=1)) == 0
    assert repo.llm_calls_since(v, "chat", now - timedelta(hours=1)) == 1 and repo.llm_calls_since(v, "chat", now + timedelta(hours=1)) == 0
    usage = {(r["kind"], r["mine"]): r for r in repo.llm_usage_since(now - timedelta(hours=1), u)}
    assert usage[("chat", True)]["calls"] == 1 and usage[("chat", True)]["cost"] == pytest.approx(0.5)
    assert usage[("chat", False)]["calls"] == 2 and ("meal", False) not in usage  # échec non compté
    a = repo.add_message(u, "user", "salut", {"x": 1})
    repo.add_message(u, "assistant", "yo")
    repo.add_message(v, "user", "autre")
    assert a["meta"] == {"x": 1} and [x["body"] for x in repo.list_messages(u, 10)] == ["salut", "yo"] and [x["body"] for x in repo.list_messages(u, 1)] == ["yo"]
    d = repo.get_prefs(u)
    assert d["push_enabled"] is False and d["ntfy_topic"] is None and repo.list_notify_users() == []
    p = repo.set_prefs(u, {"ntfy_topic": "t", "push_enabled": True})
    assert p["push_enabled"] is True and p["email_enabled"] is False and p["ntfy_topic"] == "t"
    assert repo.set_prefs(u, {"email": "a@b.fr"})["ntfy_topic"] == "t" and repo.list_notify_users() == [u]
    assert repo.last_notify(u) is None
    repo.add_notify_log(u, "digest", "ntfy", "t", "b", False, "err")
    assert repo.last_notify(u) is None and repo.last_notify(u, ok_only=False).tzinfo is not None
    repo.add_notify_log(u, "digest", "ntfy", "t", "b", True, None)
    assert repo.last_notify(u, "digest") is not None and repo.last_notify(u, "autre") is None
    repo.add_subscription(u, "https://p/1", "k", "a")
    repo.add_subscription(v, "https://p/1", "k2", "a2")  # même endpoint : repris par le dernier
    repo.add_subscription(u, "https://p/2", "k", "a")
    assert [s["endpoint"] for s in repo.list_subscriptions(u)] == ["https://p/2"] and [s["p256dh"] for s in repo.list_subscriptions(v)] == ["k2"]
    repo.delete_subscription(u, "https://p/1")  # pas à lui : sans effet
    assert len(repo.list_subscriptions(v)) == 1
    repo.delete_subscription(v, "https://p/1")
    assert repo.list_subscriptions(v) == []
