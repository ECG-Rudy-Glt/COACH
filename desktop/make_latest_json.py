"""Génère `latest.json` (manifeste du plugin updater de Tauri 2) à partir des installateurs et de leurs signatures `.sig`.

Usage : python desktop/make_latest_json.py DOSSIER_DES_ASSETS TAG DEPOT [NOTES]   (DEPOT = « propriétaire/nom »)
Les URLs pointent vers les assets de la Release `TAG`. Ne contient aucune clé : les `.sig` sont des signatures publiques vérifiables avec
la clé publique de tauri.conf.json.
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# clé de plateforme du manifeste -> motif du nom de fichier de l'installateur mis à jour (sa signature est « <fichier>.sig »)
PLATFORMS = {
    "windows-x86_64": "-setup.exe",
    "windows-x86_64-nsis": "-setup.exe",
    "windows-x86_64-msi": "_en-US.msi",
    "linux-x86_64": ".AppImage",
    "linux-x86_64-appimage": ".AppImage",
    "darwin-aarch64": "_aarch64.app.tar.gz",
    "darwin-x86_64": "_x64.app.tar.gz",
}


def build(assets: Path, tag: str, repo: str, notes: str = "") -> dict:
    if not tag.startswith("desktop-v"):
        raise SystemExit(f"tag inattendu : {tag}")
    platforms: dict[str, dict[str, str]] = {}
    for key, suffix in PLATFORMS.items():
        files = sorted(f for f in assets.iterdir() if f.name.endswith(suffix) and f.is_file())
        if len(files) != 1:
            raise SystemExit(f"{key} : {len(files)} fichier(s) en « {suffix} » (un seul attendu)")
        sig = assets / (files[0].name + ".sig")
        if not sig.is_file():
            raise SystemExit(f"{key} : signature absente ({sig.name})")
        platforms[key] = {"signature": sig.read_text(encoding="utf-8").strip(), "url": f"https://github.com/{repo}/releases/download/{tag}/{files[0].name}"}
    return {"version": tag.removeprefix("desktop-v"), "notes": notes, "pub_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "platforms": platforms}


def main(argv: list[str]) -> int:
    if len(argv) not in (4, 5):
        print(__doc__, file=sys.stderr)
        return 2
    manifest = build(Path(argv[1]), argv[2], argv[3], argv[4] if len(argv) == 5 else "")
    (Path(argv[1]) / "latest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v["url"] for k, v in manifest["platforms"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
