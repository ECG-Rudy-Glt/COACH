"""Code-barres d'un produit emballé : valeurs nutritionnelles d'Open Food Facts (pour 100 g) × quantité mangée.

Seul le code-barres quitte le serveur (aucune donnée personnelle, aucun cookie), avec un délai court et un agent explicite.
Désactivable pour l'auto-hébergement : OFF_ENABLED=0. Adresse remplaçable (miroir) : OFF_BASE_URL."""
import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.config import VERSION, env

TIMEOUT_S = 6
MAX_BYTES = 1_000_000
MAX_GRAMS = 5000
USER_AGENT = f"COACH-selfhosted/{VERSION} (+https://github.com/ECG-Rudy-Glt/COACH)"
FIELDS = "product_name,brands,nutriments,serving_quantity,quantity"


class BarcodeError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def enabled() -> bool:
    return env("OFF_ENABLED", "1").lower() not in ("0", "false", "no", "off", "non")


def base_url() -> str:
    url = env("OFF_BASE_URL", "https://world.openfoodfacts.org").rstrip("/")
    if not url.startswith(("https://", "http://")):
        raise BarcodeError("Adresse Open Food Facts invalide.", 503)
    return url


def valid_code(code: str) -> bool:
    """EAN-8, UPC-A, EAN-13 ou GTIN-14 avec une clé de contrôle correcte (attrape les fautes de frappe avant toute requête)."""
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", code):
        return False
    digits = [int(c) for c in code]
    s = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return (10 - s % 10) % 10 == digits[-1]


def _get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})  # noqa: S310 : schéma http(s) vérifié par base_url()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310
            data = json.loads(r.read(MAX_BYTES + 1)[:MAX_BYTES])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": 0}
        raise BarcodeError(f"Open Food Facts a répondu {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise BarcodeError("Open Food Facts est injoignable.") from e
    if not isinstance(data, dict):
        raise BarcodeError("Réponse Open Food Facts illisible.")
    return data


def _num(v: Any, hi: float) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if 0 <= x <= hi else None


def parse_product(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Produit normalisé (valeurs pour 100 g) ou None s'il est inconnu ou sans énergie renseignée."""
    p = payload.get("product")
    if payload.get("status") != 1 or not isinstance(p, dict):
        return None
    n = p.get("nutriments") if isinstance(p.get("nutriments"), dict) else {}
    kcal = _num(n.get("energy-kcal_100g"), 900)
    if kcal is None:
        kj = _num(n.get("energy_100g"), 3800)
        kcal = kj / 4.184 if kj is not None else None
    if kcal is None:
        return None
    name = " ".join(str(p.get("product_name") or "").split())[:80] or "Produit emballé"
    brand = str(p.get("brands") or "").split(",")[0].strip()[:40]
    serving = _num(p.get("serving_quantity"), MAX_GRAMS)
    return {"name": name, "brand": brand, "kcal_100g": round(kcal, 1), "protein_100g": round(_num(n.get("proteins_100g"), 100) or 0, 1),
            "carbs_100g": round(_num(n.get("carbohydrates_100g"), 100) or 0, 1), "fat_100g": round(_num(n.get("fat_100g"), 100) or 0, 1),
            "serving_g": round(serving) if serving else None}


def lookup(code: str) -> dict[str, Any]:
    if not enabled():
        raise BarcodeError("La recherche par code-barres est désactivée sur ce serveur.", 503)
    if not valid_code(code):
        raise BarcodeError("Code-barres invalide : vérifiez les chiffres (8, 12, 13 ou 14).", 422)
    product = parse_product(_get_json(f"{base_url()}/api/v2/product/{code}.json?fields={FIELDS}"))
    if not product:
        raise BarcodeError("Produit introuvable ou sans valeurs nutritionnelles : décrivez-le plutôt.", 404)
    return {"code": code, **product}


def analysis_for(product: dict[str, Any], grams: float) -> dict[str, Any]:
    """Analyse au format des repas : valeurs de l'emballage × quantité, sans fourchette large (donnée déclarée, pas devinée)."""
    k = grams / 100
    kcal = round(product["kcal_100g"] * k)
    return {"estimated": False, "source": "openfoodfacts", "kcal_min": round(kcal * 0.95), "kcal_max": round(kcal * 1.05), "kcal": kcal,
            "protein_g": round(product["protein_100g"] * k), "carbs_g": round(product["carbs_100g"] * k), "fat_g": round(product["fat_100g"] * k),
            "confidence": "élevée", "assumptions": "Valeurs de l'emballage pour 100 g × la quantité saisie.", "feedback": "", "tips": [],
            "items": [{"name": product["name"], "quantity": f"{grams:g} g", "kcal": kcal, "protein_g": round(product["protein_100g"] * k),
                       "carbs_g": round(product["carbs_100g"] * k), "fat_g": round(product["fat_100g"] * k)}], "note": None}
