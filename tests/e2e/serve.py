"""Serveur d'essai des tests de parcours : MemoryRepo, données de démo synthétiques, faux LLM déterministe, aucun réseau externe.

    python tests/e2e/serve.py [port]
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import demo_server  # noqa: E402  (pose l'environnement : mémoire, inscription ouverte, cookie non sécurisé)

os.environ["OFF_ENABLED"] = "0"  # aucun appel à Open Food Facts
os.environ["AUTO_NOTIFY"] = "0"

import uvicorn  # noqa: E402

from app.coach.llm import LLMResult  # noqa: E402
from app.main import app  # noqa: E402

ESTIMATE = {
    "items": [{"name": "Poulet, riz", "quantity": "1 assiette", "kcal": 640, "protein_g": 45, "carbs_g": 70, "fat_g": 18}],
    "totals": {"kcal_min": 600, "kcal_max": 700, "protein_g": 45, "carbs_g": 70, "fat_g": 18},
    "confidence": "élevée", "assumptions": "Portion standard.", "feedback": "Repas équilibré.", "tips": [], "questions": [],
}


class FakeLLM:
    """Répond toujours la même estimation de repas : pas de réseau, pas de clé."""

    def configured(self) -> bool:
        return True

    def complete(self, system, user, max_tokens, model=None, history=None, image=None, json_mode=False) -> LLMResult:
        return LLMResult(json.dumps(ESTIMATE, ensure_ascii=False), 10, 10, "fake-model")


if __name__ == "__main__":
    demo_server.seed()
    app.state.llm = FakeLLM()
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8766, log_level="warning")
