"""A stand-in for the PostgreSQL tools that BundledPostgres calls.

Started as ``fake_postgres.py <tool> <arguments>``. The server's state lives in files:
``postmaster.pid`` in the data folder while it runs, FAKE_POSTGRES_DATABASES lists the
databases. Every call is appended to FAKE_POSTGRES_LOG as a JSON line. FAKE_POSTGRES_FAIL
names a call that fails ("initdb", "pg_ctl stop", …); FAKE_POSTGRES_STATUS replaces the
exit code of ``pg_ctl status``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def option(arguments: list[str], name: str) -> str:
    return next(a.split("=", 1)[1] for a in arguments if a.startswith(f"--{name}="))


def main() -> int:
    tool, *arguments = sys.argv[1:]
    command = f"{tool} {arguments[0]}" if tool == "pg_ctl" else tool
    with Path(os.environ["FAKE_POSTGRES_LOG"]).open("a", encoding="utf-8") as log:
        entry = {
            "command": command,
            "arguments": arguments,
            "password": os.environ.get("PGPASSWORD"),
        }
        log.write(json.dumps(entry) + "\n")
    if os.environ.get("FAKE_POSTGRES_FAIL") == command:
        sys.stderr.write("boom\n")
        return 1
    databases = Path(os.environ["FAKE_POSTGRES_DATABASES"])
    if tool == "initdb":
        data = Path(option(arguments, "pgdata"))
        data.mkdir(parents=True)
        (data / "PG_VERSION").write_text("17\n")
        (data / "postgresql.conf").write_text("# initdb\n")
        databases.write_text("postgres\n")
        return 0
    if tool == "psql":
        # As ``psql --list --tuples-only --no-align``: name|owner|encoding|…
        for name in databases.read_text().split():
            sys.stdout.write(f"{name}|rhinvoice|UTF8|libc|C|C\n")
        return 0
    if tool == "createdb":
        databases.write_text(databases.read_text() + arguments[-1] + "\n")
        return 0
    pid = Path(option(arguments, "pgdata")) / "postmaster.pid"
    if command == "pg_ctl status":
        return int(os.environ.get("FAKE_POSTGRES_STATUS", "0" if pid.exists() else "3"))
    if command == "pg_ctl start":
        pid.write_text("1\n")
    else:
        pid.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
