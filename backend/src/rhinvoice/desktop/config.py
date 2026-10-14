"""The settings an installation without Docker makes for itself on its first start."""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

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
        # The folder holds the database: only for this user.
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.touch(mode=0o600)
        path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
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
