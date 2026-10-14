"""Backups of the installation without Docker with restic (ADR 0023).

The same backups as the backup container makes (backup/rhinvoice-backup.sh): restic runs
pg_dump itself (``--stdin-from-command``), with the same tag, host and file name, so
either setup can restore them; the same retention.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import IO, cast

from sqlalchemy.engine import make_url

from rhinvoice.application.backup.ports import BackupFailed, Snapshot

TAG = "rhinvoice"
HOST = "rhinvoice"
DUMP_NAME = "rhinvoice.sql"
LOCK_WAIT = "10m"
"""Wait for a lock of another restic process (e.g. the weekly prune) instead of failing."""
NO_REPOSITORY = 10
"""restic's exit code for "repository does not exist" (restic 0.17+)."""
MESSAGE_LENGTH = 500
DUMP_END_BYTES = 200
"""The end of a dump in which pg_dump's closing line must be."""
REQUEST_BACKUP = (
    "INSERT INTO public.backup_requests (requested_at, reason) VALUES (now(), 'manual')"
)
"""After a restore: the restored state gets a backup of its own once backups run."""
RETENTION = ("--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "12")
"""And every yearly backup: invoices are kept for ten years and more (OR 958f, GoBD, BAO)."""
SHORT_SECONDS = 60
"""For opening the repository: a folder that does not answer within a minute is unusable."""
LONG_SECONDS = 4 * 3600
"""For backing up, pruning, checking and restoring; the first backup may hold years of PDFs."""
NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)
"""No console window for restic and pg_dump on Windows (Rhinvoice.exe has none)."""


