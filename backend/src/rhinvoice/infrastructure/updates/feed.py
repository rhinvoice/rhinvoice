"""The newest release, from the signed release.json of the latest GitHub release (ADR 0022).

The release workflow signs release.json with an Ed25519 key that only it has; this program
knows the public key. A file whose signature does not verify is ignored, so a forged or
altered release can neither be offered nor installed. Any failure only means: unknown.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Protocol, cast

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from rhinvoice.application.updates.ports import PackageFile, Release

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

RELEASE_URL = "https://github.com/rhinvoice/rhinvoice/releases/latest/download/release.json"
RELEASES_URL = "https://api.github.com/repos/rhinvoice/rhinvoice/releases?per_page=1"
"""The newest release first, pre-releases (release candidates) included."""
DOWNLOAD_URL = "https://github.com/rhinvoice/rhinvoice/releases/download/{tag}/release.json"
TAG = re.compile(r"v\d+\.\d+\.\d+(-rc\.\d+)?")
PUBLIC_KEY = "F9FfvPZ4GxQ4qsItTuEIZPX/gcah6DYPhU0pUFkw8eI="
"""Of the key in the release workflow's secret RELEASE_SIGNING_KEY."""
TIMEOUT_SECONDS = 10.0
MAX_BYTES = 256 * 1024

logger = logging.getLogger(__name__)


def installed_version() -> str:
    """Return the version of this program, as its package says (0.0.0 in a bare source tree)."""
    try:
        return version("rhinvoice")
    except PackageNotFoundError:  # pragma: no cover - only when run from a bare source tree
        return "0.0.0"


class ManifestLocation(Protocol):
    def url(self, get: Callable[[str], bytes]) -> str:
        """Return where the release.json is; ``get`` downloads what it needs to find out."""
        ...


class FixedLocation:
    """One address: the latest release (releases/latest never leads to a pre-release)."""

    def __init__(self, url: str) -> None:
        self._url = url

    def url(self, get: Callable[[str], bytes]) -> str:
        del get
        return self._url


class NewestRelease:
    """The release.json of the newest release, release candidates included (test channel)."""

    def __init__(self, listing: str = RELEASES_URL, download: str = DOWNLOAD_URL) -> None:
        self._listing = listing
        self._download = download

    def url(self, get: Callable[[str], bytes]) -> str:
        releases = json.loads(get(self._listing))
        if not isinstance(releases, list) or not releases:
            msg = "no release is listed"
            raise ValueError(msg)
        tag = _text(_object(cast("list[object]", releases)[0]), "tag_name")
        # Only a release's own tag goes into the address.
        if not TAG.fullmatch(tag):
            msg = f"'{tag}' is not a release tag"
            raise ValueError(msg)
        return self._download.format(tag=tag)


class SignedReleaseFeed:
    def __init__(
        self,
        location: str | ManifestLocation = RELEASE_URL,
        public_key: str = PUBLIC_KEY,
        client: httpx.Client | None = None,
    ) -> None:
        self._location = FixedLocation(location) if isinstance(location, str) else location
        self._key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)

    def latest(self) -> Release | None:
        try:
            url = self._location.url(self._get)
            manifest = self._get(url)
            signature = base64.b64decode(self._get(url + ".sig").strip(), validate=True)
            self._key.verify(signature, manifest)
            return read_release(json.loads(manifest))
        except (httpx.HTTPError, InvalidSignature, binascii.Error, ValueError, TypeError) as error:
            logger.warning("no information about new releases: %s", error or type(error).__name__)
            return None

    def _get(self, url: str) -> bytes:
        content = bytearray()
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                content += chunk
                # Stopped while reading: a huge answer never fills the memory.
                if len(content) > MAX_BYTES:
                    msg = f"{url} is larger than {MAX_BYTES} bytes"
                    raise ValueError(msg)
        return bytes(content)


def release_feed(channel: str) -> SignedReleaseFeed:
    """Return the feed of a channel: "test" includes release candidates, any other the latest."""
    return SignedReleaseFeed(NewestRelease() if channel == "test" else RELEASE_URL)


def read_release(values: object) -> Release:
    """Read a release.json; refuse anything that is not exactly its format."""
    fields = _object(values)
    packages = {
        platform: _package(item) for platform, item in _object(fields.get("packages", {})).items()
    }
    setups = {
        platform: _text_value(url) for platform, url in _object(fields.get("setups", {})).items()
    }
    return Release(
        version=_text(fields, "version"),
        notes_url=_text(fields, "notes_url"),
        runtime=_number(fields, "runtime"),
        packages=packages,
        setups=setups,
    )


def _package(value: object) -> PackageFile:
    fields = _object(value)
    return PackageFile(
        url=_text(fields, "url"), sha256=_text(fields, "sha256"), size=_number(fields, "size")
    )


def _object(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        msg = f"expected an object, got {type(value).__name__}"
        raise TypeError(msg)
    # Keys of JSON objects are always text.
    return cast("dict[str, object]", value)


def _text(fields: Mapping[str, object], key: str) -> str:
    return _text_value(fields.get(key), key)


def _text_value(value: object, key: str = "value") -> str:
    if not isinstance(value, str):
        msg = f"'{key}' is not text"
        raise TypeError(msg)
    return value


def _number(fields: Mapping[str, object], key: str) -> int:
    value = fields.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"'{key}' is not a number"
        raise TypeError(msg)
    return value
