"""Manifeste de mise à jour de l'application de bureau (desktop/make_latest_json.py) : plateformes, URLs, signatures, erreurs."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("make_latest_json", Path(__file__).resolve().parent.parent / "desktop" / "make_latest_json.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FILES = ["COACH_0.2.0_x64-setup.exe", "COACH_0.2.0_x64_en-US.msi", "COACH_0.2.0_x64_fr-FR.msi", "COACH_0.2.0_amd64.AppImage", "COACH_0.2.0_aarch64.app.tar.gz", "COACH_0.2.0_x64.app.tar.gz"]


def make(tmp_path, skip_sig=None):
    for n in FILES:
        (tmp_path / n).write_bytes(b"x")
        if n != skip_sig and not n.endswith("fr-FR.msi"):
            (tmp_path / (n + ".sig")).write_text("SIGNATURE-FACTICE-" + n + "\n")
    return tmp_path


def test_manifest_lists_every_platform_with_release_urls(tmp_path):
    m = mod.build(make(tmp_path), "desktop-v0.2.0", "owner/repo", "notes")
    assert m["version"] == "0.2.0" and m["notes"] == "notes"
    assert set(m["platforms"]) == {"windows-x86_64", "windows-x86_64-nsis", "windows-x86_64-msi", "linux-x86_64", "linux-x86_64-appimage", "darwin-aarch64", "darwin-x86_64"}
    p = m["platforms"]["darwin-aarch64"]
    assert p["url"] == "https://github.com/owner/repo/releases/download/desktop-v0.2.0/COACH_0.2.0_aarch64.app.tar.gz"
    assert p["signature"] == "SIGNATURE-FACTICE-COACH_0.2.0_aarch64.app.tar.gz"


def test_missing_signature_or_bad_tag_fails(tmp_path):
    with pytest.raises(SystemExit):
        mod.build(make(tmp_path, skip_sig="COACH_0.2.0_amd64.AppImage"), "desktop-v0.2.0", "o/r")
    with pytest.raises(SystemExit):
        mod.build(tmp_path, "v0.2.0", "o/r")
