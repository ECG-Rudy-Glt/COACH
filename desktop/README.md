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
- Updates: the menu entry *Check for updates* asks the public GitHub API (anonymous, via `ureq`) for the highest published `desktop-vX.Y.Z` release; if newer and the platform can self-update (Windows, macOS, Linux AppImage; not `.deb`), it asks for confirmation, then `tauri-plugin-updater` downloads `https://github.com/ECG-Rudy-Glt/COACH/releases/download/<tag>/latest.json`'s package, verifies its minisign signature against `plugins.updater.pubkey` in `tauri.conf.json`, the shell stops the sidecar, installs and restarts. On any failure the sidecar is restarted and the release page opens in the browser. The endpoint is built from the tag at runtime (the repository's "latest" release is not necessarily a desktop one). The updater is never called from a web page: no command is exposed, the capability stays `core:default`, and the webview CSP is unchanged. These Rust-side requests (GitHub API, release assets) are the only outbound requests of the shell.
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

## Updater signing key (separate from code signing)

- The key pair was generated with `tauri signer generate`. The **public** key is in `src-tauri/tauri.conf.json` (`plugins.updater.pubkey`). The **private** key and its password are stored only in OpenBao (`secret/homelab/coach-updater-signing`, fields `private_key` and `password`) and in the repository's GitHub Actions secrets `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. Never commit, print or log them.
- The workflow requires both secrets (`bundle.createUpdaterArtifacts` signs each bundle) and uploads `.sig` files plus `latest.json` (generated by `desktop/make_latest_json.py`: windows-x86_64 (NSIS, also `-nsis` and `-msi` keys), linux-x86_64 (AppImage), darwin-aarch64, darwin-x86_64) next to the installers. `SHA256SUMS.txt` covers every uploaded file. A manual run without publishing keeps all of it, including `latest.json` and `SHA256SUMS.txt`, in the `release-assets` artifact so you can read it first.
- **Rotation or loss**: apps only trust the public key they embed. To rotate (or after a loss or leak), generate a new pair, replace the OpenBao entry and both GitHub secrets, put the new public key in `tauri.conf.json`, and publish that version as a **manual** download (existing installs cannot verify it). Once users have installed it by hand, automatic updates work again. Keep a copy of the private key and password in the vault only: if both the vault and the GitHub secrets are lost, you are in the same situation as a rotation.
- To test an update for real you need two published releases (for example `desktop-v0.1.0` then `desktop-v0.1.1`): install the first, publish the second, then use the menu entry. That test has not been run yet.
