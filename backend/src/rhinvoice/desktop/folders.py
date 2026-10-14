"""Where an installation without Docker keeps its data.

The data folder itself is chosen by the boot of the runtime (rhinvoice_boot.data_folder).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def make_private(folder: Path) -> None:
    """Create a folder that only this user can open.

    On Windows the folders below %LOCALAPPDATA% are the user's own already. There Python
    turns 0o700 into an access list that the database's tools cannot pass: they run with
    restricted rights (PostgreSQL does that on purpose).
    """
    folder.mkdir(mode=0o700 if os.name != "nt" else 0o777, parents=True, exist_ok=True)
