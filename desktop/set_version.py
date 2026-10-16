r"""Give the program the version of the tag it is built from (ADR 0029).

    python desktop/set_version.py 0.8.1

The release builds run it in their checkout before they build the images and the setups:
the version comes from the candidate's tag, never from a commit. It changes the files that
carry the version as a package (backend/pyproject.toml, the package's entry in
backend/uv.lock, the API's version in app.py, frontend/package.json) and nothing else.
"""

# A release tool reports on the console; it is no package.
# ruff: noqa: T201, INP001

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = re.compile(r"\d+\.\d+\.\d+")

# File, and the version in it: one group before it and one after it.
PLACES = (
    ("backend/pyproject.toml", r'(?m)^(version = ")[^"]+(")'),
    ("backend/uv.lock", r'(\[\[package\]\]\r?\nname = "rhinvoice"\r?\nversion = ")[^"]+(")'),
    ("backend/src/rhinvoice/api/app.py", r'(?m)^(        version=")[^"]+(",)'),
    ("frontend/package.json", r'(?m)^(  "version": ")[^"]+(",)'),
)


def set_version(version: str, root: Path = ROOT) -> None:
    if not VERSION.fullmatch(version):
        raise SystemExit(f"a version looks like 0.8.1, not {version!r}")
    for name, pattern in PLACES:
        path = root / name
        # newline="": a checkout on Windows may have CRLF; the file keeps its line endings.
        with path.open(encoding="utf-8", newline="") as file:
            text = file.read()
        changed, count = re.subn(pattern, rf"\g<1>{version}\g<2>", text, count=1)
        if count != 1:
            raise SystemExit(f"{name}: the version line was not found")
        with path.open("w", encoding="utf-8", newline="") as file:
            file.write(changed)
        print(f"{name}: {version}")


if __name__ == "__main__":
    set_version(sys.argv[1])
