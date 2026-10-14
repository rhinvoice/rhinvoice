"""restic backups of the installation without Docker, against a stand-in (fake_restic.py)."""

import json
import sys
from pathlib import Path

import pytest

from rhinvoice.application.backup.ports import BackupFailed, Snapshot
from rhinvoice.infrastructure.backup.restic import ResticArchive, summary
from tests.helpers import raises_exactly

FAKE = Path(__file__).parent.parent / "fake_restic.py"
DATABASE_URL = "postgresql+psycopg://rhinvoice:db-secret@127.0.0.1:54321/rhinvoice"


@pytest.fixture(scope="module")
def restic(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the stand-in once: macOS checks every new program on its first start."""
    script = tmp_path_factory.mktemp("restic") / "restic"
    script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    script.chmod(0o755)
    return script


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "restic.jsonl"
    monkeypatch.setenv("FAKE_RESTIC_LOG", str(path))
    for name in ("FAKE_RESTIC_FAIL", "FAKE_RESTIC_CAT_CODE", "FAKE_RESTIC_NO_SUMMARY"):
        monkeypatch.delenv(name, raising=False)
    return path


@pytest.fixture
def archive(restic: Path, tmp_path: Path, log: Path) -> ResticArchive:
    del log
    return ResticArchive(
        restic,
        Path("/opt/rhinvoice/pg_dump"),
        tmp_path / "Rhinvoice-Sicherung",
        "K7QM-2XWP",
        DATABASE_URL,
    )


def calls(log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def commands(log: Path) -> list[object]:
    return [call["command"] for call in calls(log)]


def test_a_backup_creates_the_repository_and_runs_pg_dump_through_restic(
    archive: ResticArchive, log: Path, tmp_path: Path
) -> None:
    assert archive.back_up() == Snapshot(snapshot_id="4f3a9c1e", data_added=48000)
    assert commands(log) == ["cat", "init", "backup"]
    backup = calls(log)[-1]
    # The same backups as the backup container makes: either setup restores them.
    assert backup["arguments"] == [
        "--retry-lock", "10m", "backup", "--json",
        "--tag", "rhinvoice", "--host", "rhinvoice", "--stdin-filename", "rhinvoice.sql",
        "--stdin-from-command", "--",
        "/opt/rhinvoice/pg_dump", "--no-owner", "--no-privileges",
        "--exclude-table-data=backup_runs", "--exclude-table-data=backup_requests",
    ]  # fmt: skip
    assert backup["password"] == "K7QM-2XWP"
    assert backup["repository"] == str(tmp_path / "Rhinvoice-Sicherung")
    assert backup["database"] == ["127.0.0.1", "54321", "rhinvoice", "db-secret", "rhinvoice"]
    # The next backup uses the repository that exists.
    archive.back_up()
    assert commands(log)[3:] == ["cat", "backup"]


def test_maintenance_forgets_by_the_retention_and_verifies_on_request(
    archive: ResticArchive, log: Path
) -> None:
    archive.maintain(verify=False)
    assert commands(log) == ["unlock", "forget"]
    assert calls(log)[1]["arguments"] == [
        "--retry-lock", "10m", "forget", "--tag", "rhinvoice", "--host", "rhinvoice",
        "--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "12",
        "--keep-yearly", "unlimited",
    ]  # fmt: skip
    archive.maintain(verify=True)
    assert commands(log)[2:] == ["unlock", "forget", "prune", "check"]
    assert calls(log)[-1]["arguments"] == ["check", "--read-data-subset=5%"]


@pytest.mark.parametrize(
    ("failing", "error", "message"),
    [
        (
            "backup",
            "pg_dump: error: connection to server failed\nFatal: unable to save",
            "pg_dump: error: connection to server failed",
        ),
        (
            "backup",
            '{"message_type":"exit_error","code":1,"message":"repository is locked"}',
            "repository is locked",
        ),
        (
            "init",
            "Fatal: create repository at /x failed: permission denied",
            "Fatal: create repository at /x failed: permission denied",
        ),
    ],
)
def test_failures_name_their_reason(
    archive: ResticArchive,
    monkeypatch: pytest.MonkeyPatch,
    failing: str,
    error: str,
    message: str,
) -> None:
    monkeypatch.setenv("FAKE_RESTIC_FAIL", failing)
    monkeypatch.setenv("FAKE_RESTIC_ERROR", error)
    with raises_exactly(BackupFailed, message):
        archive.back_up()


def test_a_repository_that_cannot_be_opened_is_reported(
    archive: ResticArchive, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_RESTIC_CAT_CODE", "1")
    with raises_exactly(BackupFailed, "Fatal: wrong password or no key found"):
        archive.prepare()


def test_a_backup_without_a_snapshot_is_a_failure(
    archive: ResticArchive, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_RESTIC_NO_SUMMARY", "1")
    with raises_exactly(BackupFailed, "restic reported no snapshot"):
        archive.back_up()


def test_a_failed_maintenance_step_is_reported(
    archive: ResticArchive, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_RESTIC_FAIL", "forget")
    monkeypatch.setenv("FAKE_RESTIC_ERROR", "Fatal: repository is already locked")
    with raises_exactly(BackupFailed, "Fatal: repository is already locked"):
        archive.maintain(verify=False)


def test_summaries_are_short_and_never_empty() -> None:
    assert summary("") == "unknown error"
    assert summary("\n  \n") == "unknown error"
    assert summary("[1, 2]") == "[1, 2]"
    assert summary('{"message": 7}') == '{"message": 7}'
    assert len(summary("x" * 2000)) == 500


PSQL = """#!/bin/sh
# Records its arguments and the dump it was given; fails on request.
printf '%s\\n' "$@" > "$FAKE_PSQL_LOG"
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-f" ]; then cp "$2" "$FAKE_PSQL_LOG.sql"; fi
    shift
done
if [ -n "${FAKE_PSQL_FAIL:-}" ]; then
    echo 'psql:/tmp/rhinvoice.sql:12: ERROR:  relation "x" does not exist' >&2
    exit 3
fi
"""


@pytest.fixture(scope="module")
def psql(tmp_path_factory: pytest.TempPathFactory) -> Path:
    script = tmp_path_factory.mktemp("postgresql") / "psql"
    script.write_text(PSQL)
    script.chmod(0o755)
    return script


@pytest.fixture
def psql_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "psql.log"
    monkeypatch.setenv("FAKE_PSQL_LOG", str(path))
    monkeypatch.delenv("FAKE_PSQL_FAIL", raising=False)
    monkeypatch.delenv("FAKE_RESTIC_DUMP", raising=False)
    return path


def test_a_restore_replaces_the_database_in_one_transaction(
    archive: ResticArchive, log: Path, psql: Path, psql_log: Path
) -> None:
    """As the backup container does: on any error nothing changes."""
    archive.restore("latest", psql)
    assert calls(log)[-1]["arguments"] == ["dump", "--tag", "rhinvoice", "latest", "/rhinvoice.sql"]
    assert psql_log.read_text().splitlines() == [
        "-X", "-q", "-v", "ON_ERROR_STOP=1", "--single-transaction",
        "-c", "DROP SCHEMA public CASCADE", "-c", "CREATE SCHEMA public",
        "-f", psql_log.read_text().splitlines()[10],
        "-c", "INSERT INTO public.backup_requests (requested_at, reason) VALUES (now(), 'manual')",
    ]  # fmt: skip
    assert psql_log.read_text().splitlines()[10].endswith("rhinvoice.sql")
    assert "PostgreSQL database dump complete" in Path(f"{psql_log}.sql").read_text()


def test_an_incomplete_backup_changes_nothing(
    archive: ResticArchive, psql: Path, psql_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_RESTIC_DUMP", "CREATE TABLE public.documents (\n")
    with raises_exactly(BackupFailed, "the backup is incomplete, nothing was changed"):
        archive.restore("latest", psql)
    assert not psql_log.exists()


def test_restore_failures_name_their_reason(
    archive: ResticArchive, psql: Path, psql_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_RESTIC_FAIL", "dump")
    monkeypatch.setenv("FAKE_RESTIC_ERROR", 'Fatal: no matching ID found for prefix "0000"')
    with raises_exactly(BackupFailed, 'Fatal: no matching ID found for prefix "0000"'):
        archive.restore("0000", psql)
    assert not psql_log.exists()
    monkeypatch.delenv("FAKE_RESTIC_FAIL")
    monkeypatch.setenv("FAKE_PSQL_FAIL", "1")
    with raises_exactly(
        BackupFailed, 'psql:/tmp/rhinvoice.sql:12: ERROR:  relation "x" does not exist'
    ):
        archive.restore("latest", psql)


def test_the_backups_are_listed(
    archive: ResticArchive, log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "4f3a9c1e  2026-03-09 09:00:00" in archive.snapshots()
    assert calls(log)[-1]["arguments"] == ["snapshots", "--tag", "rhinvoice"]
    monkeypatch.setenv("FAKE_RESTIC_FAIL", "snapshots")
    monkeypatch.setenv("FAKE_RESTIC_ERROR", "Fatal: wrong password or no key found")
    with raises_exactly(BackupFailed, "Fatal: wrong password or no key found"):
        archive.snapshots()


def test_a_database_url_without_details_uses_the_defaults(
    restic: Path, tmp_path: Path, log: Path
) -> None:
    archive = ResticArchive(
        restic, Path("/pg_dump"), tmp_path / "repo", "key", "postgresql+psycopg://"
    )
    archive.back_up()
    assert calls(log)[-1]["database"] == ["127.0.0.1", "5432", "", "", ""]


@pytest.mark.parametrize(
    ("latin1", "message"),
    [(False, "Fatal: unable to open C:\\Users\\Boček\\OneDrive"), (True, "Fatal: caf�")],
)
def test_error_output_is_read_as_utf_8_whatever_it_holds(
    archive: ResticArchive, monkeypatch: pytest.MonkeyPatch, *, latin1: bool, message: str
) -> None:
    """A message the locale cannot decode must still fail the run, not crash it."""
    monkeypatch.setenv("FAKE_RESTIC_FAIL", "backup")
    monkeypatch.setenv("FAKE_RESTIC_ERROR", "Fatal: café" if latin1 else message)
    if latin1:
        monkeypatch.setenv("FAKE_RESTIC_LATIN1", "1")
    with raises_exactly(BackupFailed, message):
        archive.back_up()


def test_a_restic_that_cannot_be_started_fails_the_backup(tmp_path: Path, log: Path) -> None:
    """E.g. restic.exe quarantined by a virus scanner."""
    del log
    missing = tmp_path / "restic" / "restic.exe"
    archive = ResticArchive(missing, Path("/pg_dump"), tmp_path / "repo", "key", DATABASE_URL)
    with pytest.raises(BackupFailed, match=r"^restic cannot be started: "):
        archive.back_up()
    with pytest.raises(BackupFailed, match=r"^restic cannot be started: "):
        archive.restore("latest", Path("/psql"))
