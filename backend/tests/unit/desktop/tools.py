"""Reading what the PostgreSQL stand-ins were asked to do."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Call:
    command: str
    """The tool, for pg_ctl with its action, e.g. "pg_ctl start"."""
    arguments: list[str]
    password: str | None
    """PGPASSWORD as the tool saw it."""


def calls(tmp_path: Path) -> list[Call]:
    log = tmp_path / "postgres.jsonl"
    if not log.exists():
        return []
    return [Call(**json.loads(line)) for line in log.read_text(encoding="utf-8").splitlines()]


def commands(tmp_path: Path) -> list[str]:
    return [call.command for call in calls(tmp_path)]
