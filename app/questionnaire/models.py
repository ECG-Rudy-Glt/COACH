from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

QuestionType = Literal["single", "multi", "number", "duration", "date", "scale", "text", "entries"]
FieldType = Literal["single", "number", "text", "year", "duration", "date"]


class EntryField(BaseModel):
    """Champ d'une entrée d'une question de type `entries` (parcours, performances, blessures…)."""

    id: str
    label: str
    type: FieldType
    options: list[str] | None = None
    unit: str | None = None
    optional: bool = False


class Question(BaseModel):
    id: str
    domain: str
    text: str
    type: QuestionType
    fact_key: str
    unit: str | None = None
    options: list[str] | None = None
    option_labels: dict[str, str] | None = None  # libellés affichés (valeurs stockées inchangées)
    show_if: dict[str, Any] | None = None
    required: bool = False  # important pour le plan (l'utilisateur peut quand même passer)
    essential: bool = False  # posée à l'accueil : de quoi construire un premier plan ; le reste vient ensuite, à la demande du coach
    blocking: bool = False  # seule exception : impossible à passer (ex. mention légale)
    fields: list[EntryField] | None = None  # pour type=entries
    allow_other: bool = False  # propose « autre » + précision libre (fait `<clé>.other`)
    help: str | None = None
    order: int = 0


class Fact(BaseModel):
    key: str
    value: Any
    source: str = "questionnaire"
    confidence: float = 1.0
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def current_facts(facts: list[Fact]) -> dict[str, Any]:
    """Valeur courante par clé : le fait le plus récent l'emporte."""
    latest: dict[str, Fact] = {}
    for f in facts:
        if f.key not in latest or f.observed_at >= latest[f.key].observed_at:
            latest[f.key] = f
    return {k: f.value for k, f in latest.items()}
