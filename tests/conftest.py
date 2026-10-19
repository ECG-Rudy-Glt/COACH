import pytest


@pytest.fixture(autouse=True)
def _open_registration(monkeypatch):
    """Les tests créent plusieurs comptes ; le mode par défaut (`first`) est couvert par tests/test_security.py."""
    monkeypatch.setenv("REGISTRATION", "open")
