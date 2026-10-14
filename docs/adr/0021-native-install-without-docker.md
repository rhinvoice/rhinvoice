# 0021 – Installing without Docker

- Status: proposed
- Date: 2026-10-14

## Context
Rhinvoice runs as Docker Compose: app, PostgreSQL, Gotenberg and backup. Small offices without IT
know neither Docker nor a terminal; they expect an installer: download, double-click, done. Docker
Desktop is no way out: it needs admin rights and virtualisation and breaks on updates.

## Decision
A native installer (Windows first, then macOS) ships the same code with its parts as files, no
containers. Docker Compose stays the way for servers and Linux.

| Part | In Docker | Native |
|---|---|---|
| App | Python image | Python bundled (python-build-standalone + uv), the frontend as static files |
| Database | `postgres:17-alpine` | Portable PostgreSQL 17, started by the app on `127.0.0.1` over TCP only |
| PDF | Gotenberg (Chromium) | A local Chromium, driven over the DevTools protocol (`Page.printToPDF`) |
| Backup | restic + rclone | The same two binaries |

- **PostgreSQL stays.** SQLite would need a second implementation of the full-text search
  (`tsvector`), the gapless numbering (`FOR UPDATE`) and the JSONB snapshots, tested twice.
- **The PDF renderer is a second adapter** of the `PdfRenderer` port next to Gotenberg. The PDF/A-3
  conversion (`rendering/pdfa.py`) is already done in Python and stays shared.
- **Secrets are generated on the first start**, nothing to configure.
- **One workplace in the first version** (`localhost`); access from other computers in the office
  needs HTTPS in the local network and is decided later.
- **The backup is set up in the installer**, not optional: the data lies on one computer. The
  simplest target is a folder synced by OneDrive or Dropbox.

## Structure
- **The Docker setup does not change.** With `RHINVOICE_GOTENBERG_URL` set, PDFs come from
  Gotenberg exactly as before; everything below is opt-in.
- **PDF:** `ChromiumPdfRenderer` implements the `PdfRenderer` port once (PDF/A, metadata,
  e-invoice) and hands the page to a `PagePrinter`: `Gotenberg` or `LocalChromium`. The local one
  starts the browser on first use, keeps it running, restarts it after a failure and stops it with
  the program. `RHINVOICE_CHROMIUM_PATH` selects it when no Gotenberg is configured.
- **`rhinvoice.desktop`** is a new top layer above `api` (import-linter); nothing below knows it.
  The program `rhinvoice-desktop` creates `rhinvoice.json` (random database password, port 8000)
  and the database in the user's data folder (`%LOCALAPPDATA%\Rhinvoice`,
  `~/Library/Application Support/Rhinvoice`, `$XDG_DATA_HOME/rhinvoice`), starts PostgreSQL on a
  free port of 127.0.0.1, runs the same server as `rhinvoice serve` and stops the database at the
  end. A server left running by a killed program is restarted; a database missing after an
  interrupted first start is created.
- **Install folder:** `python/` (the bundled interpreter), `postgresql/` (whole distribution),
  `static/` (web interface) and optionally `chromium/` (the whole folder of chrome-headless-shell:
  it finds its data files next to itself, a lone binary does not start). Without it Edge or an
  installed Chrome prints.
- **Database settings** are written to `postgresql.conf` at `initdb` (listen on 127.0.0.1, no Unix
  socket), not passed on the command line, whose quoting differs between Windows and Unix.

- **Security on one computer:** the database and the web interface listen on 127.0.0.1 only;
  the data folder is private to the user (0700), the configuration with the database password
  0600, and only the database clients get the password. The session cookie is not marked secure
  there (plain http on loopback; Safari would drop it). The browser's DevTools port is reachable
  for other programs of the same computer, but not for web pages (`--remote-allow-origins=`); on a
  computer shared by several people (terminal server) that is a risk to weigh before such a setup
  is supported. `--remote-debugging-pipe` would close it, but needs inherited handles that Python
  does not pass on Windows.

## Spike (2026-10-14, macOS arm64)
- **PDF:** All 19 sample invoices (`tests/einvoice_samples.py`) rendered through Gotenberg 8.37.0
  and through `chrome-headless-shell` with the same page options. All local PDFs pass Mustang
  (ZUGFeRD / Factur-X, PDF/A-3). Same page count everywhere; 0.1–0.3 % of the pixels differ on the
  invoice page (anti-aliasing), 1.3–1.4 % on the QR-bill page, whose SVG asks for Arial/Helvetica:
  Gotenberg takes Liberation Sans, macOS Helvetica, Windows would take Arial. All of them are
  allowed by the Swiss QR-bill style guide. The local Chromium was faster (≈ 0.06 s vs 0.09 s).
- **Database:** The portable builds of theseus-rs/postgresql-binaries for macOS lack ICU, which the
  `natural_sort` collation (migrations) needs; their Windows build is the EDB build and ships ICU.
  The binaries of Postgres.app 2.9.6 (PostgreSQL 17, ICU 75, relocatable through `@loader_path`)
  work: all migrations, first user, company, the demo data (72 invoices), full-text search and the
  PDF download ran without Docker.
- The Unix socket path must stay short on macOS (103 bytes); the bundled server listens on TCP only.

## Consequences
- Installers need code signing (Windows Authenticode, Apple Developer ID and notarisation), else
  the systems warn "unknown publisher".
- The installer is about 200–300 MB (Python, PostgreSQL, Chromium).
- Updates replace the program files and run the migrations as today. A new PostgreSQL major version
  needs a dump and restore by the updater.
- CI builds and smoke-tests the installers on `windows-latest` and `macos-latest`: install, start,
  issue an invoice, check the PDF.
