# Exposing COACH to your phone and the Internet

COACH holds health data. The safest design is **not to expose it publicly at all**: reach it through a private network (VPN). Public exposure is supported, but read [security.md](security.md) first.

## Pick a path

| Option | Public Internet? | Needs open ports? | Gives HTTPS (needed for PWA install & push)? | Best for |
|---|---|---|---|---|
| **A. Tailscale / WireGuard (VPN)** | no | no | yes with `tailscale serve` | **recommended** — only your own devices can connect |
| **B. Cloudflare Tunnel** (+ Access) | yes (behind Cloudflare) | no (outbound only) | yes (Cloudflare certificate) | reaching it from anywhere without a VPN app, family sharing |
| **C. ngrok** | yes (random/static URL) | no | yes | demos and quick tests, not a permanent home |
| **D. Reverse proxy + port-forward** (Caddy profile) | yes | 80 + 443 | yes (Let's Encrypt) | you own a domain and accept the exposure |
| **E. LAN only** | no | no | **no** | trying it out on your desk |

> **HTTPS is mandatory for the phone experience.** Browsers only allow service workers, "Install app" and push notifications in a *secure context*. `http://192.168.x.x:8000` works for a quick look but cannot be installed or receive push. `http://localhost` is the only plain-HTTP exception.

## Before any exposure — checklist

- [ ] Create your accounts, then keep `REGISTRATION=first` (default) or `closed`.
- [ ] Strong, unique passwords (10+ characters enforced; use a password manager).
- [ ] `ALLOWED_HOSTS=your.domain,localhost` in `.env`.
- [ ] `TRUST_PROXY=1` (compose default) **only** when every request goes through your proxy/tunnel; keep `APP_BIND=127.0.0.1` so nothing bypasses it.
- [ ] `COOKIE_SECURE=1`.
- [ ] `LLM_MONTHLY_BUDGET_EUR` set to a value you accept losing.
- [ ] Backups running (`--profile backup`) and tested.
- [ ] You know where `secrets/` lives and it is not in any synced/cloud folder.

## A. Private network (recommended)

### Tailscale (simplest)

1. Install Tailscale on the server and on your phone; sign in to the same tailnet.
2. In the Tailscale admin console enable **MagicDNS** and **HTTPS Certificates**.
3. On the server:
   ```sh
   tailscale serve --bg --https=443 http://127.0.0.1:8000
   ```
4. Open `https://<machine>.<tailnet>.ts.net` on the phone (Tailscale connected). You get a real Let's Encrypt certificate, so Safari/Chrome install the PWA and push works.
5. Set `ALLOWED_HOSTS=<machine>.<tailnet>.ts.net,localhost` and `COOKIE_SECURE=1`.

Do **not** use `tailscale funnel` unless you deliberately want the public Internet.

### WireGuard / OpenVPN / ZeroTier

Same idea, but you must provide the certificate: either run the Caddy profile with a domain you own and a DNS record pointing to the *VPN* address, or use Caddy's internal CA and install its root certificate on the phone (see [pwa.md](pwa.md#self-signed-or-private-ca)).

## B. Cloudflare Tunnel

Outbound-only connection from your server to Cloudflare: no port to open, your home IP stays hidden.

1. Cloudflare Zero Trust → Networks → Tunnels → create a tunnel, copy the token, add a public hostname `coach.example.org` → service `http://app:8000`.
2. Add a service to a `docker-compose.override.yml` (same `edge` network as the app; keep the token out of git):
   ```yaml
   services:
     cloudflared:
       image: cloudflare/cloudflared:latest
       restart: unless-stopped
       command: tunnel --no-autoupdate run
       environment:
         TUNNEL_TOKEN: ${CLOUDFLARED_TOKEN}      # in .env, which is git-ignored
       networks: [edge]
   ```
3. `.env`: `ALLOWED_HOSTS=coach.example.org,localhost`, `TRUST_PROXY=1`, `COOKIE_SECURE=1`.
4. **Strongly recommended:** add a Cloudflare **Access** policy (Zero Trust → Access → Applications) so only your e-mail/identity provider can even reach the login page. It is a second authentication layer in front of COACH.

Trade-off: Cloudflare terminates TLS, so it can technically see the traffic (including health data). Decide whether that is acceptable; the VPN option has no such third party.

## C. ngrok

```sh
ngrok http 8000 --domain=your-static-name.ngrok-free.app   # static domain avoids a new URL each run
```
- Use ngrok's built-in authentication (OAuth or IP restrictions) — without it the login page is public.
- Free plans may show an interstitial page and rotate URLs, which breaks installed PWAs and push subscriptions. Treat ngrok as a **demo** tool.
- Same `.env` settings as above (`ALLOWED_HOSTS` with the ngrok host, `TRUST_PROXY=1`, `COOKIE_SECURE=1`). Same caveat on TLS termination.

## D. Reverse proxy and port-forward

```sh
# .env:  DOMAIN=coach.example.org   ALLOWED_HOSTS=coach.example.org   COOKIE_SECURE=1   APP_BIND=127.0.0.1
docker compose --profile https up -d
```
Requirements: a DNS `A/AAAA` record for `DOMAIN` (use a DDNS client if your IP changes), router forwarding **80 and 443** to the server, a firewall that allows nothing else. Caddy obtains and renews the certificate and adds security headers.

Strongly consider adding: CrowdSec or fail2ban on the Caddy logs, a geo/IP allowlist at the router if you travel rarely, and an authentication layer (Authelia, Authentik, Cloudflare Access) in front.

## Verifying your exposure

```sh
curl -sI https://coach.example.org | grep -i -E "strict-transport|content-security|x-frame"   # headers present
curl -s  https://coach.example.org/docs -o /dev/null -w "%{http_code}\n"                        # must be 404
curl -s  https://coach.example.org/auth/status                                                   # registration: "closed"
```
From outside your network, `nmap -Pn <public-ip>` should show nothing open for options A–C and only 80/443 for D.