class ResticArchive:
    """The ``BackupArchive`` port: a restic repository in a folder."""

    def __init__(
        self, restic: Path, pg_dump: Path, repository: Path, password: str, database_url: str
    ) -> None:
        self._restic = restic
        self._pg_dump = pg_dump
        url = make_url(database_url)
        # Set for restic and the pg_dump it starts, on top of the environment of each run.
        self._environment = {
            "RESTIC_REPOSITORY": str(repository),
            "RESTIC_PASSWORD": password,
            "PGHOST": url.host or "127.0.0.1",
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "",
            "PGPASSWORD": url.password or "",
            "PGDATABASE": url.database or "",
        }

    def prepare(self) -> None:
        """Create the repository when there is none yet; raise BackupFailed if impossible."""
        found = self._run("cat", "config", timeout=SHORT_SECONDS)
        if found.returncode == 0:
            return
        if found.returncode != NO_REPOSITORY:
            raise BackupFailed(summary(found.stderr))
        created = self._run("init")
        # Created meanwhile by another process: "config file already exists" is no failure.
        if (
            created.returncode != 0
            and self._run("cat", "config", timeout=SHORT_SECONDS).returncode != 0
        ):
            raise BackupFailed(summary(created.stderr))

    def back_up(self) -> Snapshot:
        self.prepare()
        # The backup history is not part of the backup: a restored database would
        # otherwise show this run as running forever.
        result = self._run(
            "--retry-lock", LOCK_WAIT, "backup", "--json",
            "--tag", TAG, "--host", HOST, "--stdin-filename", DUMP_NAME,
            "--stdin-from-command", "--",
            str(self._pg_dump), "--no-owner", "--no-privileges",
            "--exclude-table-data=backup_runs", "--exclude-table-data=backup_requests",
        )  # fmt: skip
        if result.returncode != 0:
            raise BackupFailed(summary(result.stderr))
        for line in result.stdout.splitlines():
            message = _json(line)
            if message.get("message_type") == "summary" and isinstance(
                message.get("snapshot_id"), str
            ):
                added = message.get("data_added")
                return Snapshot(
                    snapshot_id=cast("str", message["snapshot_id"]),
                    data_added=added if isinstance(added, int) else None,
                )
        msg = "restic reported no snapshot"
        raise BackupFailed(msg)

    def maintain(self, *, verify: bool) -> None:
        steps: list[tuple[str, ...]] = [
            ("unlock",),
            ("--retry-lock", LOCK_WAIT, "forget", "--tag", TAG, "--host", HOST, *RETENTION,
             "--keep-yearly", "unlimited"),
        ]  # fmt: skip
        if verify:
            # Slow and locking the repository: on Sundays only (as the backup container).
            steps += [("--retry-lock", LOCK_WAIT, "prune"), ("check", "--read-data-subset=5%")]
        for step in steps:
            result = self._run(*step)
            if result.returncode != 0:
                raise BackupFailed(summary(result.stderr))

    def snapshots(self) -> str:
        """List the backups as restic shows them (ID and time, to choose one to restore)."""
        result = self._run("snapshots", "--tag", TAG)
        if result.returncode != 0:
            raise BackupFailed(summary(result.stderr))
        return result.stdout

    def restore(self, snapshot: str, psql: Path) -> None:
        """Replace the database with a backup ("latest" or an ID), as the backup container does.

        One transaction: on any error nothing changes. The restored state is backed up
        again as soon as backups run.
        """
        with tempfile.TemporaryDirectory() as folder:
            # In a file, not in memory: the dump holds every archived PDF.
            dump = Path(folder) / DUMP_NAME
            with dump.open("wb") as file:
                fetched = self._call(
                    [str(self._restic), "dump", "--tag", TAG, snapshot, f"/{DUMP_NAME}"],
                    stdout=file,
                )
            if fetched.returncode != 0:
                raise BackupFailed(summary(fetched.stderr))
            if not _complete(dump):
                msg = "the backup is incomplete, nothing was changed"
                raise BackupFailed(msg)
            # (The dump empties the search_path, hence the schema name.)
            replaced = self._call(
                [
                    str(psql), "-X", "-q", "-v", "ON_ERROR_STOP=1", "--single-transaction",
                    "-c", "DROP SCHEMA public CASCADE", "-c", "CREATE SCHEMA public",
                    "-f", str(dump),
                    "-c", REQUEST_BACKUP,
                ],
                quiet=True,
            )  # fmt: skip
            if replaced.returncode != 0:
                raise BackupFailed(summary(replaced.stderr))

    def _run(
        self, *arguments: str, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        return self._call([str(self._restic), *arguments], timeout=timeout)

    def _call(
        self,
        command: list[str],
        *,
        stdout: IO[bytes] | None = None,
        quiet: bool = False,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run restic or psql; output is UTF-8 whatever the locale (restic writes UTF-8).

        Never without a time limit: a hanging tool would block every later backup.
        """
        limit = LONG_SECONDS if timeout is None else timeout
        environment = {**os.environ, **self._environment}
        if quiet:
            environment["PGOPTIONS"] = "-c client_min_messages=warning"
        try:
            return subprocess.run(  # noqa: S603 - the bundled tools, arguments built here
                command,
                stdout=subprocess.PIPE if stdout is None else stdout,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                check=False,
                env=environment,
                creationflags=NO_WINDOW,
                timeout=limit,
            )
        except subprocess.TimeoutExpired as error:
            name = Path(command[0]).stem
            task = next(
                part for part in command[1:] if not part.startswith("-") and part != LOCK_WAIT
            )
            msg = f"{name} did not answer within {limit:g} seconds ({task})"
            raise BackupFailed(msg) from error
        except OSError as error:
            # E.g. quarantined by a virus scanner, or removed.
            msg = f"{Path(command[0]).stem} cannot be started: {error}"
            raise BackupFailed(msg) from error


def summary(errors: str) -> str:
    """Name the most telling line of an error output, short enough for the settings page.

    pg_dump's own message, else restic's last line (its message when it is JSON).
    """
    lines = [line.strip() for line in errors.splitlines() if line.strip()]
    line = next((line for line in lines if line.startswith("pg_dump: ")), None)
    if line is None and lines:
        message = _json(lines[-1]).get("message")
        line = message if isinstance(message, str) else lines[-1]
    return (line or "unknown error")[:MESSAGE_LENGTH]


def _complete(dump: Path) -> bool:
    """Tell whether pg_dump finished the dump: it ends every complete one with this line."""
    with dump.open("rb") as file:
        file.seek(max(dump.stat().st_size - DUMP_END_BYTES, 0))
        return b"PostgreSQL database dump complete" in file.read()


def _json(line: str) -> dict[str, object]:
    try:
        value = json.loads(line)
    except ValueError:
        return {}
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}
