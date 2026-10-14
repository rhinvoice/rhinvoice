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
