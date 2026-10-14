"""The settings an installation without Docker makes for itself on its first start."""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

from rhinvoice.desktop.folders import make_private

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_PORT = 8000
PASSWORD_BYTES = 24


class ConfigError(Exception):
    """The configuration file cannot be read."""


@dataclass(frozen=True, slots=True)
class DesktopConfig:
    database_password: str
    """Generated once; the database only listens on 127.0.0.1."""
    port: int = DEFAULT_PORT
    """Port of the web interface on 127.0.0.1."""


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
        )
    except (ValueError, TypeError) as error:
        msg = f"{path} is damaged: {error}"
        raise ConfigError(msg) from error


def save(path: Path, config: DesktopConfig) -> None:
    """Write the configuration, readable for this user only."""
    # The folder holds the database: only for this user.
    make_private(path.parent)
    path.touch(mode=0o600)
    path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")


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
