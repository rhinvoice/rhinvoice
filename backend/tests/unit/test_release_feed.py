"""The signed release.json, against a simulated GitHub (httpx.MockTransport)."""

import base64
import json
from collections.abc import Callable
from typing import cast

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from rhinvoice.application.updates.ports import PackageFile, Release
from rhinvoice.infrastructure.updates.feed import (
    DOWNLOAD_URL,
    MAX_BYTES,
    PUBLIC_KEY,
    RELEASE_URL,
    RELEASES_URL,
    NewestRelease,
    SignedReleaseFeed,
    release_feed,
)

URL = "https://github.com/rhinvoice/rhinvoice/releases/latest/download/release.json"
KEY = Ed25519PrivateKey.generate()
PUBLIC = base64.b64encode(
    KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
).decode()
MANIFEST: dict[str, object] = {
    "version": "0.7.0",
    "notes_url": "https://github.com/rhinvoice/rhinvoice/releases/tag/v0.7.0",
    "runtime": 1,
    "packages": {
        "windows-x64": {
            "url": "https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.0/app.zip",
            "sha256": "ab" * 32,
            "size": 41_000_000,
        }
    },
    "setups": {
        "windows-x64": "https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.0/Setup.exe"
    },
    "setup_files": {
        "windows-x64": {
            "url": "https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.0/Setup.exe",
            "sha256": "cd" * 32,
            "size": 58_000_000,
        }
    },
}


def signed(content: bytes, key: Ed25519PrivateKey = KEY) -> bytes:
    return base64.b64encode(key.sign(content)) + b"\n"


def github(
    manifest: bytes, signature: bytes, status: int = 200
) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == URL:
            return httpx.Response(status, content=manifest)
        if str(request.url) == URL + ".sig":
            return httpx.Response(status, content=signature)
        return httpx.Response(404)

    return handle


def feed(handle: Callable[[httpx.Request], httpx.Response]) -> SignedReleaseFeed:
    client = httpx.Client(transport=httpx.MockTransport(handle))
    return SignedReleaseFeed(URL, PUBLIC, client)


def test_a_signed_release_is_read() -> None:
    content = json.dumps(MANIFEST).encode()
    assert feed(github(content, signed(content))).latest() == Release(
        version="0.7.0",
        notes_url="https://github.com/rhinvoice/rhinvoice/releases/tag/v0.7.0",
        runtime=1,
        packages={
            "windows-x64": PackageFile(
                url="https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.0/app.zip",
                sha256="ab" * 32,
                size=41_000_000,
            )
        },
        setups={
            "windows-x64": "https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.0/Setup.exe"
        },
        setup_files={
            "windows-x64": PackageFile(
                url="https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.0/Setup.exe",
                sha256="cd" * 32,
                size=58_000_000,
            )
        },
    )


def test_a_release_without_packages_or_setups_is_a_server_release() -> None:
    content = json.dumps({"version": "0.7.0", "notes_url": "https://x", "runtime": 1}).encode()
    release = feed(github(content, signed(content))).latest()
    assert release is not None
    assert (release.packages, release.setups, release.setup_files) == ({}, {}, {})


def altered(content: bytes) -> bytes:
    return content.replace(b"0.7.0", b"9.9.9")


@pytest.mark.parametrize(
    ("manifest", "signature"),
    [
        # Changed after signing, or signed by someone else.
        (altered(json.dumps(MANIFEST).encode()), signed(json.dumps(MANIFEST).encode())),
        (
            json.dumps(MANIFEST).encode(),
            signed(json.dumps(MANIFEST).encode(), Ed25519PrivateKey.generate()),
        ),
        (json.dumps(MANIFEST).encode(), b"not base64!"),
        # Signed, but not a release.json.
        (b"not json", signed(b"not json")),
        (b"[]", signed(b"[]")),
        (json.dumps({**MANIFEST, "version": 7}).encode(), None),
        (json.dumps({**MANIFEST, "runtime": True}).encode(), None),
        (json.dumps({**MANIFEST, "packages": {"windows-x64": {"url": "x"}}}).encode(), None),
        (json.dumps({**MANIFEST, "packages": {"windows-x64": []}}).encode(), None),
        (json.dumps({**MANIFEST, "setups": {"windows-x64": 1}}).encode(), None),
        (json.dumps({**MANIFEST, "setup_files": {"windows-x64": "x"}}).encode(), None),
        (b" " * (MAX_BYTES + 1), None),
    ],
)
def test_anything_but_a_signed_release_counts_as_unknown(
    manifest: bytes, signature: bytes | None
) -> None:
    assert feed(github(manifest, signature or signed(manifest))).latest() is None


def package(**changes: object) -> dict[str, object]:
    return {**MANIFEST, "packages": {"windows-x64": {**PACKAGE, **changes}}}


PACKAGE = cast("dict[str, dict[str, object]]", MANIFEST["packages"])["windows-x64"]


