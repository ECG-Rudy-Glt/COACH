"""Transformation des données wger et free-exercise-db vers le modèle commun, fusion, exercices maison."""
import html
import re
from pathlib import Path
from typing import Any

import yaml

from app.exercises.labels import (
    FREE_EQUIPMENT,
    FREE_KIND,
    WGER_EQUIPMENT,
    WGER_MUSCLE,
)
from app.exercises.models import Exercise, Media

FR, EN = 12, 2  # identifiants de langue wger
FREE_BASE = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
CUSTOM_LICENSE = "Original du projet (AGPL-3.0)"
WGER_REGION = {"Abs": "abdominaux", "Arms": "bras", "Back": "dos", "Calves": "mollets",
               "Cardio": "cardio", "Chest": "pectoraux", "Legs": "jambes", "Shoulders": "épaules"}


def norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _plain(text: str) -> str:
    text = re.sub(r"<\s*br\s*/?>|</p>|</li>", "\n", text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


def wger_exercise(raw: dict[str, Any], licenses: dict[int, tuple[str, str | None]]) -> Exercise | None:
    tr = {int(t["language"]): t for t in raw.get("translations", []) if t.get("name")}
    chosen = tr.get(FR) or tr.get(EN)
    if not chosen:
        return None
    lang = "fr" if FR in tr else "en"
    lic = raw.get("license") or {}
    author = raw.get("license_author") or None

    def muscle(m: dict[str, Any]) -> str | None:
        return WGER_MUSCLE.get((m.get("name_en") or m.get("name") or "").lower().strip()) \
            or WGER_MUSCLE.get((m.get("name") or "").lower().strip())

    def uniq(xs: list[str | None]) -> list[str]:
        return list(dict.fromkeys(x for x in xs if x))

    equipment = uniq([WGER_EQUIPMENT.get(e["name"].lower()) for e in raw.get("equipment", [])]) \
        or ["bodyweight"]
    media: list[Media] = []
    for im in raw.get("images", []):
        name, url = licenses.get(im.get("license"), (lic.get("short_name", "CC-BY-SA"), lic.get("url")))
        media.append(Media(kind="image", url=im["image"], thumb_url=(im.get("thumbnails") or {}).get("medium"),
                           is_main=bool(im.get("is_main")), license=name, license_url=url,
                           author=im.get("license_author") or author))
    for v in raw.get("videos", []):
        name, url = licenses.get(v.get("license"), (lic.get("short_name", "CC-BY-SA"), lic.get("url")))
        media.append(Media(kind="video", url=v["video"], license=name, license_url=url,
                           author=v.get("license_author") or author))
    en_name = tr.get(EN, {}).get("name")
    text = chosen.get("description_source") or chosen.get("description") or ""
    return Exercise(
        source="wger", source_id=str(raw["id"]), sources=["wger"], name=chosen["name"].strip(),
        name_en=en_name.strip() if en_name else None, kind="strength",
        region=WGER_REGION.get((raw.get("category") or {}).get("name", "")),
        muscles_primary=uniq([muscle(m) for m in raw.get("muscles", [])]),
        muscles_secondary=uniq([muscle(m) for m in raw.get("muscles_secondary", [])]),
        equipment=equipment, instructions=_plain(text) or None, instructions_lang=lang,
        license=lic.get("short_name", "CC-BY-SA"), license_url=lic.get("url"), author=author, media=media,
    )


def free_exercise(raw: dict[str, Any]) -> Exercise:
    media = [Media(kind="image", url=FREE_BASE + p, is_main=(i == 0), license="Unlicense (domaine public)",
                   license_url="https://unlicense.org", author="free-exercise-db")
             for i, p in enumerate(raw.get("images", []))]
    equip = FREE_EQUIPMENT.get(str(raw.get("equipment")).lower(), "other")
    return Exercise(
        source="free-exercise-db", source_id=raw["id"], sources=["free-exercise-db"], name=raw["name"].strip(),
        name_en=raw["name"].strip(), kind=FREE_KIND.get(raw.get("category", ""), "other"),
        muscles_primary=list(raw.get("primaryMuscles", [])), muscles_secondary=list(raw.get("secondaryMuscles", [])),
        equipment=[equip], level=raw.get("level"),
        instructions="\n".join(f"{i}. {s}" for i, s in enumerate(raw.get("instructions", []), 1)) or None,
        instructions_lang="en", license="Unlicense (domaine public)", license_url="https://unlicense.org",
        author="free-exercise-db", media=media,
    )


def custom_exercises(path: Path) -> list[Exercise]:
    out = []
    for r in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
        out.append(Exercise(
            source="custom", source_id=r["id"], sources=["custom"], name=r["name"], kind=r["kind"],
            muscles_primary=r.get("muscles_primary", []), muscles_secondary=r.get("muscles_secondary", []),
            equipment=r.get("equipment", ["bodyweight"]), level=r.get("level"), instructions=r["instructions"].strip(),
            instructions_lang="fr", license=CUSTOM_LICENSE, author="sport-coach",
        ))
    return out


def merge(wger: list[Exercise], free: list[Exercise], custom: list[Exercise]) -> list[Exercise]:
    """wger prime (français, médias CC) ; un exercice free-exercise-db de même nom y ajoute ses images."""
    by_name = {norm_key(e.name_en): e for e in wger if e.name_en}
    merged = list(wger)
    for f in free:
        target = by_name.get(norm_key(f.name))
        if target is None:
            merged.append(f)
            continue
        target.sources.append("free-exercise-db")
        target.media.extend(f.media)
        if not target.instructions:
            target.instructions, target.instructions_lang = f.instructions, "en"
        if not target.muscles_primary:
            target.muscles_primary = f.muscles_primary
        target.level = target.level or f.level
        if target.kind == "strength" and f.kind != "other":
            target.kind = f.kind
    return merged + custom
