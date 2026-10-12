# 0018 – Public demo

- Status: accepted
- Date: 2026-10-12

## Context
People want to try an invoicing program before they install it. A public demo has to show
real-looking data for each country, stay usable when strangers change things, and must not
become a tool for spam or lock visitors out.

## Decision
- **A demo mode of the normal image** (`RHINVOICE_DEMO=true`), not a separate build. The demo is
  tested with every change and shows exactly what users get.
- **One instance per country** (`RHINVOICE_DEMO_COUNTRY`): Rhinvoice has one company per
  installation (ADR 0004). `deploy/demo/` runs CH, DE and AT behind Caddy, with one Postgres and
  one Gotenberg.
- **A fresh start every hour and at every start.** `rhinvoice serve` drops and rebuilds the schema,
  creates the demo login, the demo company of the country and the demo data (ADR 0017's profiles
  pick currency, VAT number and bank account), and hides the setup checklist. Dates follow
  today, so the cockpit always looks current.
- **Never a real installation:** the setting must be switched on explicitly, and the first reset
  refuses a database with any user besides the demo login. It marks the database as a demo (a
  comment on the database); later resets go by the mark, so a user who slipped in never blocks
  the demo. While a reset runs, the API answers 503, so nobody gets into the empty database.
- **What would hurt others is refused** with `403 demo_locked`: first-user setup, password,
  two-factor authentication, logo, mail server, sending mail, backups, and moving the company to
  another country; the interface shows a note there. Recurring invoices are not written.
  Everything else stays open; the hourly reset undoes it.
- **Limits instead of a lockout:** failed logins do not lock the shared login. Each client
  address may log in 10 times and change something 60 times a minute (in the app, as the
  demo ships without a rate-limiting proxy), and argon2 runs at most twice at a time in every
  installation, so a burst of logins waits instead of exhausting the memory.
- **Isolated:** apps, Gotenberg and Postgres have no internet access; each demo has a database
  role of its own without superuser rights.
- **Not for search engines:** `X-Robots-Tag: noindex, nofollow` on every response.
- **The login is public:** `GET /api/demo` tells the login page the login and the other countries'
  demos, and the page logs in with one click.

## Consequences
- Visitors share one login and see each other's changes for up to an hour. That is stated on the
  login page and in a strip on every page.
- Free-text abuse (offensive names) is possible until the next reset; logos are refused because
  images are worse. Floods from many addresses are left to the hoster's firewall.
- The demo needs a server of its own; it must not run next to real data.