@pytest.mark.parametrize(
    "manifest",
    [
        # The version names folders in the data folder: only ASCII digits and dots.
        {**MANIFEST, "version": "../../evil"},
        {**MANIFEST, "version": "0.7"},
        {**MANIFEST, "version": "0.7.0-rc.1"},
        {**MANIFEST, "version": "0.7.0\n"},
        {**MANIFEST, "version": " 0.7.0"},
        {**MANIFEST, "version": "0.7.0 "},
        {**MANIFEST, "version": "0.7_0.0"},
        {**MANIFEST, "version": "0.7.\u0661"},  # an Arabic-Indic one
        {**MANIFEST, "version": "\uff10.7.0"},  # a fullwidth zero
        {**MANIFEST, "version": "0.7.0/.."},
        # Addresses are downloaded or shown as links: https only.
        {**MANIFEST, "notes_url": "javascript:alert(1)"},
        {**MANIFEST, "notes_url": "http://github.com/rhinvoice"},
        {**MANIFEST, "notes_url": "https://"},
        {**MANIFEST, "notes_url": "https://github.com/a b"},
        {**MANIFEST, "notes_url": "https://github.com/\u0000"},
        {**MANIFEST, "notes_url": 7},
        {**MANIFEST, "setups": {"windows-x64": "file:///C:/Windows/evil.exe"}},
        package(url="http://github.com/app.zip"),
        package(url="file:///tmp/app.zip"),
        package(sha256="AB" * 32),
        package(sha256="ab" * 31),
        package(sha256=" " + "ab" * 32),
        package(sha256="zz" * 32),
        {**MANIFEST, "setup_files": {"windows-x64": {**PACKAGE, "url": "ftp://x/Setup.exe"}}},
        # A candidate's number (ADR 0035).
        {**MANIFEST, "candidate": 0},
        {**MANIFEST, "candidate": "3"},
        {**MANIFEST, "candidate": True},
        {**MANIFEST, "candidate": None},
    ],
)
def test_a_signed_release_with_unexpected_values_counts_as_unknown(
    manifest: dict[str, object],
) -> None:
    content = json.dumps(manifest).encode()
    assert feed(github(content, signed(content))).latest() is None


def test_a_release_names_the_candidate_its_packages_were_built_as() -> None:
    """ADR 0035; programs before it ignore the field."""
    content = json.dumps({**MANIFEST, "candidate": 3}).encode()
    release = feed(github(content, signed(content))).latest()
    assert release is not None
    assert release.candidate == 3
    content = json.dumps(MANIFEST).encode()
    release = feed(github(content, signed(content))).latest()
    assert release is not None
    assert release.candidate is None


def test_an_unreachable_or_missing_release_counts_as_unknown() -> None:
    content = json.dumps(MANIFEST).encode()
    assert feed(github(content, signed(content), status=404)).latest() is None

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    assert feed(offline).latest() is None


def test_by_default_the_release_of_the_project_is_read() -> None:
    assert RELEASE_URL == URL
    # The project's key decodes; the feed can be built without arguments.
    assert len(base64.b64decode(PUBLIC_KEY)) == 32
    assert SignedReleaseFeed() is not None


CANDIDATE_URL = "https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.4-rc.2/release.json"


def candidates(listing: object) -> Callable[[httpx.Request], httpx.Response]:
    """GitHub with a release candidate as its newest release."""
    content = json.dumps({**MANIFEST, "version": "0.7.4"}).encode()

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == RELEASES_URL:
            return httpx.Response(200, json=listing)
        if str(request.url) == CANDIDATE_URL:
            return httpx.Response(200, content=content)
        if str(request.url) == CANDIDATE_URL + ".sig":
            return httpx.Response(200, content=signed(content))
        return httpx.Response(404)

    return handle


def test_the_test_channel_reads_the_newest_release_candidate() -> None:
    client = httpx.Client(transport=httpx.MockTransport(candidates([{"tag_name": "v0.7.4-rc.2"}])))
    release = SignedReleaseFeed(NewestRelease(), PUBLIC, client).latest()
    assert release is not None
    assert release.version == "0.7.4"


@pytest.mark.parametrize(
    "listing",
    [
        [],  # no release yet
        {"message": "API rate limit exceeded"},
        [{"name": "v0.7.4"}],
        [{"tag_name": "v0.7.4/../../evil"}],  # only a release tag goes into the address
        [{"tag_name": "latest"}],
        [{"tag_name": "v0.7.\u0664"}],  # an Arabic-Indic digit
    ],
)
def test_a_listing_without_a_release_tag_counts_as_unknown(listing: object) -> None:
    client = httpx.Client(transport=httpx.MockTransport(candidates(listing)))
    assert SignedReleaseFeed(NewestRelease(), PUBLIC, client).latest() is None


def test_each_channel_has_its_feed() -> None:
    assert DOWNLOAD_URL.format(tag="v0.7.4-rc.2") == CANDIDATE_URL
    assert isinstance(release_feed("stable"), SignedReleaseFeed)
    assert isinstance(release_feed("test"), SignedReleaseFeed)
