"""Demo instance with SYNTHETIC data, in memory (nothing is written anywhere). Used for screenshots and for trying the UI.

    .venv/bin/python scripts/demo_server.py            # http://127.0.0.1:8765  — login demo@example.org / demo-password-123

The persona below is invented. There is no LLM: coach and meal-estimate screens show their "not configured" state.
"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ.pop("DATABASE_URL", None)
os.environ.pop("DB_HOST", None)
os.environ["REGISTRATION"] = "open"
os.environ["LLM_PROVIDER"] = "none"
os.environ["COOKIE_SECURE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.exercises.sources import custom_exercises  # noqa: E402
from app.main import app  # noqa: E402
from app.questionnaire.models import Fact  # noqa: E402

EMAIL, PASSWORD = "demo@example.org", "demo-password-123"
FACTS = {
    "sports.practiced": ["running", "strength", "trail"], "goal.weight_direction": "perdre", "goal.physique_focus": ["haut du corps"],
    "constraints.training_days": 5, "constraints.weekday_session_max_min": 75, "constraints.weekend_session_max_min": 180,
    "multisport.blocked_days": ["vendredi"], "running.weekly_km_8w": 32, "running.best_10k_min": 49, "running.hr_max": 188,
    "strength.sessions_per_week": 3, "strength.level": "intermédiaire", "body.birth_year": 1992, "body.sex": "homme",
    "body.height_cm": 178, "body.weight_kg": 82, "history.recent_break": "non", "history.injuries": ["aucune"],
}


def seed() -> None:
    repo = app.state.repo
    c = TestClient(app, base_url="http://testserver")
    r = c.post("/auth/register", json={"name": "Alex", "email": EMAIL, "password": PASSWORD})
    uid = r.json()["id"]
    repo.add_facts(uid, [Fact(key=k, value=v, source="demo") for k, v in FACTS.items()])
    repo.replace_exercises(custom_exercises(Path(__file__).resolve().parent.parent / "data" / "custom_exercises.yaml"))
    c.post(f"/users/{uid}/goals", json={"title": "Trail 50 km", "kind": "event", "target_date": (date.today() + timedelta(days=120)).isoformat(),
                                        "priority": "principal", "details": {"distance_km": 50, "elevation_m": 2500}})
    c.post(f"/users/{uid}/plan/generate", json={"weeks": 4})
    plan = c.get(f"/users/{uid}/plan?weeks=1").json()
    sessions = [s for w in plan.get("weeks", []) for s in w.get("sessions", [])] if isinstance(plan, dict) and "weeks" in plan else plan.get("sessions", [])
    if sessions:
        c.patch(f"/users/{uid}/plan/sessions/{sessions[0]['id']}", json={"status": "done", "logged": {"rpe": 6, "minutes": sessions[0].get("duration_min"), "note": "Bonnes sensations."}})
    for i in range(6, 0, -1):
        c.post(f"/users/{uid}/nutrition/weight", json={"day": (date.today() - timedelta(days=7 * i)).isoformat(), "kg": round(82.4 - 0.25 * (6 - i), 1)})
    for slot, text in (("petit-déjeuner", "Flocons d'avoine, banane, yaourt grec"), ("déjeuner", "Poulet, riz, brocolis"), ("collation", "Pomme et amandes")):
        c.post(f"/users/{uid}/nutrition/meals", json={"slot": slot, "description": text, "estimate": False})


if __name__ == "__main__":
    seed()
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("DEMO_PORT", "8765")), log_level="warning")
