"""Where an installation without Docker keeps its data."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def data_folder(system: str, environ: Mapping[str, str], home: Path) -> Path:
    """Return the folder for the database, the configuration and the logs of this user.

    ``system`` is ``platform.system()``. Backups must include this folder.
    """
    if system == "Windows":
        return Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "Rhinvoice"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Rhinvoice"
    return Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "rhinvoice"
