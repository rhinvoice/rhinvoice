# Public demo

This folder runs the public demo of Rhinvoice: one instance each for Switzerland, Germany and
Austria, at `ch.`, `de.` and `at.` your demo domain, with HTTPS from Let's Encrypt.

Each instance runs with `RHINVOICE_DEMO=true`:
- **Reset every hour, and at every start.** The database is emptied and filled again with a demo
  company of the country, a shared login and about 21 months of invoices, quotes and payments
  dated up to today. While a reset runs (a few seconds) the API answers 503, and visitors are
  logged out afterwards.
- **One click to log in.** The login page shows the login, a button to open the demo, and links
  to the other countries. A strip on every page says that it is a demo.
- **Some things are refused:** setting up a first user, changing the password, two-factor
  authentication, the logo, the mail server, sending any mail, backups, and changing the
  company's country. They would lock other visitors out or send mail from the demo; the
  interface shows a note instead. Recurring invoices are not written.
- **No lockout, but limits:** failed logins do not lock the shared login. Instead each client
  address may log in 10 times and change something 60 times per minute; argon2 runs at most
  twice at a time, so a flood of logins waits instead of exhausting the memory.
- **Isolated:** the apps, Gotenberg and Postgres sit on an internal network without internet
  access; only Caddy is reachable. Each demo has its own database role without superuser
  rights.
- **Not indexed:** every response says `X-Robots-Tag: noindex, nofollow`.

The first reset refuses a database that has any user besides the demo login, and marks the
database as a demo (a comment on the database). Later resets go by that mark, so nobody who
slipped in can block the demo; a database with real data never has it. Even so, never point
`RHINVOICE_DEMO` at a database with real data.

## Server

A small VPS is enough, for example Hetzner CX22 (2 vCPU, 4 GB RAM) with Debian or Ubuntu and
Docker. Keep the demo off servers that hold real data: anyone on the internet can use it.

1. **DNS:** point `ch.<domain>`, `de.<domain>` and `at.<domain>` (A and AAAA records) at the
   server, e.g. `ch.demo.rhinvoice.com`.
2. **Firewall:** open only 22 (SSH), 80 and 443.
3. **Docker:** install Docker Engine with the compose plugin
   (<https://docs.docker.com/engine/install/>).
4. **Files:**

   ```bash
   mkdir rhinvoice-demo && cd rhinvoice-demo
   for file in compose.yml Caddyfile init-databases.sh .env.example; do
     curl -fsSLO "https://raw.githubusercontent.com/rhinvoice/rhinvoice/main/deploy/demo/$file"
   done
   chmod +x init-databases.sh
   cp .env.example .env
   ```

5. **Settings:** in `.env`, set `DEMO_DOMAIN`, `ACME_EMAIL` and a long random
   `POSTGRES_PASSWORD`. `RHINVOICE_IMAGE` must be a release with the demo mode (0.4.0 or later):
   an older image would start an ordinary, empty installation.
6. **Start:**

   ```bash
   docker compose up -d
   docker compose logs -f caddy   # the certificates arrive within a minute
   ```

Then open `https://ch.<domain>`.

## Operation

- **Update:** change `RHINVOICE_IMAGE` in `.env`, then run `docker compose up -d`. The new
  version starts with a fresh demo.
- **Reset now:** `docker compose restart app-ch app-de app-at`.
- **Another interval:** set `DEMO_RESET_INTERVAL` (seconds, at least 300).
- **Load:** each app and Postgres are limited to 512 MB, Gotenberg to 1 GB, Caddy to 256 MB.
  The rate limits above are per app; against floods from many addresses, use the hoster's
  firewall or DDoS protection.
- **Logs:** `docker compose logs -f app-ch`. A failed reset is logged and tried again at the
  next interval; a start whose reset fails stops, and the log says why.

## Trying it on your machine

Caddy issues local certificates for `*.localhost`:

```bash
docker build -t rhinvoice:local ../..
DEMO_DOMAIN=localhost ACME_EMAIL=me@example.org POSTGRES_PASSWORD=demo \
  RHINVOICE_IMAGE=rhinvoice:local docker compose -p rhinvoice-demo up -d
```

Open `https://ch.localhost` and accept the local certificate.
