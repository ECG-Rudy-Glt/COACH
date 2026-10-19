# Installing COACH as an app (PWA)

COACH is a Progressive Web App: no app store, no download. It must be opened over **HTTPS** (see [exposure.md](exposure.md)) — otherwise "Install" and push notifications are not offered.

What you get once installed: its own icon, full-screen window without browser chrome, an offline shell (the interface opens without network; data needs the server), and notifications.

## iPhone / iPad (Safari)

Requires iOS/iPadOS 16.4+ for notifications from installed web apps (installation itself works on older versions).

1. Open `https://your-address` in **Safari** (other iOS browsers can add to the home screen from 16.4, but Safari is the reference).
2. Tap the **Share** button (square with an arrow) → **Add to Home Screen** → **Add**.
3. Launch COACH **from the new icon** (not from Safari) and sign in.
4. Notifications: Coach → *Notifications et conseils par mail* → enable the phone notifications and accept the iOS prompt. iOS only allows push for apps launched from the home screen. Settings → Notifications → COACH must be allowed.
5. Update: the app revalidates on every launch. If something looks stale, close it from the app switcher and reopen.

Troubleshooting
- *"Add to Home Screen" is missing:* you are in a private tab or an in-app browser; open the link in Safari proper.
- *Push never arrives:* the `VAPID_SUBJECT` must be a real `mailto:`/`https://` contact (Apple rejects the others), and the server needs `VAPID_PUBLIC_KEY` + `secrets/vapid_private_key` (`scripts/init-secrets.sh --vapid`).
- *Certificate warning:* see [Self-signed or private CA](#self-signed-or-private-ca).

## Android — Samsung Internet (Samsung phones)

1. Open the address in **Samsung Internet**.
2. Tap the menu **≡** (bottom right) → **Add page to** → **Home screen**. On recent versions an **install icon** also appears in the address bar: tap it → **Install**.
3. Confirm; the icon appears on the home screen/app drawer. Open it and sign in.
4. Notifications: Coach → *Notifications et conseils par mail* → enable the phone notifications → **Allow**.
5. Keep reminders reliable: Settings → Battery and device care → Battery → *Background usage limits* → make sure the browser is **not** in *Sleeping/Deep sleeping apps*; allow notifications in Settings → Apps → Samsung Internet → Notifications.

## Android — Chrome (any other phone, also works on Samsung)

1. Open the address in Chrome.
2. Menu **⋮** → **Install app** (or **Add to Home screen**) → **Install**.
3. Open from the icon, sign in, enable push in Coach → *Notifications et conseils par mail*.

## Desktop (Chrome, Edge)

Address-bar **install icon** (⊕) → **Install**. Safari 17+ on macOS: File → **Add to Dock**.

## Self-signed or private CA

If you run your own certificate authority (Caddy internal CA, step-ca, mkcert) the phone must trust it, otherwise Safari/Chrome refuse to install the app and service workers do not register.

- **iPhone:** send the root certificate to the phone (AirDrop/e-mail/HTTPS link), open it → *Settings → Profile Downloaded → Install*, then **Settings → General → About → Certificate Trust Settings → enable full trust** for it.
- **Samsung/Android:** Settings → Security and privacy → More security settings → Install from device storage → **CA certificate**. Note: Android Chrome trusts user CAs, but some apps and Samsung Internet versions may not; a public certificate (Tailscale `ts.net`, Cloudflare, Let's Encrypt) avoids all of this.

Prefer a real certificate (Tailscale HTTPS, Let's Encrypt via the Caddy profile): no device configuration at all.

## Uninstall

iPhone: long-press the icon → Remove App. Android: long-press → Uninstall (or App info → Uninstall). Signing out first (Profile → *Se déconnecter*) closes the session on the server.
