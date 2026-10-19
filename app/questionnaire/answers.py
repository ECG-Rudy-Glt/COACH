"""Validation d'une réponse et conversion en faits."""
from datetime import date
from typing import Any

from app.questionnaire.models import Fact, Question

OTHER = "autre"


class AnswerError(ValueError):
    pass


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _entries(q: Question, value: Any) -> list[dict[str, Any]]:
    """Liste d'entrées structurées ; une liste vide = « rien à signaler »."""
    if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):
        raise AnswerError("liste d'entrées attendue")
    if len(value) > 50:
        raise AnswerError("trop d'entrées")
    fields = {f.id: f for f in q.fields or []}
    clean: list[dict[str, Any]] = []
    for e in value:
        unknown = set(e) - set(fields)
        if unknown:
            raise AnswerError(f"champs inconnus : {sorted(unknown)}")
        row: dict[str, Any] = {}
        for f in fields.values():
            v = e.get(f.id)
            if v in (None, ""):
                if f.optional:
                    continue
                raise AnswerError(f"« {f.label} » est requis")
            if f.type == "single":
                if v not in (f.options or []):
                    raise AnswerError(f"« {f.label} » : option inconnue")
            elif f.type in ("number", "duration"):
                if not _is_number(v) or v < 0:
                    raise AnswerError(f"« {f.label} » : nombre positif attendu")
            elif f.type == "year":
                top = date.today().year + 1
                if not isinstance(v, int) or isinstance(v, bool) or not 1940 <= v <= top:
                    raise AnswerError(f"« {f.label} » : année valide attendue")
            elif f.type == "date":
                try:
                    date.fromisoformat(str(v))
                except ValueError as e:
                    raise AnswerError(f"« {f.label} » : date attendue (AAAA-MM-JJ)") from e
            elif not isinstance(v, str) or not v.strip():
                raise AnswerError(f"« {f.label} » : texte attendu")
            else:
                v = v.strip()[:300]
            row[f.id] = v
        clean.append(row)
    return clean


def to_facts(
    q: Question, value: Any, other_text: str | None = None, source: str = "questionnaire"
) -> list[Fact]:
    """Valide `value` selon le type de `q` ; retourne le fait principal (+ précision « autre »)."""
    other_text = (other_text or "").strip() or None

    if q.type == "single":
        if q.options is None or not isinstance(value, str):
            raise AnswerError("réponse unique attendue")
        if value == OTHER and q.allow_other:
            if not other_text:
                raise AnswerError("précisez « autre »")
        elif value not in q.options:
            raise AnswerError(f"option inconnue : {value}")

    elif q.type == "multi":
        if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
            raise AnswerError("liste non vide attendue")
        allowed = set(q.options or []) | ({OTHER} if q.allow_other else set())
        unknown = [v for v in value if v not in allowed]
        if unknown:
            raise AnswerError(f"options inconnues : {unknown}")
        if len(set(value)) != len(value):
            raise AnswerError("doublons")
        if OTHER in value and not other_text:
            raise AnswerError("précisez « autre »")

    elif q.type in ("number", "duration"):
        if not _is_number(value) or value < 0:
            raise AnswerError("nombre positif attendu")

    elif q.type == "scale":
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
            raise AnswerError("entier de 1 à 5 attendu")

    elif q.type == "date":
        try:
            date.fromisoformat(str(value))
        except ValueError as e:
            raise AnswerError("date ISO attendue (AAAA-MM-JJ)") from e

    elif q.type == "entries":
        value = _entries(q, value)

    elif q.type == "text":
        if not isinstance(value, str) or not value.strip():
            raise AnswerError("texte attendu")
        value = value.strip()

    facts = [Fact(key=q.fact_key, value=value, source=source)]
    keeps_other = value == OTHER or (isinstance(value, list) and OTHER in value)
    if q.allow_other and keeps_other and other_text:
        facts.append(Fact(key=f"{q.fact_key}.other", value=other_text, source=source))
    return facts
