r"""Write and sign release.json for a release (ADR 0022, 0033).

    RELEASE_SIGNING_KEY="$(cat key.pem)" uv run --project desktop/signing --frozen \\
        python desktop/release_manifest.py 0.7.4 build/release --tag v0.7.4-rc.1

Reads the release's files in the folder (``rhinvoice-app-<version>-<platform>.zip``,
``Rhinvoice-Setup-<version>.exe``), writes ``release.json`` with their download URLs,
sizes and SHA-256 under the release's tag (a candidate's ``vX.Y.Z-rc.N``, or ``vX.Y.Z``
once it is released), and ``release.json.sig`` with its Ed25519 signature. Before it ends it
checks the signature the way every installation will: with the public key the program
carries. Both files then belong to the GitHub release.

    uv run --project desktop/signing --frozen python desktop/release_manifest.py \\
        0.7.4 build/release --verify build/candidate --tag v0.7.4-rc.2

checks instead, without a key, that the files in the folder are the candidate's: its
``release.json`` in ``build/candidate`` must carry a valid signature and list every file
with the same size and SHA-256. The promotion runs it before it signs the release.

It needs nothing but ``cryptography`` (ADR 0033): the signing key never meets the
backend's packages.
"""

# A release tool reports on the console; it is no package.
# ruff: noqa: T201, INP001

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path
from typing import cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

REPOSITORY = "https://github.com/rhinvoice/rhinvoice"
# The key every installation checks release.json with; the same as PUBLIC_KEY in
# rhinvoice.infrastructure.updates.feed (a test compares them).
PUBLIC_KEY = "F9FfvPZ4GxQ4qsItTuEIZPX/gcah6DYPhU0pUFkw8eI="
# Without the version, so that releases/latest/download/<name> always leads to the newest
# setup (the download buttons on rhinvoice.com); the release workflow renames them.
SETUPS = {
    "Rhinvoice-Setup-Windows.exe": "windows-x64",
    "Rhinvoice-macOS.dmg": "macos-arm64",
    # Rhinvoice Beta's, only in a candidate (ADR 0030): its runtime needs its own setup.
    "Rhinvoice-Beta-Setup-Windows.exe": "windows-x64-beta",
    "Rhinvoice-Beta-macOS.dmg": "macos-arm64-beta",
}
MANIFEST = "release.json"
SIGNATURE = "release.json.sig"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_entry(path: Path, tag: str) -> dict[str, object]:
    """Where a file of the release is, with what the program checks after the download."""
    return {
        "url": f"{REPOSITORY}/releases/download/{tag}/{path.name}",
        "sha256": sha256(path),
        "size": path.stat().st_size,
    }


def package_entry(path: Path, version: str, tag: str) -> tuple[dict[str, object], int]:
    """Describe an app package; return it with the runtime generation it needs."""
    with zipfile.ZipFile(path) as package:
        manifest = json.loads(package.read("manifest.json"))
    if manifest["version"] != version:
        msg = f"{path.name} holds version {manifest['version']}, not {version}"
        raise SystemExit(msg)
    return file_entry(path, tag), int(manifest["runtime"])


def manifest(version: str, folder: Path, tag: str) -> dict[str, object]:
    pattern = re.compile(
        rf"rhinvoice-app-{re.escape(version)}-(?P<platform>[a-z0-9]+-[a-z0-9]+)\.zip"
    )
    packages: dict[str, dict[str, object]] = {}
    runtimes: set[int] = set()
    for path in sorted(folder.iterdir()):
        if match := pattern.fullmatch(path.name):
            packages[match["platform"]], runtime = package_entry(path, version, tag)
            runtimes.add(runtime)
    if len(runtimes) > 1:
        msg = f"the app packages need different runtimes: {sorted(runtimes)}"
        raise SystemExit(msg)
    present = {platform: folder / name for name, platform in SETUPS.items()}
    present = {platform: path for platform, path in present.items() if path.exists()}
    # "setups" for the programs before ADR 0031, which only read the links; "setup_files"
    # lets a program download and check the setup itself (ADR 0031).
    setups = {
        platform: f"{REPOSITORY}/releases/download/{tag}/{path.name}"
        for platform, path in present.items()
    }
    setup_files = {platform: file_entry(path, tag) for platform, path in present.items()}
    return {
        "version": version,
        "notes_url": f"{REPOSITORY}/releases/tag/{tag}",
        "runtime": runtimes.pop() if runtimes else 1,
        "packages": packages,
        "setups": setups,
        "setup_files": setup_files,
    }


def sign(content: bytes, pem: str) -> bytes:
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        msg = "RELEASE_SIGNING_KEY is not an Ed25519 key"
        raise SystemExit(msg)
    return base64.b64encode(key.sign(content)) + b"\n"


