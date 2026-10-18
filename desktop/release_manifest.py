r"""Write and sign release.json for a release (ADR 0022).

    RELEASE_SIGNING_KEY="$(cat key.pem)" uv run --project backend \\
        python desktop/release_manifest.py 0.7.4 build/release --tag v0.7.4-rc.1

Reads the release's files in the folder (``rhinvoice-app-<version>-<platform>.zip``,
``Rhinvoice-Setup-<version>.exe``), writes ``release.json`` with their download URLs,
sizes and SHA-256 under the release's tag (a candidate's ``vX.Y.Z-rc.N``, or ``vX.Y.Z``
once it is released), and ``release.json.sig`` with its Ed25519 signature. Before it ends it
checks the result the way every installation will: with the public key the program
carries and its own reader. Both files then belong to the GitHub release.
"""

# A release tool reports on the console; it is no package.
# ruff: noqa: T201, INP001

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from rhinvoice.infrastructure.updates.feed import PUBLIC_KEY, read_release

REPOSITORY = "https://github.com/rhinvoice/rhinvoice"
# Without the version, so that releases/latest/download/<name> always leads to the newest
# setup (the download buttons on rhinvoice.com); the release workflow renames them.
SETUPS = {
    "Rhinvoice-Setup-Windows.exe": "windows-x64",
    "Rhinvoice-macOS.dmg": "macos-arm64",
    # Rhinvoice Beta's, only in a candidate (ADR 0030): its runtime needs its own setup.
    "Rhinvoice-Beta-Setup-Windows.exe": "windows-x64-beta",
    "Rhinvoice-Beta-macOS.dmg": "macos-arm64-beta",
}


def package_entry(path: Path, version: str, tag: str) -> tuple[dict[str, object], int]:
    """Describe an app package; return it with the runtime generation it needs."""
    with zipfile.ZipFile(path) as package:
        manifest = json.loads(package.read("manifest.json"))
    if manifest["version"] != version:
        msg = f"{path.name} holds version {manifest['version']}, not {version}"
        raise SystemExit(msg)
    entry: dict[str, object] = {
        "url": f"{REPOSITORY}/releases/download/{tag}/{path.name}",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }
    return entry, int(manifest["runtime"])


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
    setups = {
        platform: f"{REPOSITORY}/releases/download/{tag}/{name.format(version=version)}"
        for name, platform in SETUPS.items()
        if (folder / name.format(version=version)).exists()
    }
    return {
        "version": version,
        "notes_url": f"{REPOSITORY}/releases/tag/{tag}",
        "runtime": runtimes.pop() if runtimes else 1,
        "packages": packages,
        "setups": setups,
    }


def sign(content: bytes, pem: str) -> bytes:
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        msg = "RELEASE_SIGNING_KEY is not an Ed25519 key"
        raise SystemExit(msg)
    return base64.b64encode(key.sign(content)) + b"\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--tag", help="the release's tag (default: v<version>)")
    args = parser.parse_args()
    pem = os.environ.get("RELEASE_SIGNING_KEY")
    if not pem:
        msg = "set RELEASE_SIGNING_KEY to the private key (PEM)"
        raise SystemExit(msg)
    tag = args.tag or f"v{args.version}"
    content = (json.dumps(manifest(args.version, args.folder, tag), indent=2) + "\n").encode()
    signature = sign(content, pem)
    # Checked as every installation will: the program's public key and reader.
    Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY)).verify(
        base64.b64decode(signature), content
    )
    release = read_release(json.loads(content))
    (args.folder / "release.json").write_bytes(content)
    (args.folder / "release.json.sig").write_bytes(signature)
    platforms = ", ".join(release.packages) or "none (server release)"
    print(f"release.json for {release.version} signed; app packages: {platforms}")


if __name__ == "__main__":
    main()
