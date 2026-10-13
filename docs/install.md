# Installation

Rhinvoice runs as four containers: the app (web interface and API), PostgreSQL, Gotenberg (PDFs)
and the backup. You only need
[Docker](https://docs.docker.com/get-docker/) with Docker Compose – no source code, no Python or Node.js.

> Rhinvoice is in early development (0.x). Tax rates and rules are provided without warranty and do not
> replace tax advice.

## 1. Download

```bash
mkdir rhinvoice && cd rhinvoice
curl -fsSLO https://raw.githubusercontent.com/rhinvoice/rhinvoice/v0.5.2/deploy/compose.yml
curl -fsSL https://raw.githubusercontent.com/rhinvoice/rhinvoice/v0.5.2/.env.example -o .env
```

## 2. Configure

Edit `.env`:

| Setting | Value |
|---|---|
| `POSTGRES_PASSWORD` | a long random value, letters and digits only (e.g. `openssl rand -hex 24`) |
| `RHINVOICE_VERSION` | the version to run, e.g. `0.5.2` – pinned versions only change when you change them |
| `RHINVOICE_PORT` | port on this machine, default `8000` |
| `RHINVOICE_COOKIE_SECURE` | keep `true`; use `false` only for plain HTTP in a trusted network (not needed for `localhost`) |

## 3. Start

```bash
docker compose pull      # fetch the images of the version in .env
docker compose up -d
docker compose ps        # "healthy" after a few seconds
```

`docker compose pull` matters when an older image of the same name is already on the computer
(e.g. from an earlier test): `up` alone would start that one instead of downloading.

Open <http://rhinvoice.localhost:8000> (or <http://127.0.0.1:8000>). Every name ending in
`.localhost` points to your own computer, so this needs no entry in `/etc/hosts`; browsers treat it
as secure, so logging in works without HTTPS. With `RHINVOICE_PORT=80` in `.env` the address is
simply <http://rhinvoice.localhost> (if nothing else uses port 80).

An even shorter address on your own laptop, `http://rhinvoice:8000`, needs two changes: a hosts
entry, and cookies over plain HTTP, because browsers treat only `localhost` names as secure without
HTTPS. Do this only while Rhinvoice listens on this computer alone (`RHINVOICE_BIND=127.0.0.1`,
the default), never on a network or a server:

```bash
echo "127.0.0.1 rhinvoice" | sudo tee -a /etc/hosts   # once; on Windows: C:\Windows\System32\drivers\etc\hosts
# in .env:
RHINVOICE_COOKIE_SECURE=false
docker compose up -d
```

The first visit asks you to create the first user account. Alternatively:

```bash
docker compose exec app rhinvoice user create --email you@example.com --name "Your Name"
```

Then enter your company details and a bank account under **Settings** and create your first invoice
(key `N`).

### Trying it out with demo data

On a test installation, finish the first-start wizard (country and company), then fill it with
invented customers, articles and about 21 months of invoices, payments, overdue invoices and
quotes, so the overview and the lists have something to show:

```bash
docker compose exec app rhinvoice demo                      # or: make demo
docker compose exec app rhinvoice demo --without-documents  # customers and articles only
```

The command only runs on an installation without customers and documents, so it never mixes with
real data. When no bank account exists yet it adds the official example accounts of SIX or the ECBS;
replace them before sending real invoices.

A public demo that resets itself every hour (one per country, behind HTTPS) is described in
[`deploy/demo/README.md`](../deploy/demo/README.md).

The stack has three containers: `app` (Rhinvoice), `db` (PostgreSQL) and `gotenberg`, which turns
documents into PDFs. Gotenberg has no port of its own and makes no requests to the internet; only
the app talks to it. Without it, everything works except PDF download and printing.

### Sending by e-mail

Invoices, quotes and reminders can be sent from Rhinvoice with their PDF attached. Enter the
outgoing mail server (SMTP) of your e-mail provider once under **Settings → E-mail** and send a
test mail; the provider's help pages list server, port and encryption (e.g. Microsoft 365:
`smtp.office365.com`, port 587, STARTTLS). Gmail and iCloud need an app password. The app
container needs to reach that server: allow outgoing connections on port 587 or 465 if a firewall
is in between. Mails go out right away; a refused mail shows the server's answer.

### Recurring invoices

Plans under **Invoices → Recurring** write their invoices by themselves: the app looks for due ones
a minute after it starts and then every ten minutes. Set `RHINVOICE_RECURRING_INTERVAL` (seconds,
at least 60) to look more or less often, or `RHINVOICE_RECURRING=false` to switch it off and run
`docker compose exec app rhinvoice recurring` yourself (e.g. from cron). Each period is written
once, also with several app containers; periods missed while the app was stopped are caught up.

## Updating

