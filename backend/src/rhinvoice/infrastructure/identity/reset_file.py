"""The code for a forgotten password, as a file in the private data folder (ADR 0024)."""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

FILE_NAME = "Rhinvoice-Passwort-Password.txt"
OPEN_SECONDS = 10


class FileResetDelivery:
    """Writes the code where only this computer's user can read it, and opens the file."""

    def __init__(self, folder: Path, opener: Callable[[Path], None] | None = None) -> None:
        self.path = folder / FILE_NAME
        self._opener = opener

    def deliver(self, code: str, accounts: list[str], valid_until: datetime) -> None:
        until = valid_until.astimezone().strftime("%H:%M")
        listed = "\n".join(f"  {account}" for account in accounts)
        text = (
            "Rhinvoice: Passwort vergessen\n\n"
            f"Code: {code}\n"
            f"Gültig bis {until} Uhr, nur einmal.\n\n"
            f"Konten (E-Mail-Adresse für die Anmeldung):\n{listed}\n\n"
            "Geben Sie den Code im Rhinvoice-Fenster ein. Diese Datei wird danach gelöscht.\n"
            "Wenn Sie das nicht angefordert haben, können Sie die Datei löschen.\n\n"
            "---\n\n"
            "Rhinvoice: Forgotten password\n\n"
            f"Code: {code}\n"
            f"Valid until {until}, once.\n\n"
            f"Accounts (e-mail address to sign in):\n{listed}\n\n"
            "Enter the code in the Rhinvoice window. This file is deleted afterwards.\n"
            "If you did not ask for it, you can delete the file.\n"
        )
        # Readable for this user only; written in one piece so no other program sees half of it.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(text)
        if self._opener is not None:
            self._opener(self.path)

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)


def open_with_system(path: Path) -> None:
    """Show the file in the program the computer opens text files with; quietly not, if none."""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - the file the program just wrote
            return
        command = "/usr/bin/open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([command, str(path)], check=False, timeout=OPEN_SECONDS)  # noqa: S603
