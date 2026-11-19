import os
import tempfile
from pathlib import Path

import pytest

if os.environ.get("COACH_TEST_REPO") == "sqlite":
    # Rejoue toute la suite contre SQLite : chaque `MemoryRepo()` des tests devient une base SQLite neuve (fichier temporaire).
    import app.repo as _repo

    _ROOT = Path(tempfile.mkdtemp(prefix="coach-sqlite-suite-"))
    _COUNT = [0]

    def _sqlite_for_tests() -> _repo.SqliteRepo:
        _COUNT[0] += 1
        r = _repo.SqliteRepo(_ROOT / f"{_COUNT[0]}.db")
        r.migrate(_repo.ROOT / "db" / "sqlite")
        return r

    _repo.MemoryRepo = _sqlite_for_tests  # type: ignore[misc,assignment]


def pytest_collection_modifyitems(config, items):
    if os.environ.get("COACH_TEST_REPO") == "sqlite":
        skip = pytest.mark.skip(reason="dépend de l'état interne de MemoryRepo")
        for item in items:
            if "memory_only" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def _open_registration(monkeypatch):
    """Les tests créent plusieurs comptes ; le mode par défaut (`first`) est couvert par tests/test_security.py."""
    monkeypatch.setenv("REGISTRATION", "open")
