# COACH desktop app (Windows and Linux)

One installer, nothing else to install. The desktop app bundles the COACH server and a local database, opens in its own window and keeps everything on your computer. Français : [desktop.fr.md](desktop.fr.md).

> Not a medical device and not dietary advice, same as the rest of COACH: see [DISCLAIMER.md](../DISCLAIMER.md).

## What you get (and what you do not)

- A normal desktop window. Behind it, a COACH server starts on `127.0.0.1` only (never reachable from the network, on a random free port) and stops when you close the window.
- Your accounts, plans and logs are stored in a local SQLite file. No account on any website, no telemetry.
- The AI coach is **optional**. Without it COACH still builds your plan and your nutrition targets (they never come from an AI anyway). Details in [the AI key guide](#ai-key-guide).
- Not included: access from your phone (use the [Docker setup](../README.md#quick-start-5-minutes-docker) for that), browser push notifications, code signing. Updates are one click but never silent. See [Known limits](#known-limits).

## 1. Download

Open the [Releases page](https://github.com/ECG-Rudy-Glt/COACH/releases) and pick the release whose tag starts with `desktop-v`.

| System | File to download |
|---|---|
| Windows 10/11 | `COACH_<version>_x64-setup.exe` (recommended) or `COACH_<version>_x64_en-US.msi` |
| Linux (any recent distribution) | `COACH_<version>_amd64.AppImage` |
| Debian / Ubuntu | `COACH_<version>_amd64.deb` |
| macOS, Apple Silicon (M1 and later) | `COACH_<version>_aarch64.dmg` |
| macOS, Intel | `COACH_<version>_x64.dmg` |

Also download `SHA256SUMS.txt` from the same release.

## 2. Check the download (SHA-256)

The installers are built by GitHub Actions from this repository. `SHA256SUMS.txt` lets you check that your file is the one that was built and was not corrupted or swapped.

```sh
# Linux (in the download folder)
sha256sum -c SHA256SUMS.txt --ignore-missing
```

```powershell
# Windows (PowerShell): the value must be identical to the line in SHA256SUMS.txt
Get-FileHash .\COACH_0.1.0_x64-setup.exe -Algorithm SHA256
```

If the values differ, do not run the file; download it again.

## 3. Install

### Windows and the SmartScreen warning

The installers are **not code-signed** (a certificate costs money). Windows SmartScreen therefore shows "Windows protected your PC / Unknown publisher". It is not a virus detection. After checking the SHA-256 above: click **More info**, then **Run anyway**.

Run the `-setup.exe` (installs for your user only, no administrator rights) or the `.msi`. Start **COACH** from the Start menu.

### Linux

```sh
chmod +x COACH_*.AppImage && ./COACH_*.AppImage     # AppImage (on Ubuntu 22.04+ install libfuse2 first if it refuses to start)
sudo apt install ./COACH_*_amd64.deb               # Debian / Ubuntu
```

### macOS and Gatekeeper

The `.dmg` is **not signed or notarized by Apple** (Apple's signing programme is not free to our knowledge; we have not verified its current terms), so macOS blocks the first launch ("cannot be opened because the developer cannot be verified", or on Apple Silicon sometimes "is damaged"). Check the SHA-256 first, drag COACH to Applications, then either:

- try to open it once, then open *System Settings > Privacy & Security* and click **Open Anyway** next to the COACH message (macOS 15 and later); on older macOS, right-click the app and choose **Open**; or
- in a terminal: `xattr -dr com.apple.quarantine /Applications/COACH.app`.

We have no Mac to test on: the macOS installers are built by the CI but the interface has never been run by the maintainers on macOS. The AI key goes to the macOS Keychain (it may ask for your login password).

### Linux keyring

The AI key is kept in your desktop's keyring (GNOME Keyring or KWallet, present on most desktops). Without a keyring you can still use COACH without an AI or with Ollama.

## 4. First launch, step by step

1. **Wizard screen.** COACH asks which AI assistant to use. If you are unsure, choose **None** now: you can change it any time in **COACH > Settings**. Click **Start COACH**.
2. **Waiting.** The first start takes a few seconds (the server starts and creates its database).
3. **Create your account.** The first account is the owner; this is local, nothing is sent anywhere. Pick a password of at least 10 characters and keep it: there is no e-mail server to send a reset link. Registration then closes (nobody else can create an account on your computer through the app).
4. **Answer the essential questions** (see [What is left to fill in](#what-is-left-to-fill-in)).

<img src="img/home-light.png" width="240" alt="COACH home screen">

## AI key guide

Facts below were read on the providers' official pages on **2026-11-19**; prices and menus change, so check the linked page before paying. What we could not verify is said explicitly.

### What the key is for

The AI coach writes explanations, answers your chat questions, proposes small bounded adjustments to your week (the server checks them against the rules), estimates a meal from a photo and asks the missing questions during onboarding. It never produces the numbers of your plan or your nutrition targets.

### Do I need one?

No. Everything marked "optional" works without it, and COACH tells you when an AI feature is off. Add a key whenever you want the chat, the weekly review or the meal-photo estimate.

### What leaves your computer

Only if you choose a cloud provider: the questions and context of the AI feature you use (your facts and recent training, never your name or e-mail, see [docs/prompts.md](prompts.md)) go to that provider. With **Ollama** (local model) or **None**, nothing leaves the computer for the AI.

### Where the key is stored

In your operating system's keyring (Windows Credential Manager, macOS Keychain, GNOME Keyring / KWallet). Never in a file of the app, never in the logs, never shown again after you save it. The server receives it only as an environment variable when it starts.

### A ChatGPT or Claude subscription is not an API key

You need a developer **API** account with billing at the provider. Chat subscriptions cannot be used by an application.

### Create a key, provider by provider

The wizard has a **Create a key with this provider** button that opens the right page in your browser. Never share a key and never paste it in an issue.

**Anthropic (Claude)**: [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys).
1. Sign in at [platform.claude.com](https://platform.claude.com/) (create an account if needed) and open the API keys page.
2. **Create key**, give it a name, choose an expiration and the linked account (yourself).
3. The Console shows the full key (it starts with `sk-ant-`) **only once**: copy it.
4. Spending cap: your monthly **spend limit** is under [Settings > Spend limits](https://platform.claude.com/settings/spend-limits); you can ask for a higher tier on the Rate limits page.
5. Not verified: the exact steps to add credit or a payment method (the pages we read do not describe them).
- Price per million tokens (input / output), [pricing page](https://platform.claude.com/docs/en/about-claude/pricing): Claude Sonnet 5.5 $2 / $10 (COACH default), Haiku 4.5 $1 / $5, Opus 5.5 $4 / $20. Prompt-cache reads are billed at 0.05 x the input price on Sonnet 5.5 (cache writes at 1.25 x).
- Sources: [Get your Claude API key](https://platform.claude.com/docs/en/get-api-key), [API overview](https://platform.claude.com/docs/en/api/overview).

**OpenAI**: [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
1. Sign in, open the API keys page and create a secret key; store it somewhere safe.
2. Billing: [platform.openai.com/account/billing/overview](https://platform.openai.com/account/billing/overview). The quickstart says the first test request is free and recommends adding credits to continue; it states no minimum amount.
3. Spending cap: OpenAI documents two controls, a **spend alert** (notifies only, traffic continues) and a **hard spend limit** (requests then return error 429). Usage tiers are under [Settings > Organization > Limits](https://platform.openai.com/settings/organization/limits). Not verified: the exact menu path of the hard limit (the page points to a separate "spend limits" guide).
- Price per million tokens (input / output), [pricing page](https://developers.openai.com/api/docs/pricing): gpt-4o $2.50 / $10 (COACH default), gpt-4o-mini $0.15 / $0.60, gpt-4.1 $2 / $8, gpt-4.1-mini $0.40 / $1.60.
- Sources: [quickstart](https://developers.openai.com/api/docs/quickstart), [rate limits](https://developers.openai.com/api/docs/guides/rate-limits).

**Google Gemini**: [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
1. Sign in with a Google account and accept the terms: AI Studio creates a default Google Cloud project and an API key for new users. Existing Google Cloud users import their project first (Dashboard > Projects > Import projects), then create a key on the API Keys page.
2. A free tier exists (strict limits; imported projects may need verification). For the paid tier you set up billing in Google Cloud.
3. Spending cap: Google advises **billing alerts** in the Google Cloud console. We found no hard cap in the page we read: an alert warns you, it does not stop spending.
- Price per million tokens, paid tier, [pricing page](https://aistudio.google.com/docs/pricing): gemini-2.5-flash $0.30 input / $2.50 output (COACH default), gemini-2.5-pro $1.25 / $10 for prompts up to 200k tokens.
- **Heads-up**: that page says both 2.5 models are deprecated and are redirected to other models, billed at those models' rates, from 1 December 2026. After that date set `Model` in COACH to the current model you want.
- Source: [API key page](https://aistudio.google.com/docs/api-key).

**Mistral AI**: [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys).
1. You need an account on a plan with API access and a payment method (Admin > Billing, "Set up billing").
2. API Keys page > **New key**, name it, set an expiration, choose the connector scope (**Shared connectors only** is enough), create, and copy the key: it appears only once.
3. Spending cap: Admin Panel > Subscriptions and Billing > your workspace > set a **monthly budget in USD**. Past it, requests return 429 until the next billing cycle.
- Price: Mistral Large $0.50 per million input tokens and $1.50 output, as shown on [mistral.ai/pricing](https://mistral.ai/pricing). Not verified: Mistral Small (not listed there).
- Sources: [API key quickstart](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key), [workspaces and limits](https://docs.mistral.ai/getting-started/quickstarts/admin/manage-workspaces).

**OpenRouter**: [openrouter.ai/keys](https://openrouter.ai/keys).
1. Create a key: give it a name and choose a **credit limit** (or no limit). OpenRouter's documentation strongly recommends a limit on every key; limits can reset daily, weekly or monthly. Once a key reaches its limit, its requests are rejected.
2. Not verified: how to buy credits and OpenRouter's fees (not in the page we read). Model prices depend on the model you pick: look them up on openrouter.ai.
3. In COACH, enter a model name from the OpenRouter catalogue, or leave it empty for the automatic choice.
- Source: [authentication docs](https://openrouter.ai/docs/api-reference/authentication).

**Ollama (local, no key)**: [ollama.com/download](https://ollama.com/download).
1. Install Ollama, then in a terminal download a model: `ollama pull qwen2.5:7b` (the one COACH suggests; any model Ollama offers works).
2. Keep Ollama running. In COACH choose **Ollama**; the address `http://127.0.0.1:11434/v1` is the local server's OpenAI-compatible address (Ollama ignores the API key locally).
3. Free, but it needs a computer able to run the model, and answers are slower and less accurate than the big cloud models. The suggested model cannot read meal photos and tool use varies by model: not verified for every model.
- Source: [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

In COACH: **COACH > Settings**, pick the provider, paste the key (the field is masked), optionally set a model (empty = the one COACH recommends), set the budget, **Save and restart**.

### Cap your spending, twice

1. **At the provider** (the real safety net): a monthly limit or prepaid credit, as above. Providers differ: some stop at the limit, others only alert.
2. **In COACH**: the monthly budget (default **5 EUR**). Once COACH's own estimate reaches it, AI calls are refused until next month; everything else keeps working. *Profile > Preferences > AI cost this month* shows the estimate; it is computed from public prices, the provider's invoice is authoritative.

### Typical cost, with the calculation

Measured on the real prompts (a demo account in the test suite): the weekly review sends a system message of about 38,600 characters (rules and sources) and the chat about 41,900 characters, plus a short context. The reply limits in the code are 1,400 tokens (review) and 700 (chat). Tokens are **estimated** at 3.5 characters per token (we could not run each provider's tokenizer: expect +/- 20 %).

Scenario, one person, one week: **1 weekly review + 10 chat messages** in a session. Assumptions: review = 11,000 system tokens + 2,000 of context + 1,000 output; chat = 12,000 system tokens + 1,500 (message and history) + 400 output per message.

With the default Claude Sonnet 5.5 ($2 in / $10 out per million tokens; cache write 1.25 x, cache read 0.05 x, as COACH counts them):

- Review: 11,000 x 2.5 + 2,000 x 2 + 1,000 x 10 = 41,500 -> **$0.042**
- Chat: first message writes the cache (12,000 x 2.5 = 30,000), 9 others read it (9 x 12,000 x 0.10 = 10,800), plus 10 x 1,500 x 2 = 30,000 of context and 10 x 400 x 10 = 40,000 of output -> 110,800 -> **$0.111**
- Week: $0.152; month (52/12 weeks): **about $0.66, roughly 0.59 EUR** (at COACH's prudent rate of 0.90 EUR per USD).

Same scenario, other models (no prompt-cache discount assumed, which over-estimates when the provider caches automatically):

| Model | Approx. per month |
|---|---|
| Claude Haiku 4.5 ($1 / $5) | 0.32 EUR |
| GPT-4o ($2.50 / $10) | 1.64 EUR |
| GPT-4.1 mini ($0.40 / $1.60) | 0.26 EUR |
| Gemini 2.5 Flash ($0.30 / $2.50) | 0.22 EUR |
| Mistral Large ($0.50 / $1.50) | 0.32 EUR |
| Ollama (local) | 0 |

So a light user stays well under the default 5 EUR budget. Not included and not measured: the chat can call history-search tools (extra model rounds, which can roughly double the chat cost), meal-photo estimates (cheap model, photo tokens not verified), the intake questions, and heavier use. The in-app counter shows the real figure.

### If the AI says "not configured"

- Open **COACH > Settings** and check a provider other than **None** is selected and a key is stored ("A key is already stored" is shown).
- Paste the key again (no spaces or line breaks); a key from the wrong provider is refused by that provider.
- Check billing/credit on the provider's site, and that your COACH monthly budget is not used up.
- Ollama: check it is running (`ollama list`) and the model name matches.
- Linux: if saving the key fails, install and unlock a keyring (GNOME Keyring or KWallet), or use Ollama / None.

## What is left to fill in

Nothing is mandatory except your account and the health notice. In order:

1. **Local account**: e-mail-style identifier and password (kept on this computer only).
2. **Essential questions** (about 13 screens at most): sports, goals, age, sex, height, weight, health notice and red flags, training days, session length, injuries, running volume and strength level. Why: the rule engine needs them to size a plan safely. You can skip all but the health notice; skipped answers make the plan more cautious or generic.
3. **The coach's follow-up questions** (only with an AI): it asks at most a few missing questions with the reason for each. Without an AI, COACH asks the remaining required ones itself.
4. **Goals**: a target event with a date, or a general objective. A dated goal gives the plan its phases.
5. **Generate the plan**: from the home screen. The first plan comes out of the rules, with the rule ids cited on each session.
6. **Nutrition and weight**: enter your weight regularly and, if you want, log meals (barcode and text; photo estimate needs an AI with vision). Targets and weight-trend feedback are computed by rules.
7. **Garmin watch (optional)**: Profile, then Garmin. Enter your Garmin Connect credentials once: only encrypted tokens are kept (the encryption key lives in your keyring). For another brand, import FIT/TCX/GPX files ([docs/activity-import.md](activity-import.md)). The Garmin library is unofficial, use is at your own risk.
8. **Language and theme**: in the Profile (language of the app, of the coach and of the e-mails; light, dark and eco themes).
9. **Reminders (optional)**: in **COACH > Settings > Reminders by ntfy or e-mail** you can give the address of an [ntfy](https://ntfy.sh) server and its access token (COACH only sends to ntfy with a token), and/or an SMTP server (host, port, user, password, sender). Passwords and tokens go to the system keyring. Tick *Send automatically* and pick an hour for the daily check-in and weekly digest. Then each person chooses their ntfy topic or turns e-mail on in *Profile > Notifications* and can send a test. Browser push notifications and desktop pop-ups are not offered (see [Known limits](#known-limits)).

<img src="img/plan-light.png" width="240" alt="Weekly plan">

## Where your data lives

| What | Windows | Linux / macOS |
|---|---|---|
| Data folder | `%APPDATA%\io.github.ecgrudyglt.coach` | `~/.local/share/io.github.ecgrudyglt.coach` (macOS: `~/Library/Application Support/io.github.ecgrudyglt.coach`) |

Inside: `coach.db` (everything: accounts, plans, logs), `media/` (photos, cached exercise images), `settings.json` (provider, model, budget: no key), `logs/sidecar.log` (server log, replaced at each start). Open it from **COACH > Open data folder**. The AI key and the Garmin encryption key are in the OS keyring (service `COACH`).

## Back up and restore

- **Back up**: **COACH > Back up my data...** saves a dated archive `coach-backup-YYYY-MM-DD.zip` containing a consistent copy of the database (`coach.db`, made with SQLite's backup function, safe while COACH runs) and the `media/` folder (photos). Keep it somewhere other than this computer too. Your AI key, ntfy token and SMTP password are not in it (nor in any file): you re-enter them after a reinstall.
- **Restore**: 1. close COACH; 2. in the data folder, move `coach.db` (and `coach.db-wal` / `coach.db-shm` if present) and `media/` aside; 3. unzip your archive into the data folder (you get `coach.db` and `media/`); 4. start COACH. On another computer, Garmin tokens will not decrypt (their key stays in the old keyring): reconnect Garmin.

## Update

**COACH > Check for updates...** looks (one anonymous request to GitHub's public API, no account, nothing about you is sent) for the latest published `desktop-v*` release and compares it with your version. If it is newer:

- **Windows, macOS and Linux AppImage**: COACH offers to **install it now**. It downloads the update from that release's `latest.json`, **verifies its signature** against the update public key built into the app, stops its local server, installs, and restarts. Nothing is installed without your confirmation, and an update whose signature does not match is refused. If anything fails (network, signature, rights), COACH starts again as before and opens the download page for a manual install.
- **Linux `.deb`** (installed through the package manager): COACH opens the download page; install the new `.deb` as in step 3.

Make a backup first. Your data and settings stay; database migrations run at the next start. COACH never checks by itself in the background: the check happens only when you click the menu entry, so to "turn updates off" simply do not use it.

How the signature works: every release contains `latest.json` and one `.sig` file per update package, produced in the project's CI with a dedicated update-signing private key (stored only in the maintainer's secret vault and in the repository's GitHub secrets). The matching public key is embedded in the app (`desktop/src-tauri/tauri.conf.json`):

```
dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEIyQzc0RDNEMDY4MkI5MUUKUldRZXVZSUdQVTNIc2pNaStxdnExblVCeWJaZUhOMVQrUG1yRzVvZkVqa09DU00zaTlUd3I0YlAK
```

It is independent from any code-signing certificate (the installers stay unsigned: see SmartScreen and Gatekeeper above). If the private key is ever lost or leaked, a release signed with a new key cannot be installed by apps that embed the old public key: the maintainer must then publish a version **manually** (download and install it yourself, as the first time) that embeds the new public key; from that version on, automatic updates work again. Only an app that already trusts the key will install an update, which is why the first install is always manual and checked with SHA-256.

## Uninstall

- Windows: *Settings > Apps > COACH > Uninstall*.
- Linux: delete the AppImage, or `sudo apt remove coach`.
- macOS: drag COACH from Applications to the Bin.

Your data folder is **not** deleted (so a reinstall finds everything). To erase everything: delete the data folder, and remove the `COACH` entries from the keyring (Windows: Credential Manager, Windows Credentials; macOS: Keychain Access; Linux: "Passwords and Keys" or KWalletManager).

## Known limits

| Limit | Status |
|---|---|
| Installers not code-signed | **Remains** (the update packages are signed, with a separate key). Signing needs a certificate that costs money; see [SmartScreen](#windows-and-the-smartscreen-warning) and [macOS](#macos-and-gatekeeper). A free route for open source (SignPath Foundation) is noted in [desktop/README.md](../desktop/README.md) but not applied for. |
| Automatic update | **Added**: *Check for updates...* downloads, verifies and installs on Windows, macOS and Linux AppImage (not `.deb`). It is not silent and not in the background. Not yet tested across two real releases (see the maintainer notes). |
| Browser push and desktop pop-up notifications | **Remains.** Web push needs a push service tied to a web origin, which the embedded local address cannot register; the app has no bridge to native pop-ups. ntfy (on your phone) and e-mail work instead. |
| Backup of photos | **Fixed**: the archive includes `media/`. |
| macOS | **Added**, unsigned, interface never run by the maintainers on a Mac. |
| Windows and macOS interface | Built by the CI but **not run** by the maintainers. The Linux server part was tested end to end. |
| Phone access | Not possible with the desktop app (local only); use the Docker install. |

## Troubleshooting

| Symptom | What to do |
|---|---|
| "COACH could not start" | Read `logs/sidecar.log` in the data folder; click **Retry**. Security software may block the first start of the bundled server: allow COACH. |
| Very slow first start | Normal for a few seconds (the server unpacks itself). Over a minute: see the log. |
| Nothing opens, window stays blank | Close it from the system tray / task manager; start again. Only one COACH can run at a time. |
| Linux: AppImage does not start | Install `libfuse2`, or use the `.deb`. |
| Linux: key cannot be saved | Install and unlock GNOME Keyring or KWallet, or choose Ollama / None. |
| Windows: "Windows protected your PC" | See [SmartScreen](#windows-and-the-smartscreen-warning). |
| macOS: "cannot be opened" / "is damaged" | See [Gatekeeper](#macos-and-gatekeeper). |
| Forgot the AI key | You cannot read it back by design: create a new one at the provider and paste it in Settings. |

Bugs and questions: [issues](https://github.com/ECG-Rudy-Glt/COACH/issues). Never paste your keys, your database or health data there. To build the installers yourself, see [desktop/README.md](../desktop/README.md).
