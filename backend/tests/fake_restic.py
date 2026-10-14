"""A stand-in for restic: the commands ResticArchive runs, with a repository in a folder.

Started as ``fake_restic.py <arguments>``. The repository exists once its folder holds a
``config`` file. Every call is appended to FAKE_RESTIC_LOG as a JSON line, with the
password and database the environment gave it. FAKE_RESTIC_FAIL names a command that
fails with FAKE_RESTIC_ERROR on stderr; FAKE_RESTIC_CAT_CODE replaces the exit code of
``cat config`` (e.g. 1: wrong password); FAKE_RESTIC_NO_SUMMARY leaves out the summary;
FAKE_RESTIC_DUMP replaces the complete dump that ``dump`` writes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATABASE = ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")
COMPLETE_DUMP = "CREATE TABLE public.documents ();\n--\n-- PostgreSQL database dump complete\n--\n"
SNAPSHOTS = """\
ID        Time                 Host       Tags
4f3a9c1e  2026-03-09 09:00:00  rhinvoice  rhinvoice
"""


def command_of(arguments: list[str]) -> str:
    rest = list(arguments)
    while rest and rest[0] == "--retry-lock":
        rest = rest[2:]
    return rest[0] if rest else ""


def main() -> int:
    arguments = sys.argv[1:]
    command = command_of(arguments)
    environ = os.environ
    with Path(environ["FAKE_RESTIC_LOG"]).open("a", encoding="utf-8") as log:
        entry = {
            "command": command,
            "arguments": arguments,
            "password": environ.get("RESTIC_PASSWORD"),
            "repository": environ.get("RESTIC_REPOSITORY"),
            "database": [environ.get(name) for name in DATABASE],
        }
        log.write(json.dumps(entry) + "\n")
    if environ.get("FAKE_RESTIC_FAIL") == command:
        sys.stderr.write(environ.get("FAKE_RESTIC_ERROR", "Fatal: something went wrong") + "\n")
        return 1
    repository = Path(environ["RESTIC_REPOSITORY"])
    if command == "cat":
        code = environ.get("FAKE_RESTIC_CAT_CODE")
        if code is not None:
            sys.stderr.write("Fatal: wrong password or no key found\n")
            return int(code)
        return 0 if (repository / "config").exists() else 10
    if command == "init":
        repository.mkdir(parents=True, exist_ok=True)
        (repository / "config").write_text("fake")
        return 0
    sys.stdout.write(output_of(command))
    return 0


def output_of(command: str) -> str:
    if command == "dump":
        return os.environ.get("FAKE_RESTIC_DUMP", COMPLETE_DUMP)
    if command == "snapshots":
        return SNAPSHOTS
    if command == "backup":
        lines = [{"message_type": "status", "percent_done": 1}]
        if not os.environ.get("FAKE_RESTIC_NO_SUMMARY"):
            lines.append(
                {"message_type": "summary", "snapshot_id": "4f3a9c1e", "data_added": 48000}
            )
        return "".join(json.dumps(line) + "\n" for line in lines)
    return ""


if __name__ == "__main__":
    sys.exit(main())
