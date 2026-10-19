
import pytest
import yaml
from fastapi.testclient import TestClient

from app import evidence as ev
from app.coach import service
from app.main import app, get_repo
from app.repo import MemoryRepo

RULES = {"G1", "M8", "N2"}
GOOD = {"id": "STR-001", "topic": "hypertrophy", "citation": "Auteur (2017). Titre. Revue.", "year": 2017, "doi": None, "pmid": None,
        "url": "https://pubmed.ncbi.nlm.nih.gov/1/", "design": "méta-analyse", "finding_fr": "Un constat.", "limits_fr": "Une limite.",
        "applies_to": ["M8"], "confidence": "élevée", "verified_on": "2026-10-18"}


def test_validation_rejects_bad_entries():
    assert ev.validate_entry(GOOD, RULES) is None
    for bad in ({**GOOD, "id": "x1"}, {**GOOD, "url": "http://x"}, {**GOOD, "topic": "magie"}, {**GOOD, "applies_to": ["Z9"]},
                {**GOOD, "year": 1800}, {**GOOD, "finding_fr": "x" * 500}, {k: v for k, v in GOOD.items() if k != "limits_fr"}):
        assert ev.validate_entry(bad, RULES) is not None


def test_loader_skips_duplicates_and_invalid(tmp_path):
    (tmp_path / "a.yaml").write_text(yaml.safe_dump([GOOD, {**GOOD, "id": "STR-002", "confidence": "faible"}, {**GOOD, "id": "bad"}, GOOD]), encoding="utf-8")
    items = ev.load_evidence(tmp_path, RULES)
    assert [e["id"] for e in items] == ["STR-001", "STR-002"] and ev.load_evidence(tmp_path / "absent", RULES) == []
    assert "STR-001" in ev.digest(items) and "élevée" in ev.digest(items)["STR-001"]


def test_committed_evidence_files_are_all_valid():
    """Chaque publication versionnée doit passer la validation : aucune n'est ignorée silencieusement."""
    rules = set(yaml.safe_load((service.ROOT / "data" / "rules_digest.yaml").read_text(encoding="utf-8")))
    d = service.ROOT / "data" / "evidence"
    for path in sorted(d.glob("*.yaml")) if d.exists() else []:
        for e in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            assert ev.validate_entry(e, rules) is None, (path.name, e.get("id"), ev.validate_entry(e, rules))


@pytest.fixture
def api():
    from app.auth import reset_rate_limits

    reset_rate_limits()
    repo = MemoryRepo()
    app.dependency_overrides[get_repo] = lambda: repo
    old = app.state.evidence
    app.state.evidence = [GOOD, {**GOOD, "id": "NUT-001", "topic": "nutrition", "citation": "Autre (2018). Protéines. Revue."}]
    c = TestClient(app)
    assert c.get("/evidence").status_code == 401
    c.post("/auth/register", json={"name": "R", "email": "ev@example.org", "password": "un-mot-de-passe-solide"})
    yield c
    app.state.evidence = old
    app.dependency_overrides.clear()


def test_evidence_api_filters(api):
    r = api.get("/evidence").json()
    assert r["total"] == 2 and r["topics"]["nutrition"]["count"] == 1
    assert [e["id"] for e in api.get("/evidence?topic=nutrition").json()["items"]] == ["NUT-001"]
    assert [e["id"] for e in api.get("/evidence?q=protéines").json()["items"]] == ["NUT-001"]
    assert api.get("/evidence/STR-001").json()["citation"].startswith("Auteur") and api.get("/evidence/ZZZ-999").status_code == 404


def test_coach_only_cites_known_sources():
    from datetime import date, timedelta

    repo = MemoryRepo()
    uid = repo.create_user("x")
    repo.add_sessions(uid, [{"day": date.today() + timedelta(days=2), "kind": "run_long", "title": "L", "duration_min": 60, "details": {}, "rules": ["C2"], "notes": []}])
    sid = repo.list_sessions(uid, date.today(), None)[0]["id"]
    service.set_evidence({"STR-001": "x"}, {"STR-001"})
    base = {"session_id": sid, "action": "reduce", "factor": 0.8, "reason": "Fatigue", "rule_ids": ["G1"]}
    ok, why = service.check_proposal(repo, uid, {**base, "source_ids": ["STR-001"]}, date.today())
    assert ok and ok["source_ids"] == ["STR-001"]
    bad, why = service.check_proposal(repo, uid, {**base, "source_ids": ["INV-123"]}, date.today())
    assert bad is None and "publication" in why
    service.set_evidence({}, set())


def test_coach_receives_every_publication_and_is_told_to_rely_on_them():
    items = [{**GOOD, "id": f"STR-{i:03d}"} for i in range(1, 61)]
    assert len(ev.digest(items)) == 60  # aucune publication n'est tronquée
    assert "N'invente jamais d'étude" in service.SOURCES_RULE and "sources" in service.SOURCES_RULE


def test_server_links_sources_to_the_rules_a_proposal_cites():
    from datetime import date, timedelta

    repo = MemoryRepo()
    uid = repo.create_user("x")
    repo.add_sessions(uid, [{"day": date.today() + timedelta(days=2), "kind": "run_long", "title": "L", "duration_min": 60, "details": {}, "rules": ["C2"], "notes": []}])
    sid = repo.list_sessions(uid, date.today(), None)[0]["id"]
    service.set_evidence({"RUN-001": "x", "RUN-002": "y"}, {"RUN-001", "RUN-002"}, {"G1": ["RUN-001", "RUN-002"]})
    ok, _ = service.check_proposal(repo, uid, {"session_id": sid, "action": "reduce", "factor": 0.8, "reason": "Fatigue", "rule_ids": ["G1"]}, date.today())
    assert ok["source_ids"] == ["RUN-001", "RUN-002"]  # citées sans que le modèle les ait nommées
    service.set_evidence({}, set())
