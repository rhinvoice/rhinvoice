"""The settings an installation without Docker makes for itself on its first start."""

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

from rhinvoice_boot import make_private

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

DEFAULT_PORT = 8000
_CHANGING = threading.Lock()
"""The API's threads and the backup job change the file at the same time."""
PASSWORD_BYTES = 24


class ConfigError(Exception):
    """The configuration file cannot be read."""


@dataclass(frozen=True, slots=True)
class DesktopConfig:
    database_password: str
    """Generated once; the database only listens on 127.0.0.1."""
    port: int = DEFAULT_PORT
    """Port of the web interface on 127.0.0.1."""
    backup_folder: str | None = None
    """Where the backups go (ADR 0023); None before they are set up."""
    backup_key: str | None = None
    """The recovery key that encrypts the backups (the restic password)."""
    backup_key_confirmed: bool = False
    """The person confirmed that the key is kept elsewhere."""
    backup_verified_at: str | None = None
    """When the backups were last pruned and checked (ISO 8601)."""
    update_check: bool = True
    """false: the program never asks GitHub for a newer version. Which versions it is
    offered follows the edition, not this file (ADR 0030): an "update_channel" written
    here by hand is no longer read."""


def load_or_create(path: Path) -> DesktopConfig:
    """Read the configuration, or write a new one with a random database password."""
    if not path.exists():
        config = DesktopConfig(database_password=secrets.token_hex(PASSWORD_BYTES))
        save(path, config)
        return config
    try:
        values = _fields(json.loads(path.read_text(encoding="utf-8")))
        return DesktopConfig(
            database_password=_text(values, "database_password"),
            port=_number(values, "port"),
            backup_folder=_optional_text(values, "backup_folder"),
            backup_key=_optional_text(values, "backup_key"),
            backup_key_confirmed=_flag(values, "backup_key_confirmed"),
            backup_verified_at=_optional_text(values, "backup_verified_at"),
            update_check=_update_check(values),
        )
    except (ValueError, TypeError) as error:
        msg = f"{path} is damaged: {error}"
        raise ConfigError(msg) from error


def save(path: Path, config: DesktopConfig) -> None:
    """Write the configuration, readable for this user only, whole or not at all.

    It holds the database password and the recovery key: a write cut short must not
    leave half a file.
    """
    # The folder holds the database: only for this user.
    make_private(path.parent)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(json.dumps(asdict(config), indent=2) + "\n")
    temporary.replace(path)


def update(path: Path, change: Callable[[DesktopConfig], DesktopConfig]) -> DesktopConfig:
    """Read, change and write the configuration as one step for the threads of this program."""
    with _CHANGING:
        changed = change(load_or_create(path))
        save(path, changed)
        return changed


def _fields(values: object) -> dict[str, object]:
    if not isinstance(values, dict):
        msg = "not a JSON object"
        raise TypeError(msg)
    # Keys of JSON objects are always text.
    return cast("dict[str, object]", values)


def _text(values: dict[str, object], key: str) -> str:
    if not isinstance(value := values.get(key), str):
        msg = f"'{key}' is missing"
        raise TypeError(msg)
    return value


def _number(values: dict[str, object], key: str) -> int:
    if not isinstance(value := values.get(key, DEFAULT_PORT), int):
        msg = f"'{key}' is not a number"
        raise TypeError(msg)
    return value


def _optional_text(values: dict[str, object], key: str) -> str | None:
    if not isinstance(value := values.get(key), str | None):
        msg = f"'{key}' is not text"
        raise TypeError(msg)
    return value


def _flag(values: dict[str, object], key: str) -> bool:
    if not isinstance(value := values.get(key, False), bool):
        msg = f"'{key}' is not true or false"
        raise TypeError(msg)
    return value


def _update_check(values: dict[str, object]) -> bool:
    """Read whether to look for updates; only a written false switches it off."""
    return values.get("update_check") is not False
