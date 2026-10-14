"""The PostgreSQL that comes with an installation without Docker.

It belongs to this program alone: created in the data folder on the first start, it
listens on 127.0.0.1 only (no Unix socket, whose path may be too long on macOS) and
is stopped with the program.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING
from urllib.parse import quote

from rhinvoice.desktop.folders import make_private

if TYPE_CHECKING:
    from pathlib import Path

USER = "rhinvoice"
DATABASE = "rhinvoice"
SERVER_SETTINGS = """
# Rhinvoice: only this computer, over TCP (no Unix socket, whose path may be too long).
listen_addresses = '127.0.0.1'
unix_socket_directories = ''
"""
NOT_RUNNING = 3
"""Exit code of ``pg_ctl status`` when no server runs on the data folder."""


class PostgresError(Exception):
    """A PostgreSQL tool failed; the message has its output."""


class BundledPostgres:
    def __init__(self, binaries: Path, data: Path, password: str, port: int) -> None:
        self._binaries = binaries
        self._data = data
        self._password = password
        self._port = port

    @property
    def url(self) -> str:
        return (
            f"postgresql+psycopg://{USER}:{quote(self._password, safe='')}"
            f"@127.0.0.1:{self._port}/{DATABASE}"
        )

    @property
    def log(self) -> Path:
        return self._data.parent / "postgresql.log"

    def start(self) -> None:
        """Create the database on the first start, then start the server."""
        if not self._exists():
            self._initialize()
        elif self._running():
            # Left over from a program that was killed: it is ours, so it is restarted.
            self._halt()
        # The server keeps the output handles of pg_ctl open; pipes there would never end
        # (Windows). Its messages go to the log instead.
        started = subprocess.run(  # noqa: S603 - the bundled tool, arguments built here
            [
                str(self._binaries / "pg_ctl"),
                "start",
                "--wait",
                f"--pgdata={self._data}",
                f"--log={self.log}",
                f"--options=-p {self._port}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if started.returncode != 0:
            msg = f"pg_ctl start failed ({started.returncode}): see {self.log}"
            raise PostgresError(msg)
        # Also after a first start that was interrupted between initdb and createdb.
        if not self._has_database():
            self._run("createdb", *self._connection(), DATABASE, password=True)

    def running(self) -> bool:
        """Tell whether the server runs (started by this program, now or earlier)."""
        return self._exists() and self._running()

    def stop(self) -> None:
        """Stop the server if it runs."""
        if self.running():
            self._halt()

    def _halt(self) -> None:
        self._run("pg_ctl", "stop", "--wait", "--mode=fast", f"--pgdata={self._data}")

    def _exists(self) -> bool:
        return (self._data / "PG_VERSION").exists()

    def _initialize(self) -> None:
        make_private(self._data.parent)
        # Beside the database, not in the temporary folder: initdb runs with restricted
        # rights on Windows and may not open files there. Removed right after.
        password_file = self._data.parent / "initdb-password"
        password_file.unlink(missing_ok=True)
        descriptor = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(self._password)
        try:
            # No locale: the same on every system; sorting uses ICU collations (search.py).
            self._run(
                "initdb",
                f"--pgdata={self._data}",
                f"--username={USER}",
                f"--pwfile={password_file}",
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--no-locale",
            )
        finally:
            password_file.unlink()
        with (self._data / "postgresql.conf").open("a", encoding="utf-8") as config:
            config.write(SERVER_SETTINGS)

    def _running(self) -> bool:
        result = self._call("pg_ctl", "status", f"--pgdata={self._data}")
        if result.returncode not in {0, NOT_RUNNING}:
            raise PostgresError(_output("pg_ctl status", result))
        return result.returncode == 0

    def _has_database(self) -> bool:
        result = self._call(
            "psql",
            *self._connection(),
            "--dbname=postgres",
            "--list",
            "--tuples-only",
            "--no-align",
            password=True,
        )
        if result.returncode != 0:
            raise PostgresError(_output("psql", result))
        return DATABASE in {line.split("|")[0] for line in result.stdout.splitlines()}

    def _connection(self) -> tuple[str, ...]:
        return ("--host=127.0.0.1", f"--port={self._port}", f"--username={USER}")

    def _run(self, tool: str, *arguments: str, password: bool = False) -> None:
        result = self._call(tool, *arguments, password=password)
        if result.returncode != 0:
            raise PostgresError(_output(f"{tool} {arguments[0]}", result))

    def _call(
        self, tool: str, *arguments: str, password: bool = False
    ) -> subprocess.CompletedProcess[str]:
        # Only the clients get the password, not the server that pg_ctl starts.
        environ = {**os.environ, "PGPASSWORD": self._password} if password else None
        return subprocess.run(  # noqa: S603 - the bundled tools, arguments built here
            [str(self._binaries / tool), *arguments],
            capture_output=True,
            text=True,
            check=False,
            env=environ,
        )


def _output(command: str, result: subprocess.CompletedProcess[str]) -> str:
    return f"{command} failed ({result.returncode}): {(result.stderr or result.stdout).strip()}"
