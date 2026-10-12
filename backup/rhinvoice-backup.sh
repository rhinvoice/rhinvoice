#!/bin/sh
# Rhinvoice backup: the database (documents, archived PDFs, logo, settings) as an
# SQL dump in an encrypted, deduplicated restic repository. See docs/backup.md.
#
#   rhinvoice-backup run              wait for requests and the daily time (default)
#   rhinvoice-backup backup [reason]  back up now (reason: manual, daily, document)
#   rhinvoice-backup snapshots        list the backups
#   rhinvoice-backup restore ID       replace the database with a backup (an ID or "latest")
#   rhinvoice-backup check            verify the repository
#   rhinvoice-backup rclone ARGS...   run rclone, e.g. to connect Dropbox (docs/backup.md)
#
# Connection: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE.
# Repository: RESTIC_REPOSITORY (or _FILE) and RESTIC_PASSWORD (or _FILE), plus the
# variables of the backend (e.g. AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY for S3).
# rclone: repositories (rclone:remote:path) use the configuration in RCLONE_CONFIG.
#
# Functions that can fail are called as `if ! f` or `f || ...`, where `set -e` does
# not apply inside them; they therefore check every step themselves.
set -eu

DAILY_AT="${BACKUP_DAILY_AT:-02:00}"
# Issuing several documents in a row gives one backup: it starts once no request
# came for QUIET seconds, but at the latest MAX_WAIT seconds after the first one.
QUIET="${BACKUP_QUIET_SECONDS:-120}"
MAX_WAIT="${BACKUP_MAX_WAIT_SECONDS:-900}"
POLL="${BACKUP_POLL_SECONDS:-30}"
# Snapshots of one installation; another installation sharing the repository
# must use another name, or the retention rules would mix them.
HOST="${BACKUP_HOST:-rhinvoice}"
TIMEZONE="${TZ:-Europe/Zurich}"
DUMP_NAME="rhinvoice.sql"
TAG="rhinvoice"
# Wait for a lock of another restic process (e.g. the weekly prune) instead of failing.
LOCK_WAIT="10m"
# Touched while the loop runs; the container's health check reads it.
HEARTBEAT="/tmp/heartbeat"
# restic exit code for "repository does not exist" (restic 0.17+).
NO_REPOSITORY=10

log() {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

# Run SQL from stdin; psql variables are passed as -v name=value.
sql() {
    psql -X -q -A -t -v ON_ERROR_STOP=1 "$@"
}

rstc() {
    restic --retry-lock "$LOCK_WAIT" "$@"
}

configured() {
    { [ -n "${RESTIC_REPOSITORY:-}" ] || [ -n "${RESTIC_REPOSITORY_FILE:-}" ]; } &&
        { [ -n "${RESTIC_PASSWORD:-}" ] || [ -n "${RESTIC_PASSWORD_FILE:-}" ]; }
}

check_settings() {
    hours="${DAILY_AT%%:*}"
    case "$DAILY_AT" in
    [0-2][0-9]:[0-5][0-9]) ;;
    *) hours=99 ;;
    esac
    if [ "$hours" -gt 23 ]; then
        log "BACKUP_DAILY_AT must be a time like 02:00, not \"$DAILY_AT\""
        exit 2
    fi
}

wait_for_schema() {
    attempts=0
    errors="$(mktemp)"
    until [ "$(echo "SELECT to_regclass('public.backup_runs') IS NOT NULL" | sql 2>"$errors")" = "t" ]; do
        attempts=$((attempts + 1))
        # Every minute: show why (e.g. a wrong password), not just that we wait.
        if [ $((attempts % 12)) -eq 1 ]; then
            log "waiting for the database and its migrations: $(head -n 1 "$errors")"
        fi
        sleep 5
    done
    rm -f "$errors"
}

# A new or empty installation is never backed up: its empty database would become
# the latest snapshot of the repository it shares with the real installation.
has_data() {
    [ "$(echo "SELECT EXISTS (SELECT 1 FROM public.company)" | sql)" = "t" ]
}

ensure_repository() {
    status=0
    restic cat config >/dev/null 2>&1 || status=$?
    if [ "$status" -eq "$NO_REPOSITORY" ]; then
        log "creating the restic repository"
        restic init >/dev/null || return 1
    fi
}

# Runs left "running" by a stopped container (update, reboot) are marked as failed.
recover_runs() {
    sql <<'SQL'
UPDATE backup_runs
SET status = 'failed', finished_at = now(),
    message = 'interrupted: the backup container stopped during the backup'
WHERE status = 'running';
SQL
}

# Prints the id of the new run.
start_run() {
    sql -v reason="$1" <<'SQL'
INSERT INTO backup_runs (started_at, reason, status) VALUES (now(), :'reason', 'running')
RETURNING id;
SQL
}

