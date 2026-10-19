"""Configuration lue dans l'environnement (jamais de secret dans le code).

Chaque secret `NOM` peut aussi être fourni par `NOM_FILE` (chemin d'un fichier, ex. un secret Docker `/run/secrets/…`) :
le fichier prime sur la variable, pour ne laisser aucune valeur sensible dans `docker inspect` ni dans l'environnement du conteneur.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

VERSION = "0.1.0"


def env(name: str, default: str = "") -> str:
    """Valeur de `NOM_FILE` (contenu du fichier) si présente, sinon de `NOM`, sinon `default`. Sans espaces aux extrémités."""
    path = os.environ.get(f"{name}_FILE", "").strip()
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError as e:
            raise RuntimeError(f"{name}_FILE : fichier illisible ({path})") from e
    return os.environ.get(name, default).strip()


def database_url() -> str:
    """`DATABASE_URL` si fournie, sinon assemblée depuis `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`(`_FILE`). Vide = stockage mémoire."""
    url = env("DATABASE_URL")
    if url or not os.environ.get("DB_HOST"):
        return url
    user, pw = quote(os.environ.get("DB_USER", "sportcoach"), safe=""), quote(env("DB_PASSWORD"), safe="")
    return f"postgresql://{user}:{pw}@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{quote(os.environ.get('DB_NAME', 'sportcoach'), safe='')}"


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_provider: str
    log_level: str


def load_settings() -> Settings:
    return Settings(
        database_url=database_url(),
        llm_provider=os.environ.get("LLM_PROVIDER", "anthropic"),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
