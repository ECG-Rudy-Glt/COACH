"""Page « Mes performances » : record et niveau actuel par exercice.

Chaque exercice est un fait `bench.<id>` = {"pr": {...}, "now": {...}}
(l'un ou l'autre peut manquer).
"""
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.questionnaire.answers import AnswerError
from app.questionnaire.models import Fact

KINDS = {"weight_reps", "reps", "time", "watts", "rounds"}
TIME_RE = re.compile(r"^(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)$")  # h:mm:ss ou mm:ss


class Benchmark(BaseModel):
    id: str
    label: str
    kind: str
    sport: str
    title: str


def load_catalog(path: Path) -> tuple[list[dict[str, Any]], dict[str, Benchmark]]:
    sections = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    index: dict[str, Benchmark] = {}
    for sec in sections:
        for it in sec["items"]:
            if it["kind"] not in KINDS:
                raise ValueError(f"benchmark {it['id']} : type inconnu {it['kind']}")
            if it["id"] in index:
                raise ValueError(f"benchmark dupliqué : {it['id']}")
            index[it["id"]] = Benchmark(**it, sport=sec["sport"], title=sec["title"])
    return sections, index


def visible_sections(sections: list[dict[str, Any]], sports: list[str]) -> list[dict[str, Any]]:
    out = []
    for sec in sections:
        keys = {sec["sport"], *sec.get("also", [])}
        if keys & set(sports):
            out.append({"sport": sec["sport"], "title": sec["title"], "items": sec["items"]})
    return out


def _num(v: Any, label: str, *, integer: bool = False) -> float | int:
    if isinstance(v, bool) or not isinstance(v, int | float) or v < 0 or v > 100000:
        raise AnswerError(f"{label} : nombre positif attendu")
    if integer and int(v) != v:
        raise AnswerError(f"{label} : entier attendu")
    return int(v) if integer or int(v) == v else v


def _result(kind: str, raw: Any, label: str) -> dict[str, Any] | None:
    """Valide un résultat (record ou actuel). Vide ou None = non renseigné."""
    if raw in (None, {}, ""):
        return None
    if not isinstance(raw, dict):
        raise AnswerError(f"{label} : format invalide")
    out: dict[str, Any] = {}
    if kind == "weight_reps":
        if raw.get("weight") in (None, ""):
            return None
        out["weight"] = _num(raw["weight"], label)
        out["reps"] = _num(raw.get("reps", 1), label, integer=True) or 1
    elif kind in ("reps", "rounds"):
        if raw.get("reps") in (None, ""):
            return None
        out["reps"] = _num(raw["reps"], label)
    elif kind == "watts":
        if raw.get("watts") in (None, ""):
            return None
        out["watts"] = _num(raw["watts"], label, integer=True)
    else:  # time
        t = raw.get("time")
        if t in (None, ""):
            return None
        m = TIME_RE.match(str(t).strip())
        if not m:
            raise AnswerError(f"{label} : temps attendu au format mm:ss ou h:mm:ss")
        out["time"] = str(t).strip()
    if raw.get("year") not in (None, ""):
        out["year"] = _num(raw["year"], "année", integer=True)
        if not 1940 <= out["year"] <= 2100:
            raise AnswerError("année invalide")
    return out


def to_fact(b: Benchmark, payload: dict[str, Any]) -> Fact:
    pr = _result(b.kind, payload.get("pr"), f"{b.label} (record)")
    now = _result(b.kind, payload.get("now"), f"{b.label} (actuel)")
    value: dict[str, Any] | None = {k: v for k, v in (("pr", pr), ("now", now)) if v} or None
    return Fact(key=f"bench.{b.id}", value=value, source="questionnaire")
