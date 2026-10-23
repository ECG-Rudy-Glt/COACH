import re
from pathlib import Path

from app.config import VERSION

ROOT = Path(__file__).resolve().parent.parent


def test_version_is_semver_and_matches_changelog():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)
    released = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), flags=re.M)
    assert released and released[0] == VERSION, "CHANGELOG.md top release must equal app.config.VERSION"


def test_compose_documents_published_image():
    assert "ghcr.io/ecg-rudy-glt/coach" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_ui_build_matches_service_worker_cache():
    sw = re.search(r'const CACHE = "([^"]+)"', (ROOT / "app" / "static" / "sw.js").read_text(encoding="utf-8"))
    app = re.search(r'const UI_BUILD = "([^"]+)"', (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8"))
    assert sw and app and sw.group(1) == app.group(1), "bump sw.js CACHE and app.js UI_BUILD together"
