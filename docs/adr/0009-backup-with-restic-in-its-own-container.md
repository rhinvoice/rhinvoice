# 0009 – Backup with restic in its own container

- Status: accepted
- Date: 2026-10-11

## Context
CLAUDE.md §10 requires an encrypted, deduplicated backup (restic) with targets configured via
environment variables, daily plus after every issuing or cancellation (debounced, "job via
procrastinate"), retention 7/4/12/yearly, at least 10 years, `make restore`, a
restore test in CI and a warning in the dashboard after 24 h.

## Decision
- **What is backed up:** only the database. Everything lives there (including archived PDFs and the logo).
  `pg_dump` in plain SQL format: restic deduplicates and compresses it well, and a restore
  needs only `psql`. The backup tables themselves are not in the dump (otherwise, after a
  restore, a run would show "running" forever).
- **Separate container** `backup` (alpine + postgresql17-client + restic 0.19), script
  `backup/rhinvoice-backup.sh`. This way the app needs neither restic nor credentials for the target.
- **Instead of procrastinate:** the app writes requests to `backup_requests`, in the same
  transaction as the issuing (a rejected issuing requests nothing). The container
  polls every 30 s and starts once no further request has arrived for 2 minutes, at the latest
  15 minutes after the first one (debouncing); manual requests start immediately. Requests are only done
  after a successful run; after a failure, document requests wait
  15 minutes. A queue with a worker would be introduced just for this one job; procrastinate remains
  for later jobs (e.g. sending).
- **Never back up an empty installation:** without company data nothing is backed up; otherwise a
  new or test installation on the same repository would become the "latest" snapshot. Several installations
  on one repository are kept apart via `BACKUP_HOST`.
- **Robust against interruptions:** on start, "running" runs are marked as interrupted and
  orphaned restic locks are removed (`restic unlock`); all restic commands wait up to 10 minutes
  for other locks (`--retry-lock`).
- **Result:** the container writes every run to `backup_runs` (status, snapshot ID,
  bytes added, error message); the app shows the state from it (not set up /
  up to date / stale after 24 h). Without `RESTIC_REPOSITORY` the container reports "not set up".
- **Retention:** `forget` after the daily backup with 7 daily, 4 weekly,
  12 monthly and all yearly snapshots (`--keep-yearly unlimited`): conservatively beyond the
  10 years. `prune` and `check --read-data-subset=5%` only on Sundays (slow, they lock the
  repository, and they cost requests on S3).
- **Restore** in one transaction (`DROP SCHEMA` + dump + new backup request); only if
  nobody else is connected to the database; an incomplete dump is rejected. The dump
  is buffered on the cache volume, not in memory (it contains all PDFs).
- **Test:** `make backup-qa` (shellcheck, then backup → change → restore → app starts) runs in
  `make qa` and as a separate CI job. The image is published on release as `ghcr.io/rhinvoice/rhinvoice-backup`.

## Consequences
- The shell script lies outside the Python coverage; it is secured by shellcheck and the
  end-to-end test against the real images.
- Anyone running Rhinvoice without the container sees "not set up" in the dashboard.
