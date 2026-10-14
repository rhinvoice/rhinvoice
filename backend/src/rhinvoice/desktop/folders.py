"""Where an installation without Docker keeps its data."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def make_private(folder: Path) -> None:
    """Create a folder that only this user can open.

    On Windows the folders below %LOCALAPPDATA% are the user's own already. There Python
    turns 0o700 into an access list that the database's tools cannot pass: they run with
    restricted rights (PostgreSQL does that on purpose).
    """
    folder.mkdir(mode=0o700 if os.name != "nt" else 0o777, parents=True, exist_ok=True)


def data_folder(system: str, environ: Mapping[str, str], home: Path) -> Path:
    """Return the folder for the database, the configuration and the logs of this user.

    ``system`` is ``platform.system()``. Backups must include this folder.
    """
    if system == "Windows":
        return Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "Rhinvoice"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Rhinvoice"
    return Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "rhinvoice"