finish_run() {
    sql -v id="$1" -v status="$2" -v snapshot="$3" -v added="$4" -v message="$5" <<'SQL'
UPDATE backup_runs
SET finished_at = now(),
    status = :'status',
    snapshot_id = NULLIF(:'snapshot', ''),
    data_added = NULLIF(:'added', '')::bigint,
    message = NULLIF(:'message', '')
WHERE id = :'id'::bigint;
SQL
}

# The requests made before a successful run are done; old ones are removed.
take_requests() {
    sql -v id="$1" <<'SQL'
UPDATE backup_requests SET handled_at = now()
WHERE handled_at IS NULL
  AND requested_at <= (SELECT started_at FROM backup_runs WHERE id = :'id'::bigint);
DELETE FROM backup_requests WHERE handled_at < now() - interval '30 days';
SQL
}

# The most telling line of an error output, short enough for the settings page:
# pg_dump's own message, else restic's (JSON with --json, first line only).
summary_of() {
    line="$(grep -m 1 '^pg_dump: ' "$1" || true)"
    if [ -z "$line" ]; then
        line="$(grep -v '^[[:space:]]*$' "$1" | tail -n 1 || true)"
        message="$(printf '%s' "$line" | jq -r '.message // empty' 2>/dev/null | head -n 1 || true)"
        line="${message:-$line}"
    fi
    printf '%s' "${line:-unknown error}" | cut -c 1-500
}

fail_run() {
    log "backup $1 failed: $2"
    finish_run "$1" failed "" "" "$2" || log "could not record the failure of backup $1"
    return 1
}

backup() {
    reason="${1:-manual}"
    if ! has_data; then
        log "nothing to back up: no company is set up yet (new installation)"
        return 0
    fi
    errors="$(mktemp)" || return 1
    if ! id="$(start_run "$reason")" || [ -z "$id" ]; then
        log "could not record the start of the backup"
        rm -f "$errors"
        return 1
    fi
    log "backup $id ($reason) started"
    if ! ensure_repository 2>"$errors"; then
        fail_run "$id" "$(summary_of "$errors")" || true
        rm -f "$errors"
        return 1
    fi
    # restic runs pg_dump itself and fails when it fails (--stdin-from-command).
    # The backup history is not part of the backup: a restored database would
    # otherwise show this run as running forever.
    if ! output="$(rstc backup --json --tag "$TAG" --host "$HOST" \
        --stdin-filename "$DUMP_NAME" --stdin-from-command -- \
        pg_dump --no-owner --no-privileges \
        --exclude-table-data=backup_runs --exclude-table-data=backup_requests 2>"$errors")"; then
        fail_run "$id" "$(summary_of "$errors")" || true
        rm -f "$errors"
        return 1
    fi
    summary="$(printf '%s\n' "$output" | jq -c 'select(.message_type == "summary")' 2>/dev/null || true)"
    snapshot="$(printf '%s' "$summary" | jq -r '.snapshot_id // empty' 2>/dev/null || true)"
    added="$(printf '%s' "$summary" | jq -r '.data_added // empty' 2>/dev/null || true)"
    if [ -z "$snapshot" ]; then
        fail_run "$id" "restic reported no snapshot" || true
        rm -f "$errors"
        return 1
    fi
    message=""
    if [ "$reason" = "daily" ] && ! maintain 2>"$errors"; then
        message="backed up, but the repository maintenance failed: $(summary_of "$errors")"
        log "backup $id: $message"
    fi
    rm -f "$errors"
    if ! finish_run "$id" succeeded "$snapshot" "$added" "$message" || ! take_requests "$id"; then
        log "backup $id: snapshot $snapshot was made, but the result could not be recorded"
        return 1
    fi
    log "backup $id succeeded: snapshot $snapshot, ${added:-0} bytes added"
}

# Retention (CLAUDE.md §10): 7 daily, 4 weekly, 12 monthly and every yearly backup,
# so documents stay recoverable for the legal 10 years and beyond. Removing data
# (prune) and verifying a sample of it (check) happen on Sundays only: both are slow
# and lock the repository.
maintain() {
    restic unlock >/dev/null || return 1
    rstc forget --tag "$TAG" --host "$HOST" \
        --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --keep-yearly unlimited >/dev/null || return 1
    if [ "$(date +%u)" = "7" ]; then
        rstc prune >/dev/null || return 1
        rstc check --read-data-subset=5% >/dev/null || return 1
    fi
}

daily_due() {
    sql -v tz="$TIMEZONE" -v at="$DAILY_AT" <<'SQL'
WITH today AS (
    SELECT (date_trunc('day', now() AT TIME ZONE :'tz') + :'at'::time) AT TIME ZONE :'tz' AS due
)
SELECT now() >= due AND NOT EXISTS (
    SELECT 1 FROM backup_runs
    WHERE reason = 'daily' AND started_at >= due
      -- A failed run is retried after 30 minutes.
      AND (status IN ('succeeded', 'running') OR started_at > now() - interval '30 minutes')
)
FROM today;
SQL
}