```bash
# set RHINVOICE_VERSION in .env to the new version, then
docker compose pull
docker compose up -d
```

Database migrations run automatically on start (`RHINVOICE_RUN_MIGRATIONS=true`). Read the
[changelog](../CHANGELOG.md) before updating.

## Stopping

```bash
docker compose down          # stop; the data stays in the volume "rhinvoice_db-data"
docker compose up -d         # start again, with all data
```

## Uninstalling

Removing Rhinvoice deletes all invoices, customers and settings for good. Issued invoices usually
have to be kept for ten years (CH: OR 958f, DE: § 147 AO, AT: § 132 BAO), so keep their PDFs or a
backup outside of Docker first:

```bash
docker compose exec backup rhinvoice-backup backup   # a last backup, if you set one up (backup.md)
```

Then, in the folder with `compose.yml` and `.env`:

```bash
docker compose down --volumes --rmi all    # containers, network, data volumes and images
cd .. && rm -r rhinvoice                   # compose.yml and .env (holds the database password)
```

`--volumes` deletes the database (`rhinvoice_db-data`) and the backup volumes
(`rhinvoice_backup-*`), including the stored Dropbox or Google Drive access. Backups in the default
local volume go with them; a folder set as `BACKUP_LOCAL_DIR`, S3, SFTP and cloud targets are not
touched – delete those yourself when you no longer need them. `--rmi all` removes the images of Rhinvoice, its backup, PostgreSQL
and Gotenberg; Docker keeps an image that another project still uses and says so – that is fine.

For an installation with a name of its own (see below), run the command in its folder when the
name is in its `.env` (`COMPOSE_PROJECT_NAME`), else add it: `docker compose -p rhinvoice-try down
--volumes --rmi all`. The checks below then look for that name instead of `rhinvoice`.

Check that nothing is left:

```bash
docker ps -a --filter name=rhinvoice                   # containers: none
docker volume ls --filter name=rhinvoice               # volumes: none
docker image ls | grep -E "rhinvoice|gotenberg"        # images: none
```

If something is still listed, e.g. images of older versions that `--rmi all` does not know:

```bash
docker image rm $(docker image ls -q --filter "reference=ghcr.io/rhinvoice/*")
docker volume rm rhinvoice_db-data                     # one by one, as listed
```

Docker Desktop shows the same under *Containers*, *Images* and *Volumes*, each with a delete
button.

## Running it on a server

- Put a TLS reverse proxy (Caddy, Traefik, nginx) in front and keep `RHINVOICE_BIND=127.0.0.1`.
- Set `RHINVOICE_FORWARDED_ALLOW_IPS` to the proxy's address and let the proxy send
  `Strict-Transport-Security`.
- Session cookies are `Secure` by default; set `RHINVOICE_COOKIE_SECURE=false` only when you
  deliberately use plain HTTP in a trusted network.
- Login attempts are limited per account; add per-IP rate limiting in the proxy when the instance
  is reachable from the internet, and turn on two-factor authentication for every user.
- Set up backups: [backup.md](backup.md).

## Several installations on one computer

Each installation needs a folder, a port and a **project name** of its own, so that containers and
data stay apart. Give the name with `-p`, in every command for that installation:

```bash
RHINVOICE_PORT=8100 docker compose -p rhinvoice-try up -d
docker compose -p rhinvoice-try ps
docker compose -p rhinvoice-try logs -f app
docker compose -p rhinvoice-try down -v      # remove it again, with its data
```

Easier: write the name and the port into that folder's `.env` once (the `.env.example` has the
line `COMPOSE_PROJECT_NAME=rhinvoice` for this); then the plain commands work there:

```
COMPOSE_PROJECT_NAME=rhinvoice-try
RHINVOICE_PORT=8100
```

Open it at <http://rhinvoice.localhost:8100>.

## Images

Images are published for `linux/amd64` and `linux/arm64` (e.g. Apple Silicon, Raspberry Pi 4/5) at
`ghcr.io/rhinvoice/rhinvoice:<version>`. PDFs come from the official `gotenberg/gotenberg` image (pinned in
`deploy/compose.yml`).

Own document layouts: most needs are covered by *Settings → Print template* (three templates, logo,
font, footer). For a layout of your own, mount a folder and set `RHINVOICE_THEME_DIR` to it; files
there replace the built-in ones:

- `layout.html.j2` – the page around every document: head, address, footer, Swiss payment part
- `document.html.j2` – the content of invoices, quotes and cancellations
- `reminder.html.j2` – the content of payment reminders
- `document.css` – the styles of all of them

Copy the built-in files from `backend/src/rhinvoice/infrastructure/rendering/templates/` as a start.
A theme that replaces only an old full-page `document.html.j2` keeps working for documents; its
reminders use the built-in layout.
