"""Base de publications scientifiques vérifiées (data/evidence/*.yaml) : consultable dans l'app et citée par le coach par identifiant."""
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request

log = logging.getLogger("sport-coach.evidence")
ID_RE = re.compile(r"^[A-Z]{3}-\d{3}$")
DESIGNS = {"méta-analyse", "essai contrôlé randomisé", "revue systématique", "revue narrative", "position stand", "étude observationnelle", "étude croisée", "revue exploratoire"}
CONFIDENCE = {"élevée": 0, "moyenne": 1, "faible": 2}
TOPICS = {"running": "Course à pied", "trail": "Trail", "cycling": "Vélo", "hybrid": "Hyrox et CrossFit", "recovery": "Récupération", "strength": "Force",
          "hypertrophy": "Hypertrophie", "injury": "Blessures", "sleep": "Sommeil", "nutrition": "Nutrition", "body_composition": "Composition corporelle",
          "hydration": "Hydratation"}
REQUIRED = ("id", "topic", "citation", "year", "url", "design", "finding_fr", "limits_fr", "confidence")


def validate_entry(e: dict[str, Any], rule_ids: set[str]) -> str | None:
    """Retourne la raison du rejet, ou None si l'entrée est valide."""
    if any(k not in e or e[k] in (None, "") for k in REQUIRED):
        return "champ obligatoire manquant"
    if not ID_RE.match(str(e["id"])):
        return "identifiant invalide"
    if e["topic"] not in TOPICS or e["design"] not in DESIGNS or e["confidence"] not in CONFIDENCE:
        return "valeur hors liste"
    if not isinstance(e["year"], int) or not 1950 <= e["year"] <= 2027:
        return "année invalide"
    if not str(e["url"]).startswith("https://"):
        return "lien non sécurisé"
    if len(str(e["finding_fr"])) > 400 or len(str(e["limits_fr"])) > 400:
        return "texte trop long"
    if any(r not in rule_ids for r in (e.get("applies_to") or [])):
        return "règle inconnue"
    return None


def load_evidence(directory: Path, rule_ids: set[str]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.yaml")) if directory.exists() else []:
        for e in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            why = validate_entry(e, rule_ids) if isinstance(e, dict) else "entrée invalide"
            if why or e["id"] in out:
                log.warning("publication rejetée (%s) : %s", path.name, why or "identifiant en double")
                continue
            e["applies_to"] = e.get("applies_to") or []
            out[e["id"]] = e
    return sorted(out.values(), key=lambda e: (CONFIDENCE[e["confidence"]], e["id"]))


def digest(evidence: list[dict[str, Any]], limit: int = 120) -> dict[str, str]:
    """Résumé compact transmis au coach : identifiant -> constat et niveau de confiance."""
    return {e["id"]: f'{e["finding_fr"][:170]} ({e["confidence"]}, {e["design"]})' for e in evidence[:limit]}


def build_router(require_user: Any) -> APIRouter:
    router = APIRouter(prefix="/evidence", tags=["sources"], dependencies=[Depends(require_user)])

    @router.get("")
    def list_evidence(request: Request, topic: str | None = None, q: str | None = None) -> dict[str, Any]:
        items = request.app.state.evidence
        if topic:
            items = [e for e in items if e["topic"] == topic]
        if q:
            ql = q.lower()[:60]
            items = [e for e in items if ql in (e["citation"] + e["finding_fr"]).lower()]
        counts: dict[str, int] = {}
        for e in request.app.state.evidence:
            counts[e["topic"]] = counts.get(e["topic"], 0) + 1
        return {"items": items, "topics": {k: {"label": TOPICS[k], "count": n} for k, n in counts.items()}, "total": len(request.app.state.evidence)}

    @router.get("/{evidence_id}")
    def one(evidence_id: str, request: Request) -> dict[str, Any]:
        e = next((x for x in request.app.state.evidence if x["id"] == evidence_id), None)
        if not e:
            raise HTTPException(404, "Publication inconnue.")
        return e

    return router