# Prints the reason of the backup the pending requests ask for, if one is due.
# After a failed run, requests from documents wait 15 minutes (e.g. while the target
# is unreachable); a request from the settings page is tried at once.
requested() {
    sql -v quiet="$QUIET" -v max_wait="$MAX_WAIT" <<'SQL'
WITH failure AS (
    SELECT max(started_at) AS at FROM backup_runs
    WHERE status = 'failed' AND started_at > now() - interval '15 minutes'
)
SELECT CASE
    WHEN bool_or(r.reason = 'manual' AND (f.at IS NULL OR r.requested_at > f.at)) THEN 'manual'
    WHEN f.at IS NOT NULL THEN NULL
    WHEN max(r.requested_at) <= now() - make_interval(secs => :'quiet'::int)
      OR min(r.requested_at) <= now() - make_interval(secs => :'max_wait'::int) THEN 'document'
END
FROM backup_requests AS r CROSS JOIN failure AS f
WHERE r.handled_at IS NULL
GROUP BY f.at;
SQL
}

not_configured() {
    # Recorded once, not on every restart.
    sql <<'SQL' || log "could not record that backups are not set up"
INSERT INTO backup_runs (started_at, finished_at, reason, status, message)
SELECT now(), now(), 'manual', 'not_configured', 'RESTIC_REPOSITORY or RESTIC_PASSWORD is not set'
WHERE NOT EXISTS (
    SELECT 1 FROM backup_runs
    WHERE id = (SELECT max(id) FROM backup_runs) AND status = 'not_configured'
);
SQL
    log "no repository configured (RESTIC_REPOSITORY, RESTIC_PASSWORD): not backing up"
    while :; do
        touch "$HEARTBEAT"
        sleep 300
    done
}

run() {
    check_settings
    wait_for_schema
    configured || not_configured
    recover_runs || log "could not clean up interrupted runs"
    if ensure_repository && restic unlock >/dev/null; then
        log "waiting for requests; daily backup at $DAILY_AT ($TIMEZONE)"
    else
        log "the repository is not reachable yet; the next backup will try again"
    fi
    told_empty=""
    while :; do
        touch "$HEARTBEAT"
        if ! data="$(echo "SELECT EXISTS (SELECT 1 FROM public.company)" | sql)"; then
            log "the database is not reachable"
        elif [ "$data" != "t" ]; then
            if [ -z "$told_empty" ]; then
                log "nothing to back up until a company is set up"
                told_empty="yes"
            fi
        elif ! due="$(daily_due)" || ! pending="$(requested)"; then
            log "the database is not reachable"
        else
            reason=""
            if [ "$due" = "t" ]; then
                reason="daily"
            elif [ -n "$pending" ]; then
                reason="$pending"
            fi
            if [ -n "$reason" ] && ! backup "$reason"; then
                log "the $reason backup failed; it is retried later"
            fi
        fi
        sleep "$POLL"
    done
}

restore() {
    if [ "$#" -eq 0 ]; then
        log "usage: rhinvoice-backup restore <snapshot ID or latest>; the backups:"
        rstc snapshots --tag "$TAG"
        return 2
    fi
    snapshot="$1"
    others="$(echo "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()" | sql)"
    if [ "$others" != "0" ]; then
        log "the database is in use: stop the app and the backup first (docker compose stop app backup)"
        return 1
    fi
    # On the cache volume, not in /tmp (memory): the dump holds every archived PDF.
    dump="$(mktemp -p /cache restore.XXXXXX)"
    trap 'rm -f "$dump"' EXIT
    log "fetching $DUMP_NAME from snapshot $snapshot"
    rstc dump --tag "$TAG" "$snapshot" "/$DUMP_NAME" >"$dump"
    # pg_dump ends every complete dump with this line.
    if ! tail -n 5 "$dump" | grep -q 'PostgreSQL database dump complete'; then
        log "the backup is incomplete, nothing was changed"
        return 1
    fi
    log "replacing the database (one transaction: on any error nothing changes)"
    # The restored state gets a backup of its own as soon as the backup container runs.
    # (The dump empties the search_path, hence the schema name.)
    PGOPTIONS="-c client_min_messages=warning" psql -X -q -v ON_ERROR_STOP=1 --single-transaction \
        -c 'DROP SCHEMA public CASCADE' -c 'CREATE SCHEMA public' -f "$dump" \
        -c "INSERT INTO public.backup_requests (requested_at, reason) VALUES (now(), 'manual')" >/dev/null
    log "restored snapshot $snapshot; start the app again (docker compose start app backup)"
}

command="${1:-run}"
[ "$#" -gt 0 ] && shift
case "$command" in
run) run ;;
backup)
    wait_for_schema
    backup "${1:-manual}"
    ;;
snapshots) rstc snapshots --tag "$TAG" ;;
restore) restore "$@" ;;
check) rstc check ;;
rclone) exec rclone "$@" ;;
*)
    log "unknown command: $command"
    exit 2
    ;;
esac
