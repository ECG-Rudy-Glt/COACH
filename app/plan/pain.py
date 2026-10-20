"""Douleurs déclarées en texte libre dans les retours de séance : le moteur les traite comme des blessures actives (règle S2)."""
import re
from datetime import date, timedelta
from typing import Any

PAIN = re.compile(r"\b(douleur|douleurs|mal au|mal à|gêne|gene|tendinite|inflammation|blessure|claquage|élongation|elongation|sensible)\w*", re.I)
ZONES = {
    "coude": ["coude"], "épaule": ["épaule", "epaule"], "genou": ["genou"], "dos": ["dos", "lombaire", "lombaires"], "cheville": ["cheville"],
    "hanche": ["hanche"], "poignet": ["poignet"], "tendon d'Achille": ["achille", "tendon d'achille"], "tibia": ["tibia", "périostite", "periostite"],
    "mollet": ["mollet", "mollets"], "pied": ["pied", "fascia", "plantaire", "voûte", "voute"], "ischio-jambiers": ["ischio", "ischios", "ischio-jambiers"],
}


def pain_zones(sessions: list[dict[str, Any]], today: date, days: int = 21) -> set[str]:
    """Zones douloureuses mentionnées dans les retours des dernières semaines (note, adaptation, étiquette « douleur »)."""
    found: set[str] = set()
    for s in sessions:
        if s["day"] < today - timedelta(days=days) or not s.get("logged"):
            continue
        lg = s["logged"]
        text = " ".join(str(lg.get(k) or "") for k in ("note", "adaptation")).lower()
        if not (PAIN.search(text) or "douleur" in (lg.get("changes") or [])):
            continue
        for zone, words in ZONES.items():
            if any(re.search(rf"\b{re.escape(w)}\b", text) for w in words):
                found.add(zone)
    return found
