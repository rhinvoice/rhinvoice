"""Backups of the installation without Docker: folder, recovery key and archive (ADR 0023).

The backups go to a folder, preferably one a cloud service keeps in sync: Rhinvoice needs
no credentials, and a copy leaves the computer by itself. The recovery key (the restic
password) is generated once and kept in rhinvoice.json, so that backups run unattended;
the person keeps a copy elsewhere.
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from rhinvoice.application.backup.ports import BackupFailed, BackupTarget, FolderSuggestion
from rhinvoice.desktop.config import load_or_create, update

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from rhinvoice.application.backup.ports import Snapshot

FOLDER_NAME = "Rhinvoice-Backup"
"""The folder created inside a suggested cloud folder."""
KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
"""Without 0/O and 1/I, which are easily mixed up when the key is typed from paper."""
KEY_GROUPS = 8
GROUP_LENGTH = 4
VERIFY_EVERY = timedelta(days=7)
"""8 groups of 4 characters out of 32: 160 bits."""


class PreparedArchive(Protocol):
    """A restic repository in a folder (infrastructure.backup.restic.ResticArchive)."""

    def prepare(self) -> None: ...

    def back_up(self) -> Snapshot: ...

    def maintain(self, *, verify: bool) -> None: ...


def new_recovery_key() -> str:
    """Make a key that can be read aloud and typed from paper, e.g. K7QM-2XWP-…."""
    groups = (
        "".join(secrets.choice(KEY_ALPHABET) for _ in range(GROUP_LENGTH))
        for _ in range(KEY_GROUPS)
    )
    return "-".join(groups)


def cloud_folders(system: str, environ: Mapping[str, str], home: Path) -> list[FolderSuggestion]:
    """Find the folders cloud services keep in sync on this computer, as backup folders."""
    found: list[FolderSuggestion] = []
    seen: set[Path] = set()
    for name, folder in _candidates(system, environ, home):
        if folder.is_dir() and folder.resolve() not in seen:
            seen.add(folder.resolve())
            found.append(FolderSuggestion(name=name, path=str(folder / FOLDER_NAME)))
    return found


def _candidates(system: str, environ: Mapping[str, str], home: Path) -> list[tuple[str, Path]]:
    if system == "Windows":
        onedrive = [
            Path(environ[variable])
            for variable in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive")
            if environ.get(variable)
        ]
        return [
            *(("OneDrive", folder) for folder in onedrive),
            ("OneDrive", home / "OneDrive"),
            ("Dropbox", home / "Dropbox"),
            ("iCloud Drive", home / "iCloudDrive"),
            ("Google Drive", home / "Google Drive"),
        ]
    if system == "Darwin":
        # Since macOS 12 the cloud services sync below ~/Library/CloudStorage.
        storage = home / "Library" / "CloudStorage"
        services = sorted(storage.iterdir()) if storage.is_dir() else []
        return [
            ("iCloud Drive", home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"),
            *(("OneDrive", folder) for folder in services if folder.name.startswith("OneDrive")),
            *(("Dropbox", folder) for folder in services if folder.name.startswith("Dropbox")),
            *(
                ("Google Drive", drive)
                for folder in services
                if folder.name.startswith("GoogleDrive")
                for drive in (folder / "My Drive", folder / "Meine Ablage")
            ),
            ("Dropbox", home / "Dropbox"),
        ]
    return [("Dropbox", home / "Dropbox")]


class DesktopBackupSetup:
    """The ``BackupSetup`` port of the installation without Docker."""

    def __init__(
        self,
        config: Path,
        archive_for: Callable[[Path, str], PreparedArchive],
        suggestions: Callable[[], list[FolderSuggestion]],
    ) -> None:
        self._config = config
        self._archive_for = archive_for
        self._suggestions = suggestions

    def folder(self) -> str | None:
        return load_or_create(self._config).backup_folder

    def target(self) -> BackupTarget:
        config = load_or_create(self._config)
        return BackupTarget(
            folder=config.backup_folder,
            suggestions=self._suggestions(),
            key_confirmed=config.backup_key_confirmed,
        )

    def set_up(self, folder: str) -> str:
        path = Path(folder.strip()).expanduser()
        if not path.is_absolute():
            msg = "choose the full path of a folder"
            raise BackupFailed(msg)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            msg = f"the folder cannot be created: {error.strerror or error}"
            raise BackupFailed(msg) from error
        key = load_or_create(self._config).backup_key or new_recovery_key()
        # Creates the repository, or opens the one there: a wrong key is refused here.
        self._archive_for(path, key).prepare()
        update(
            self._config, lambda config: replace(config, backup_folder=str(path), backup_key=key)
        )
        return key

    def recovery_key(self) -> str | None:
        return load_or_create(self._config).backup_key

    def confirm_key(self) -> None:
        update(self._config, lambda config: replace(config, backup_key_confirmed=True))


class CurrentArchive:
    """The ``BackupArchive`` port: the repository in the folder set up right now."""

    def __init__(
        self,
        config: Path,
        archive_for: Callable[[Path, str], PreparedArchive],
        now: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._archive_for = archive_for
        self._now = now

    def back_up(self) -> Snapshot:
        return self._current().back_up()

    def maintain(self, *, verify: bool) -> None:
        """Verify on Sundays (as the backup container), and whenever a week passed without.

        A laptop that is off every Sunday would otherwise never prune or check.
        """
        verified = load_or_create(self._config).backup_verified_at
        now = self._now()
        due = verified is None or now - datetime.fromisoformat(verified) >= VERIFY_EVERY
        self._current().maintain(verify=verify or due)
        if verify or due:
            stamp = now.isoformat()
            update(self._config, lambda config: replace(config, backup_verified_at=stamp))

    def _current(self) -> PreparedArchive:
        config = load_or_create(self._config)
        if config.backup_folder is None or config.backup_key is None:
            msg = "backups are not set up"
            raise BackupFailed(msg)
        return self._archive_for(Path(config.backup_folder), config.backup_key)