def check_signature(content: bytes, signature: bytes) -> None:
    """Check a release.json as every installation does; end the run if it does not pass."""
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY)).verify(
            base64.b64decode(signature.strip(), validate=True), content
        )
    except (InvalidSignature, binascii.Error, ValueError) as error:
        msg = "the signature of release.json does not match the program's public key"
        raise SystemExit(msg) from error


def listed_files(release: dict[str, object], tag: str) -> dict[str, tuple[str, int]]:
    """Name, SHA-256 and size of every file a signed release.json describes."""
    prefix = f"{REPOSITORY}/releases/download/{tag}/"
    files: dict[str, tuple[str, int]] = {}
    for section in ("packages", "setup_files"):
        entries = release.get(section, {})
        if not isinstance(entries, dict):
            msg = f"release.json: '{section}' is not an object"
            raise SystemExit(msg)
        for entry in cast("dict[str, object]", entries).values():
            if not isinstance(entry, dict):
                msg = f"release.json: an entry of '{section}' is not an object"
                raise SystemExit(msg)
            fields = cast("dict[str, object]", entry)
            url, digest, size = fields.get("url"), fields.get("sha256"), fields.get("size")
            if not (isinstance(url, str) and url.startswith(prefix) and isinstance(digest, str)):
                msg = f"release.json: {url!r} is no file of {tag} with a SHA-256"
                raise SystemExit(msg)
            if not isinstance(size, int) or isinstance(size, bool):
                msg = f"release.json: {url} has no size"
                raise SystemExit(msg)
            files[url.removeprefix(prefix)] = (digest, size)
    return files


def verify_candidate(version: str, folder: Path, candidate: Path, tag: str) -> list[str]:
    """Check that every file in the folder is the candidate's; return their names.

    The candidate's release.json (in ``candidate``, with its signature) must be signed with
    the program's key, be for this version and list each file with its size and SHA-256.
    """
    content = (candidate / MANIFEST).read_bytes()
    check_signature(content, (candidate / SIGNATURE).read_bytes())
    release = json.loads(content)
    if not isinstance(release, dict):
        msg = "release.json is not an object"
        raise SystemExit(msg)
    release = cast("dict[str, object]", release)
    if release.get("version") != version:
        msg = f"the candidate's release.json is for {release.get('version')!r}, not {version}"
        raise SystemExit(msg)
    listed = listed_files(release, tag)
    names = sorted(path.name for path in folder.iterdir())
    if not names:
        msg = f"{folder} holds no files to check"
        raise SystemExit(msg)
    for name in names:
        if name not in listed:
            msg = f"{name} is not in the candidate's release.json"
            raise SystemExit(msg)
        path = folder / name
        expected_digest, expected_size = listed[name]
        if path.stat().st_size != expected_size or sha256(path) != expected_digest:
            msg = f"{name} differs from the file the candidate's release.json describes"
            raise SystemExit(msg)
    return names


def write_signed(version: str, folder: Path, tag: str, pem: str) -> dict[str, object]:
    content = (json.dumps(manifest(version, folder, tag), indent=2) + "\n").encode()
    signature = sign(content, pem)
    # Checked as every installation will: with the program's public key.
    check_signature(content, signature)
    (folder / MANIFEST).write_bytes(content)
    (folder / SIGNATURE).write_bytes(signature)
    return cast("dict[str, object]", json.loads(content))


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("folder", type=Path)
    parser.add_argument(
        "--tag",
        help="the release's tag (default: v<version>); with --verify the candidate's tag",
    )
    parser.add_argument(
        "--verify",
        type=Path,
        metavar="CANDIDATE",
        help="only check the files against the candidate's signed release.json in this folder",
    )
    args = parser.parse_args(arguments)
    version = cast("str", args.version)
    folder = cast("Path", args.folder)
    tag = cast("str | None", args.tag) or f"v{version}"
    candidate = cast("Path | None", args.verify)
    if candidate is not None:
        names = verify_candidate(version, folder, candidate, tag)
        print(f"{len(names)} files are the candidate's {tag}: {', '.join(names)}")
        return
    pem = os.environ.get("RELEASE_SIGNING_KEY")
    if not pem:
        msg = "set RELEASE_SIGNING_KEY to the private key (PEM)"
        raise SystemExit(msg)
    release = write_signed(version, folder, tag, pem)
    packages = cast("dict[str, object]", release["packages"])
    platforms = ", ".join(packages) or "none (server release)"
    print(f"release.json for {version} signed; app packages: {platforms}")


if __name__ == "__main__":
    main()
