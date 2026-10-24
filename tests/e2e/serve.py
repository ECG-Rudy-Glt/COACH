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

os.environ["OFF_ENABLED"] = "1"  # la recherche par code-barres est simulée plus bas : aucun appel réseau
os.environ["AUTO_NOTIFY"] = "0"

import uvicorn  # noqa: E402

from app.coach.llm import LLMResult  # noqa: E402
from app.main import app  # noqa: E402
from app.weather import client as weather_client  # noqa: E402


def fake_open_meteo(url):
    """Faux Open-Meteo : une ville (Lyon) et des rafales de 70 km/h tous les jours, donc toute séance en extérieur est « déconseillée »."""
    if "geocoding" in url:
        return {"results": [{"name": "Lyon", "admin1": "Auvergne-Rhône-Alpes", "country": "France", "latitude": 45.74846, "longitude": 4.84671}]}
    from datetime import date, timedelta
    days = [(date.today() + timedelta(days=d)).isoformat() for d in range(7)]
    times = [f"{d}T{h:02d}:00" for d in days for h in range(24)]
    n = len(times)
    return {"hourly": {"time": times, "temperature_2m": [14] * n, "apparent_temperature": [14] * n, "precipitation_probability": [5] * n, "precipitation": [0.0] * n,
                       "wind_gusts_10m": [70] * n, "weather_code": [1] * n}}


weather_client._get_json = fake_open_meteo  # aucun appel réseau réel

from app.nutrition import barcode as nut_barcode  # noqa: E402

PRODUCT = {"status": 1, "product": {"product_name": "Biscuit d'essai", "brands": "Marque d'essai", "quantity": "300 g", "serving_quantity": "30", "nutriscore_grade": "c", "ecoscore_grade": "b",
                                    "nutriments": {"energy-kcal_100g": 480, "proteins_100g": 6, "carbohydrates_100g": 70, "fat_100g": 18},
                                    "image_front_small_url": "https://images.openfoodfacts.org/images/products/essai.200.jpg"}}
PIXEL = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")
nut_barcode._get_json = lambda url: PRODUCT if "/3017620422003.json" in url else {"status": 0}  # un seul produit connu
nut_barcode.fetch_image = lambda code: (PIXEL, "image/png")  # image relayée : un pixel

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
