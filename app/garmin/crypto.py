"""Chiffrement des jetons Garmin au repos (Fernet). La clé vient de l'environnement ou d'un fichier secret, jamais du dépôt."""

from cryptography.fernet import Fernet, InvalidToken

from app.config import env


class NotConfigured(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = env("SECRETS_KEY")
    if not key:
        raise NotConfigured("SECRETS_KEY manquante : la connexion Garmin est désactivée.")
    return Fernet(key.encode())


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise NotConfigured("Jeton Garmin illisible (clé de chiffrement changée ?). Reconnectez Garmin.") from e
