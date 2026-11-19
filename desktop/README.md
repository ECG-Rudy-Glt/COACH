# COACH desktop (Tauri)

Desktop shell for COACH on Windows, Linux and macOS (unsigned). Users want the **guide**: [docs/desktop.md](../docs/desktop.md) (English) · [docs/desktop.fr.md](../docs/desktop.fr.md) (français). This page is for people building or changing the app.

## How it works

```
Tauri shell (Rust, src-tauri/)  ──spawn──▶  coach-sidecar (PyInstaller, desktop/sidecar.py)
   │  local pages: src/ (first-run wizard, Settings)       │  uvicorn on 127.0.0.1:<free port>
   │  OS keyring: LLM key, Garmin encryption key           │  DATABASE_URL=sqlite:///<data dir>/coach.db
   └─ window ◀──────────── http://127.0.0.1:<port> ────────┘  COOKIE_SECURE=0, ALLOWED_HOSTS=127.0.0.1,localhost, REGISTRATION=first
```

- `sidecar.py` is the entry point frozen by `build-sidecar.py` (PyInstaller, Python 3.12). It bundles `app/` (static files, fonts, i18n), `questions/`, `data/`, `db/` and `skills/`. `serve` runs the app; `backup` makes a consistent SQLite copy. The sidecar exits when its standard input closes (the shell holds the pipe), so it never outlives the app, even after a crash.
- The shell picks a free port, starts the sidecar, waits for `/healthz`, then loads the local URL. One instance only (`tauri-plugin-single-instance`).
- The LLM key is stored in the OS keyring (crate `keyring`, service `COACH`) and given to the sidecar as `LLM_API_KEY` at launch. It is never written to a file, logged, or sent back to the page (`get_state` only says whether a key exists). Other settings (`settings.json` in the data folder): provider, model, base URL (Ollama), monthly budget (`LLM_MONTHLY_BUDGET_EUR`).
- Security: strict CSP on the local pages, no IPC capability for the page served by the sidecar, external links go to the default browser, only `ipc` connections from the shell pages, the sidecar listens on loopback only and rejects other `Host` headers.
- Reminders (optional): ntfy and SMTP settings are stored in `settings.json`; the ntfy token and SMTP password in the OS keyring, and passed to the sidecar as `NTFY_URL`, `NTFY_PUBLIC_URL`, `NTFY_TOKEN`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `AUTO_NOTIFY`, `NOTIFY_HOUR` (names from `docker-compose.yml`). Native desktop pop-ups and web push are not offered: web push needs a push service bound to a web origin, and the page served by the sidecar deliberately has no access to native APIs.
- Update check: the menu entry *Check for updates* makes one anonymous HTTPS request from the Rust shell (crate `ureq`) to `api.github.com/repos/ECG-Rudy-Glt/COACH/releases`, picks the highest published `desktop-vX.Y.Z`, and opens the release page in the browser if it is newer. That is the only outbound request of the shell; the webview CSP (`default-src 'self'`) is unchanged. There is no auto-update (the Tauri updater needs a signing key stored as a GitHub secret: a decision for the maintainer).
- Backup: `coach-sidecar backup --data-dir D --dest X.zip` writes a consistent SQLite copy (backup API) plus `media/`.
- The database is SQLite, selected by `DATABASE_URL=sqlite:///…` (see the storage layer of `app/repo`). `COACH_DESKTOP_DATABASE_URL` overrides it for tests (empty = in-memory).

## Build locally

Requirements: Python 3.12 with `pip install -r requirements.txt pyinstaller`, Rust (stable), Node 20+, and on Linux `libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev patchelf`.

```sh
python desktop/build-sidecar.py     # writes desktop/src-tauri/binaries/coach-sidecar-<target triple>[.exe]
cd desktop && npm ci && npx tauri build
```

Installers land in `desktop/src-tauri/target/release/bundle/`. Regenerate the icons from the fir logo with `npm run icons` (source `icon-source.png` = `app/static/icons/icon-512.png`).

## CI and releases

[`.github/workflows/desktop.yml`](../.github/workflows/desktop.yml):

- Tag `desktop-vX.Y.Z` → builds Windows (msi + NSIS), Linux (AppImage + deb) and macOS (dmg for Apple Silicon and Intel, on native runners because the PyInstaller server is not multi-architecture), writes `SHA256SUMS.txt`, creates the GitHub Release.
- Manual run (Actions > Desktop app > Run workflow): builds and keeps the installers as artifacts for 14 days; nothing is published unless you tick "Publier" and give a tag.
- Unsigned by default. Optional signing: Windows certificate in `WINDOWS_CERTIFICATE` (base64 .pfx) and `WINDOWS_CERTIFICATE_PASSWORD`; macOS through Tauri's `APPLE_*` variables. Without secrets the build is unsigned.

Bump the version in `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml` and `package.json` together, then tag.

## Signing: a possible free route (not applied for)

Code-signing certificates normally cost money, hence the SmartScreen and Gatekeeper warnings documented in the guides. For Windows, the [SignPath Foundation](https://signpath.org) offers free code signing to open source projects. From its [terms page](https://signpath.org/terms) (read on 2026-11-19), a project must: use an OSI-approved open source licence without commercial dual-licensing for all components (COACH is AGPL-3.0-only), contain no malware or potentially unwanted programs, be actively maintained, build its binaries from source in a verifiable way (automated builds, as `desktop.yml` does), have all team members use multi-factor authentication for SignPath and the source repository, and state a code signing policy on the project home page that credits SignPath.io and the SignPath Foundation. The page also asks for documented functionality and defined author, reviewer and approver roles. Applying, and wiring SignPath into the workflow, is a maintainer decision; approval is not automatic. Apple signing and notarization were not researched: no free route is claimed here.
