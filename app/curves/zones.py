"""Zones de fréquence cardiaque et temps passé dans chacune (règle ST26)."""
from typing import Any

# Bornes en % de la FC max : 60-75 % (zone 2) et 85-92 % (zone 4) sont celles du moteur (zone_text, M17) ; les autres sont une convention.
BOUNDS = (0.60, 0.75, 0.85, 0.92)
NAMES = ("Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5")
MAX_GAP_S = 30  # au-delà, le point suivant ne « rattrape » pas la pause : l'intervalle n'est pas compté


def zone_of(hr: float, hr_max: float) -> int:
    share = hr / hr_max
    return sum(share >= b for b in BOUNDS)


def zone_edges(hr_max: float) -> list[int]:
    return [round(hr_max * b) for b in BOUNDS]


def time_in_zones(t: list[int], hr: list[int | None], hr_max: float) -> list[int]:
    """Secondes par zone : chaque point compte pour l'intervalle qui le suit (au plus MAX_GAP_S), les points sans FC sont ignorés. Approximation sur des points moyennés."""
    secs = [0.0] * len(NAMES)
    for i in range(len(t) - 1):
        if hr[i] is None:
            continue
        dt = t[i + 1] - t[i]
        if 0 < dt <= MAX_GAP_S * 4:  # des points moyennés sont espacés de plusieurs secondes sur une longue sortie
            secs[zone_of(hr[i], hr_max)] += dt
    return [round(s) for s in secs]


def zones_block(streams: dict[str, Any], hr_max: float | None, basis: str | None) -> dict[str, Any] | None:
    if not streams.get("hr") or not hr_max:
        return None
    return {"hr_max": round(hr_max), "basis": basis, "edges": zone_edges(hr_max), "names": list(NAMES), "seconds": time_in_zones(streams["t"], streams["hr"], hr_max)}
