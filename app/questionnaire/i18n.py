"""Traductions du questionnaire : `questions/i18n/<langue>/*.yaml` (une entrée par identifiant de question).

Seuls les textes affichés changent : identifiants, valeurs d'options (stockées en français), conditions `show_if` et clés de faits restent ceux de la
banque d'origine. Format d'une entrée :

    his.injuries:
      text: "Do you have any current or recurring injuries?"
      options: { genou: "Knee", dos: "Back" }          # valeur stockée -> libellé affiché
      unit: "years" · help: "…"
      fields: { zone: { label: "Area", options: { genou: "Knee" } } }   # questions de type « entries »

`benchmarks.yaml` traduit la page « Mes performances » (`sections` par sport, `items` par exercice).
"""
from pathlib import Path
from typing import Any

import yaml

from app.questionnaire.models import Question

SAME_UNITS = {"h", "cm", "kg", "km", "m", "min", "bpm", "%", "kcal"}  # symboles identiques dans toutes les langues gérées


def _read(directory: Path, lang: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((directory / "i18n" / lang).glob("*.yaml")) if (directory / "i18n" / lang).is_dir() else []:
        if path.name == "benchmarks.yaml":
            continue
        out.update(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    return out


def load_overlay(directory: Path, lang: str) -> dict[str, dict[str, Any]]:
    return _read(directory, lang)


def load_benchmark_overlay(directory: Path, lang: str) -> dict[str, dict[str, str]]:
    path = directory / "i18n" / lang / "benchmarks.yaml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def localize(bank: list[Question], overlay: dict[str, dict[str, Any]]) -> list[Question]:
    """Copie de la banque dont les textes affichés sont traduits ; une entrée absente reste en français."""
    out = []
    for q in bank:
        o = overlay.get(q.id)
        if not o:
            out.append(q)
            continue
        data = q.model_dump()
        for key in ("text", "help", "unit"):
            if o.get(key):
                data[key] = o[key]
        if o.get("options"):
            data["option_labels"] = {**(q.option_labels or {}), **o["options"]}
        for f in data.get("fields") or []:
            fo = (o.get("fields") or {}).get(f["id"]) or {}
            if fo.get("label"):
                f["label"] = fo["label"]
            if fo.get("unit"):
                f["unit"] = fo["unit"]
            if fo.get("options"):
                f["option_labels"] = fo["options"]
        out.append(Question(**data))
    return out


def localize_benchmarks(sections: list[dict[str, Any]], overlay: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    titles, items = overlay.get("sections") or {}, overlay.get("items") or {}
    return [{**s, "title": titles.get(s["sport"], s["title"]),
             "items": [{**it, "label": items.get(it["id"], it["label"])} for it in s["items"]]} for s in sections]


def problems(bank: list[Question], overlay: dict[str, dict[str, Any]]) -> list[str]:
    """Ce qui manque ou ne correspond plus à la banque française (utilisé par les tests : une traduction doit toujours être complète)."""
    out: list[str] = []
    by_id = {q.id: q for q in bank}
    out += [f"{k} : identifiant inconnu" for k in overlay if k not in by_id]
    for q in bank:
        o = overlay.get(q.id)
        if not o or not o.get("text"):
            out.append(f"{q.id} : text manquant")
            continue
        out += [f"{q.id} : option {v!r} sans libellé" for v in q.options or [] if v not in (o.get("options") or {})]
        out += [f"{q.id} : option {v!r} inconnue" for v in (o.get("options") or {}) if v not in (q.options or [])]
        if q.help and not o.get("help"):
            out.append(f"{q.id} : help manquant")
        if q.unit and q.unit not in SAME_UNITS and not o.get("unit"):
            out.append(f"{q.id} : unit manquant")
        fo_all = o.get("fields") or {}
        out += [f"{q.id} : champ {k!r} inconnu" for k in fo_all if k not in {f.id for f in q.fields or []}]
        for f in q.fields or []:
            fo = fo_all.get(f.id) or {}
            if not fo.get("label"):
                out.append(f"{q.id}.{f.id} : label manquant")
            out += [f"{q.id}.{f.id} : option {v!r} sans libellé" for v in f.options or [] if v not in (fo.get("options") or {})]
            if f.unit and f.unit not in SAME_UNITS and not fo.get("unit"):
                out.append(f"{q.id}.{f.id} : unit manquant")
    return out


def bank_for(state: Any, lang: str) -> list[Question]:
    """Banque localisée de l'application (`state.banks[lang]`), sinon la banque française d'origine."""
    return getattr(state, "banks", {}).get(lang) or state.bank  # type: ignore[no-any-return]
