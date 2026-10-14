"""Stand-ins for the bundled PostgreSQL tools (tests/fake_postgres.py)."""

import sys
from pathlib import Path

import pytest

FAKE = Path(__file__).parent.parent.parent / "fake_postgres.py"
TOOLS = ("initdb", "pg_ctl", "createdb", "psql")


@pytest.fixture(scope="session")
def tools(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the stand-ins once: macOS checks every new program on its first start (~2 s)."""
    binaries = tmp_path_factory.mktemp("postgresql") / "bin"
    binaries.mkdir()
    for tool in TOOLS:
        script = binaries / tool
        script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {tool} "$@"\n')
        script.chmod(0o755)
    return binaries


@pytest.fixture
def install(tmp_path: Path, tools: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Make an installed program's folder whose PostgreSQL tools are stand-ins."""
    folder = tmp_path / "install"
    (folder / "postgresql").mkdir(parents=True)
    (folder / "postgresql" / "bin").symlink_to(tools)
    monkeypatch.setenv("FAKE_POSTGRES_LOG", str(tmp_path / "postgres.jsonl"))
    monkeypatch.setenv("FAKE_POSTGRES_DATABASES", str(tmp_path / "databases"))
    monkeypatch.delenv("FAKE_POSTGRES_FAIL", raising=False)
    monkeypatch.delenv("FAKE_POSTGRES_STATUS", raising=False)
    monkeypatch.delenv("PGPASSWORD", raising=False)
    return folder
