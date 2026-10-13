#!/bin/sh
# Backs up, changes the data, restores and checks that the app works on the result;
# also through rclone and the failure cases: a new installation, an interrupted run,
# a wrong password.
set -eu

compose() {
    docker compose -f compose.backup-test.yml "$@"
}

psql_db() {
    compose exec -T db psql -X -q -A -t -v ON_ERROR_STOP=1 -U rhinvoice -d rhinvoice -c "$1"
}

# Waits until the SQL query prints "t".
wait_for() {
    attempts=0
    until [ "$(psql_db "$1")" = "t" ]; do
        attempts=$((attempts + 1))
        if [ "$attempts" -gt 120 ]; then
            echo "timed out waiting for: $1" >&2
            compose logs backup >&2
            exit 1
        fi
        sleep 1
    done
}

cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
compose up --build --wait --detach db app
schema="$(psql_db "SELECT version_num FROM alembic_version")"

echo "--- a new installation is not backed up; an interrupted run is cleaned up"
psql_db "INSERT INTO backup_runs (started_at, reason, status) VALUES (now() - interval '1 hour', 'daily', 'running')"
psql_db "INSERT INTO backup_requests (requested_at, reason) VALUES (now(), 'manual')"
compose up --build --detach backup
wait_for "SELECT bool_and(status = 'failed' AND message LIKE 'interrupted%') FROM backup_runs"
sleep 5
test "$(psql_db "SELECT count(*) FROM backup_runs")" = "1"
test "$(psql_db "SELECT count(*) FROM backup_requests WHERE handled_at IS NULL")" = "1"

echo "--- daily backup (due at once), then a backup on request"
psql_db "INSERT INTO company (id, name, postal_code, city, country, default_currency, default_language,
    small_business, cash_rounding, payment_terms_days, accent_hue)
    VALUES (gen_random_uuid(), 'Muster GmbH', '8001', 'Zürich', 'CH', 'CHF', 'de', false, true, 30, 250)"
psql_db "INSERT INTO legal_notices VALUES ('domestic', 'de', 'Wortlaut vor dem Backup')"
wait_for "SELECT EXISTS (SELECT 1 FROM backup_runs WHERE reason = 'daily' AND status = 'succeeded')"
wait_for "SELECT NOT EXISTS (SELECT 1 FROM backup_requests WHERE handled_at IS NULL)"
psql_db "INSERT INTO backup_requests (requested_at, reason) VALUES (now(), 'document')"
wait_for "SELECT EXISTS (SELECT 1 FROM backup_runs WHERE reason = 'document' AND status = 'succeeded')"
wait_for "SELECT NOT EXISTS (SELECT 1 FROM backup_requests WHERE handled_at IS NULL)"
# The daily backup also maintained the repository (forget) without errors.
test "$(psql_db "SELECT bool_and(message IS NULL AND snapshot_id IS NOT NULL AND data_added > 0) FROM backup_runs WHERE status = 'succeeded'")" = "t"
compose exec -T backup rhinvoice-backup snapshots

echo "--- a repository reached through rclone (here its local backend, in the cloud e.g. Dropbox)"
compose run --rm --no-deps backup rclone config create target local >/dev/null
via_rclone="rclone:target:/repository/via-rclone"
compose run --rm --no-deps -e RESTIC_REPOSITORY="$via_rclone" backup backup
compose run --rm --no-deps -e RESTIC_REPOSITORY="$via_rclone" backup snapshots | grep -q rhinvoice.sql
test "$(psql_db "SELECT count(*) FROM backup_runs WHERE reason = 'manual' AND status = 'succeeded'")" = "1"

echo "--- a new repository is filled at once, although today's backup was made"
compose stop backup
dailies="$(psql_db "SELECT count(*) FROM backup_runs WHERE reason = 'daily' AND status = 'succeeded'")"
fresh="/repository/fresh"
for expected in "$((dailies + 1))" "$((dailies + 1))"; do
    container="$(compose run --detach --no-deps -e RESTIC_REPOSITORY="$fresh" backup)"
    until docker logs "$container" 2>&1 | grep -q "waiting for requests"; do sleep 1; done
    # The first start creates the repository and backs up, the second finds it and does not.
    test "$(psql_db "SELECT count(*) FROM backup_runs WHERE reason = 'daily' AND status = 'succeeded'")" = "$expected"
    docker logs "$container" 2>&1 | grep -c "the repository is new" >>/tmp/rhinvoice-backup-test-new || true
    docker stop "$container" >/dev/null
    docker rm "$container" >/dev/null
done
test "$(tr '\n' ' ' </tmp/rhinvoice-backup-test-new)" = "1 0 "
rm -f /tmp/rhinvoice-backup-test-new
compose run --rm --no-deps -e RESTIC_REPOSITORY="$fresh" backup snapshots | grep -q rhinvoice.sql

echo "--- a failed backup is recorded with its reason and its request stays open"
wrong="$(compose run --detach --no-deps -e RESTIC_PASSWORD=wrong backup)"
psql_db "INSERT INTO backup_requests (requested_at, reason) VALUES (now(), 'manual')"
wait_for "SELECT EXISTS (SELECT 1 FROM backup_runs WHERE status = 'failed' AND message LIKE '%password%')"
test "$(psql_db "SELECT count(*) FROM backup_requests WHERE handled_at IS NULL")" = "1"
docker stop "$wrong" >/dev/null
docker rm "$wrong" >/dev/null

echo "--- change the data, then restore the latest backup"
psql_db "UPDATE legal_notices SET text = 'nach dem Backup'"
psql_db "INSERT INTO legal_notices VALUES ('export', 'de', 'nach dem Backup')"
compose stop app
if compose run --rm --no-deps backup restore; then
    echo "restore without a snapshot did not stop" >&2
    exit 1
fi
compose run --rm --no-deps backup restore latest

test "$(psql_db "SELECT string_agg(text, '|') FROM legal_notices")" = "Wortlaut vor dem Backup"
test "$(psql_db "SELECT version_num FROM alembic_version")" = "$schema"
# The protection of issued documents is back, the history starts anew with a request.
test "$(psql_db "SELECT count(*) FROM pg_trigger WHERE tgname = 'protect_document_pdfs'")" = "1"
test "$(psql_db "SELECT count(*) FROM backup_runs")" = "0"
test "$(psql_db "SELECT count(*) FROM backup_requests WHERE handled_at IS NULL")" = "1"

echo "--- the app runs on the restored database"
compose up --wait --detach app
compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)"

echo "--- a restore with the app running is refused"
if compose run --rm --no-deps backup restore latest; then
    echo "restore did not refuse a database in use" >&2
    exit 1
fi

echo "--- without a repository the backup container says so, once"
for _ in 1 2; do
    container="$(compose run --detach --no-deps -e RESTIC_REPOSITORY= backup)"
    # Logged after the run was recorded (or found recorded already).
    until docker logs "$container" 2>&1 | grep -q "no repository configured"; do sleep 1; done
    docker stop "$container" >/dev/null
    docker rm "$container" >/dev/null
done
test "$(psql_db "SELECT count(*) FROM backup_runs WHERE status = 'not_configured'")" = "1"
echo "backup test passed"
