"""Fige desktop/sidecar.py (et l'application COACH) avec PyInstaller, puis le place là où Tauri l'attend :
desktop/src-tauri/binaries/coach-sidecar-<triplet de cible>[.exe]   (voir `bundle.externalBin`).

À lancer depuis n'importe où, avec un Python 3.12 qui a `pip install -r requirements.txt pyinstaller`.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "desktop" / "src-tauri" / "binaries"
# Dossiers lus au démarrage par l'application (voir app/main.py, app/i18n.py, app/coach/*.py).
DATA = ["app/static", "questions", "data", "db", "skills"]
# Paquets chargés dynamiquement ou avec des fichiers de données : PyInstaller ne les devine pas tous.
COLLECT_ALL = ["garminconnect", "garth", "psycopg", "psycopg_binary", "pywebpush", "py_vapid", "fitdecode", "defusedxml", "uvicorn", "yaml"]


def target_triple() -> str:
    out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    m = re.search(r"^host: (\S+)$", out, re.M)
    if not m:
        raise SystemExit("rustc -vV : triplet introuvable")
    return m.group(1)


def main() -> None:
    triple = os.environ.get("TARGET_TRIPLE") or target_triple()
    exe = ".exe" if "windows" in triple else ""
    work = ROOT / "desktop" / "build"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console", "--name", "coach-sidecar",
           "--distpath", str(work / "dist"), "--workpath", str(work / "work"), "--specpath", str(work),
           "--paths", str(ROOT), "--collect-submodules", "app"]
    for d in DATA:
        cmd += ["--add-data", f"{ROOT / d}{os.pathsep}{d}"]
    for pkg in COLLECT_ALL:
        cmd += ["--collect-all", pkg]
    cmd += [str(ROOT / "desktop" / "sidecar.py")]
    subprocess.run(cmd, check=True, cwd=ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"coach-sidecar-{triple}{exe}"
    shutil.copy2(work / "dist" / f"coach-sidecar{exe}", dest)
    print(f"Sidecar : {dest} ({dest.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    main()
