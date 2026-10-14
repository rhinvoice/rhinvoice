"""Folder, recovery key and archive of the program's own backups (ADR 0023)."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rhinvoice.application.backup.ports import BackupFailed, FolderSuggestion, Snapshot
from rhinvoice.desktop.backup import (
    FOLDER_NAME,
    CurrentArchive,
    DesktopBackupSetup,
    cloud_folders,
    new_recovery_key,
)
from tests.helpers import raises_exactly

SUGGESTION = FolderSuggestion(name="OneDrive", path="/Users/anna/OneDrive/Rhinvoice-Backup")


class Archive:
    """Stands in for ResticArchive; records what it was asked."""

    def __init__(
        self, folder: Path, key: str, log: list[str], *, refuse: str | None = None
    ) -> None:
        self.folder = folder
        self.key = key
        self.log = log
        self.refuse = refuse

    def prepare(self) -> None:
        self.log.append(f"prepare {self.folder} {self.key}")
        if self.refuse is not None:
            raise BackupFailed(self.refuse)

    def back_up(self) -> Snapshot:
        self.log.append(f"back up {self.folder} {self.key}")
        return Snapshot("4f3a9c1e", 1)

    def maintain(self, *, verify: bool) -> None:
        self.log.append(f"maintain {self.folder} {verify}")


@pytest.fixture
def log() -> list[str]:
    return []


@pytest.fixture
def config(tmp_path: Path) -> Path:
    return tmp_path / "data" / "rhinvoice.json"


def setup(config: Path, log: list[str], refuse: str | None = None) -> DesktopBackupSetup:
    return DesktopBackupSetup(
        config,
        lambda folder, key: Archive(folder, key, log, refuse=refuse),
        lambda: [SUGGESTION],
    )


def stored(config: Path) -> dict[str, object]:
    values: dict[str, object] = json.loads(config.read_text())
    return values


def test_recovery_keys_can_be_typed_from_paper() -> None:
    key = new_recovery_key()
    assert re.fullmatch(r"([A-HJ-NP-Z2-9]{4}-){7}[A-HJ-NP-Z2-9]{4}", key)
    assert new_recovery_key() != key


def test_a_folder_is_set_up_with_a_new_key(config: Path, log: list[str], tmp_path: Path) -> None:
    backups = setup(config, log)
    assert backups.target().folder is None
    assert backups.target().suggestions == [SUGGESTION]
    assert backups.recovery_key() is None
    folder = tmp_path / "OneDrive" / FOLDER_NAME
    key = backups.set_up(f"  {folder}  ")
    assert folder.is_dir()
    assert log == [f"prepare {folder} {key}"]
    assert (stored(config)["backup_folder"], stored(config)["backup_key"]) == (str(folder), key)
    assert backups.recovery_key() == key
    assert not backups.target().key_confirmed
    backups.confirm_key()
    assert backups.target().key_confirmed
    # Another folder keeps the key: one key for every backup of this installation.
    assert backups.set_up(str(tmp_path / "USB")) == key
    assert backups.target().folder == str(tmp_path / "USB")


@pytest.mark.parametrize(
    ("folder", "message"),
    [
        ("Rhinvoice-Backup", "choose the full path of a folder"),
        ("{file}/inside", "the folder cannot be created: "),
    ],
)
def test_a_folder_that_cannot_be_used_is_refused(
    config: Path, log: list[str], tmp_path: Path, folder: str, message: str
) -> None:
    file = tmp_path / "a-file"
    file.write_text("")
    with pytest.raises(BackupFailed, match=f"^{re.escape(message)}"):
        setup(config, log).set_up(folder.format(file=file))
    assert log == []
    assert not config.exists() or stored(config).get("backup_folder") is None


def test_a_folder_whose_repository_does_not_open_is_not_used(
    config: Path, log: list[str], tmp_path: Path
) -> None:
    """E.g. another installation's backups with another key."""
    with raises_exactly(BackupFailed, "Fatal: wrong password or no key found"):
        setup(config, log, refuse="Fatal: wrong password or no key found").set_up(
            str(tmp_path / "x")
        )
    assert stored(config).get("backup_folder") is None


