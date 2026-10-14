# 0023 – Backups of the installation without Docker

- Status: proposed
- Date: 2026-10-14

## Context
In the Docker setup the `backup` container saves the database with restic (docs/backup.md):
daily, after documents were issued or cancelled, and on request; 7 daily, 4 weekly, 12 monthly
and every yearly backup; a sample is verified on Sundays. It talks to the app only through the
tables `backup_runs` and `backup_requests`, which the settings page and the dashboard read.

The installation without Docker (ADR 0021) has no such container, and its data lies on one
computer. Invoices must be kept for ten years (OR 958f, GoBD, BAO): a lost laptop must not lose
them. The people it is meant for do not run restic commands.

## Decision
- **The same backups, made by the program itself.** A `BackupWorker` in the application layer
  follows the rules of the backup container (when, what is kept, the retries after a failure)
  and records its runs in the same tables. The settings page and the dashboard's warning work
  unchanged, and the backups are the same restic repositories: either setup can restore them.
- **restic and pg_dump stay tools behind a port** (`BackupArchive`): the infrastructure runs the
  bundled restic with the bundled `pg_dump`, as the container does (`--stdin-from-command`).
- **The target is a folder**, preferably one that a cloud service keeps in sync (OneDrive,
  Dropbox, iCloud Drive, Google Drive): no credentials in Rhinvoice, and the copy leaves the
  computer by itself. A network drive or a USB disk work the same way.
- **The password is generated** and kept in the configuration so that backups run unattended;
  the person has to keep a copy elsewhere (how it is shown and confirmed is decided with the UI).
- **The worker runs only in the installation without Docker** (the desktop layer starts it);
  the Docker setup keeps its container.

## Consequences
- The setups bundle restic (pinned, SHA-256 like the other parts).
- The repository methods the container uses in SQL (start, finish, take requests, recover runs
  left running) get a Python implementation; the container keeps its own.
- A restore without Docker needs a documented way (and a test), like `make restore` for Docker.
