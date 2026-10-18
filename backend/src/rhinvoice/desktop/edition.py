"""Which installation this is: Rhinvoice or Rhinvoice Beta (ADR 0030).

The setup fixes the edition in the runtime (``runtime.json``); the app packages are the same
for both. Rhinvoice Beta is a release candidate's installation beside the released one: its
own name, data, logs and backups, and it is offered release candidates as updates.

Read here, not with the boot's ``edition``: an update runs on the runtime of an earlier
setup, whose boot has no such function (ADR 0022).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

    from rhinvoice.api.settings import UpdateChannel


@dataclass(frozen=True, slots=True)
class Edition:
    name: str
    """The program's name: its windows, its folders on Windows and macOS."""
    beta: bool

    @property
    def update_channel(self) -> UpdateChannel:
        """Rhinvoice Beta is offered release candidates; Rhinvoice never."""
        return "test" if self.beta else "stable"

    @property
    def setup_suffix(self) -> str:
        """Added to the platform for this edition's setup in release.json ("macos-arm64-beta")."""
        return "-beta" if self.beta else ""

    @property
    def mutex(self) -> str:
        """Held on Windows while it runs; its setup waits for it (desktop/windows/rhinvoice.iss)."""
        return f"{self.name.replace(' ', '')}Running"

    @property
    def backup_folder(self) -> str:
        """The folder suggested for backups inside a cloud folder: never the other edition's."""
        return f"{self.name.replace(' ', '-')}-Backup"


STABLE = Edition("Rhinvoice", beta=False)
BETA = Edition("Rhinvoice Beta", beta=True)


def installed_edition(install: Path) -> Edition:
    """Read the edition of the runtime in ``install``; without one it is Rhinvoice."""
    try:
        values = json.loads((install / "runtime.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return STABLE
    if isinstance(values, dict) and cast("dict[str, object]", values).get("edition") == "beta":
        return BETA
    return STABLE