def test_the_archive_follows_the_folder_set_up_right_now(
    config: Path, log: list[str], tmp_path: Path
) -> None:
    def archive_for(folder: Path, key: str) -> Archive:
        return Archive(folder, key, log)

    archive = CurrentArchive(config, archive_for, lambda: datetime(2026, 3, 9, tzinfo=UTC))
    with raises_exactly(BackupFailed, "backups are not set up"):
        archive.back_up()
    key = setup(config, log).set_up(str(tmp_path / "first"))
    archive.back_up()
    setup(config, log).set_up(str(tmp_path / "second"))
    archive.back_up()
    archive.maintain(verify=True)
    first, second = tmp_path / "first", tmp_path / "second"
    assert log == [
        f"prepare {first} {key}",
        f"back up {first} {key}",
        f"prepare {second} {key}",
        f"back up {second} {key}",
        f"maintain {second} True",
    ]


def make(folders: list[Path]) -> None:
    for folder in folders:
        folder.mkdir(parents=True)


def test_cloud_folders_on_windows(tmp_path: Path) -> None:
    home = tmp_path / "anna"
    business = tmp_path / "OneDrive - Muster GmbH"
    make([business, home / "OneDrive", home / "Dropbox"])
    environ = {"OneDriveCommercial": str(business), "OneDrive": str(home / "OneDrive")}
    assert cloud_folders("Windows", environ, home) == [
        FolderSuggestion("OneDrive", str(business / FOLDER_NAME)),
        FolderSuggestion("OneDrive", str(home / "OneDrive" / FOLDER_NAME)),
        FolderSuggestion("Dropbox", str(home / "Dropbox" / FOLDER_NAME)),
    ]


def test_cloud_folders_on_macos(tmp_path: Path) -> None:
    home = tmp_path / "anna"
    storage = home / "Library" / "CloudStorage"
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    make(
        [
            icloud,
            storage / "OneDrive-Personal",
            storage / "Dropbox",
            storage / "GoogleDrive-anna@example.com" / "My Drive",
        ]
    )
    assert cloud_folders("Darwin", {}, home) == [
        FolderSuggestion("iCloud Drive", str(icloud / FOLDER_NAME)),
        FolderSuggestion("OneDrive", str(storage / "OneDrive-Personal" / FOLDER_NAME)),
        FolderSuggestion("Dropbox", str(storage / "Dropbox" / FOLDER_NAME)),
        FolderSuggestion(
            "Google Drive", str(storage / "GoogleDrive-anna@example.com" / "My Drive" / FOLDER_NAME)
        ),
    ]
    assert cloud_folders("Darwin", {}, tmp_path / "nobody") == []


def test_cloud_folders_elsewhere(tmp_path: Path) -> None:
    make([tmp_path / "Dropbox"])
    assert cloud_folders("Linux", {}, tmp_path) == [
        FolderSuggestion("Dropbox", str(tmp_path / "Dropbox" / FOLDER_NAME))
    ]


def test_a_week_without_verification_verifies_also_on_a_weekday(
    config: Path, log: list[str], tmp_path: Path
) -> None:
    """A laptop that is off every Sunday still prunes and checks its backups once a week."""
    now = datetime(2026, 3, 9, 10, 0, tzinfo=UTC)  # a Monday
    moments = iter([now, now + timedelta(days=6), now + timedelta(days=7)])

    def archive_for(folder: Path, key: str) -> Archive:
        return Archive(folder, key, log)

    archive = CurrentArchive(config, archive_for, lambda: next(moments))
    setup(config, log).set_up(str(tmp_path / "backups"))
    archive.maintain(verify=False)  # never verified yet
    archive.maintain(verify=False)  # six days later
    archive.maintain(verify=False)  # a week later
    assert [entry.rsplit(" ", 1)[1] for entry in log[1:]] == ["True", "False", "True"]
    assert stored(config)["backup_verified_at"] == "2026-03-16T10:00:00+00:00"
