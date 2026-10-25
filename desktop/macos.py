"""Sign, notarize and pack the macOS apps of the installation without Docker (ADR 0036).

    python desktop/macos.py dmg <app> <folder>     pack the app as <folder>/<Name>-<version>.dmg
    python desktop/macos.py sign <app or image>...  sign with the Developer ID
    python desktop/macos.py notarize <app or image>  have Apple notarize it, then staple it

``sign`` takes the certificate's name from APPLE_SIGNING_IDENTITY and the keychain that holds
it from APPLE_KEYCHAIN; an app is signed from the inside out, every program and library with
the hardened runtime; the interpreters and Chromium with the entitlements their part needs
(desktop/entitlements-*.plist), PostgreSQL and restic without any. ``notarize`` takes
APPLE_ID, APPLE_PASSWORD (an app-specific password) and APPLE_TEAM_ID.
Only the standard library and Apple's tools: it runs in the job that holds the certificate.
"""

# A build script reports its steps on the console; it is no package.
# ruff: noqa: T201, INP001

from __future__ import annotations

import argparse
import json
import os
import plistlib
import struct
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENTITLEMENTS = {
    "python": HERE / "entitlements-python.plist",
    "chromium": HERE / "entitlements-chromium.plist",
}
"""Which programs need what: by the folder of Contents/Resources they lie in, or the helper."""
THIN = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"}
"""Mach-O for one processor (64 and 32 bit), little-endian as on Apple's processors."""
FAT = {b"\xca\xfe\xba\xbe": ">I", b"\xca\xfe\xba\xbf": ">Q"}
"""Mach-O for several processors, and how the offset of its first part is stored."""
HEADER = 32
MACH_HEADER = 16
"""Bytes read: a fat header with its first part's offset; a Mach-O header up to its type."""
EXECUTE = 2
"""The file type of a program (MH_EXECUTE); libraries and Python modules are others."""
NESTED = {".app", ".framework", ".bundle", ".xpc"}
ATTEMPTS = 5
"""How often a call to Apple's services is tried before the job gives up."""
CHUNK = 100
"""Files per codesign call: one call per file would take long, all at once too long a line."""


def run(*command: str | Path) -> None:
    print("$", " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], check=True)  # noqa: S603 - Apple's tools


def file_type(path: Path) -> int | None:
    """Return the Mach-O file type of ``path`` (of its first part), None for other files."""
    with path.open("rb") as file:
        header = file.read(32)
        magic = header[:4]
        if magic in FAT and len(header) == HEADER:
            # fat_header (magic, count), then the first fat_arch: cputype, cpusubtype, offset
            [offset] = struct.unpack_from(FAT[magic], header, 16)
            file.seek(offset)
            header = file.read(16)
            magic = header[:4]
        if magic not in THIN or len(header) < MACH_HEADER:
            return None
        [kind] = struct.unpack_from("<I", header, 12)
        return int(kind)


def code_in(app: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """List the programs, the libraries and the nested bundles inside ``app``."""
    programs: list[Path] = []
    libraries: list[Path] = []
    nested: list[Path] = []
    for path in sorted(app.rglob("*")):
        if path.is_symlink():
            continue
        if path.is_dir():
            if path.suffix in NESTED:
                nested.append(path)
        elif (kind := file_type(path)) is not None:
            (programs if kind == EXECUTE else libraries).append(path)
    return programs, libraries, nested


def role(app: Path, program: Path) -> str | None:
    """Name the entitlements ``program`` needs: an interpreter, Chromium, or none."""
    relative = program.relative_to(app / "Contents")
    if relative.parts[0] == "MacOS":
        return "python"
    if relative.parts[:2] in {("Resources", "python"), ("Resources", "chromium")}:
        return relative.parts[1]
    return None


def codesign(paths: list[Path], *, entitlements: Path | None = None, hardened: bool = True) -> None:
    command: list[str | Path] = ["/usr/bin/codesign", "--force", "--timestamp"]
    command += ["--sign", os.environ["APPLE_SIGNING_IDENTITY"]]
    if keychain := os.environ.get("APPLE_KEYCHAIN"):
        command += ["--keychain", keychain]
    if hardened:
        command += ["--options", "runtime"]
    if entitlements is not None:
        command += ["--entitlements", entitlements]
    for start in range(0, len(paths), CHUNK):
        chunk = paths[start : start + CHUNK]
        print(f"signing {len(chunk)} files, from {chunk[0]}", flush=True)
        subprocess.run([*map(str, command), *map(str, chunk)], check=True)  # noqa: S603


def sign_app(app: Path) -> None:
    """Sign every program and library, then the nested bundles, the deepest first, then ``app``."""
    programs, libraries, nested = code_in(app)
    print(f"{app.name}: {len(programs)} programs, {len(libraries)} libraries", flush=True)
    codesign(libraries)
    for name in [None, *ENTITLEMENTS]:
        group = [program for program in programs if role(app, program) == name]
        if group:
            codesign(group, entitlements=ENTITLEMENTS.get(name) if name else None)
    for bundle in sorted(nested, key=lambda path: len(path.parts), reverse=True):
        codesign([bundle])
    # The bundle's own executable is the start script: it needs no entitlements.
    codesign([app])
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", app)
    [python] = (app / "Contents" / "MacOS").glob("* Helper")
    run("/usr/bin/codesign", "--display", "--entitlements", "-", python)


def sign(paths: list[Path]) -> None:
    for path in paths:
        if path.suffix == ".dmg":
            # A disk image carries no runtime; its signature names who made it.
            codesign([path], hardened=False)
            run("/usr/bin/codesign", "--verify", "--verbose=2", path)
        else:
            sign_app(path)


def notarize(path: Path) -> None:
    """Send ``path`` to Apple's notary service, wait for it, then staple the ticket to it."""
    credentials = [
        "--apple-id", os.environ["APPLE_ID"],
        "--password", os.environ["APPLE_PASSWORD"],
        "--team-id", os.environ["APPLE_TEAM_ID"],
    ]  # fmt: skip
    with tempfile.TemporaryDirectory() as temporary:
        upload = path
        if path.suffix == ".app":
            # The service takes an app as a zip archive; ditto keeps what the signature covers.
            upload = Path(temporary) / f"{path.stem}.zip"
            run("/usr/bin/ditto", "-c", "-k", "--keepParent", path, upload)
        print(f"notarizing {path.name}", flush=True)
        submitted = subprocess.run(  # noqa: S603 - Apple's tool; the password is not printed
            ["/usr/bin/xcrun", "notarytool", "submit", str(upload), *credentials, "--wait",
             "--timeout", "45m", "--output-format", "json"],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
    print(submitted.stdout + submitted.stderr, flush=True)
    try:
        result = json.loads(submitted.stdout)
    except ValueError:
        result = {}
    if result.get("status") != "Accepted":
        if submission := result.get("id"):
            # Apple's report names every file it refused and why.
            subprocess.run(  # noqa: S603 - Apple's tool
                ["/usr/bin/xcrun", "notarytool", "log", submission, *credentials], check=False
            )
        msg = f"Apple did not notarize {path.name}: {result.get('status', 'no answer')}"
        raise SystemExit(msg)
    staple(path)


def staple(path: Path) -> None:
    """Attach the ticket to ``path``; Apple's ticket service drops a connection now and then."""
    for attempt in range(1, ATTEMPTS + 1):
        stapled = subprocess.run(  # noqa: S603 - Apple's tool
            ["/usr/bin/xcrun", "stapler", "staple", str(path)], check=False
        )
        if stapled.returncode == 0:
            break
        if attempt == ATTEMPTS:
            msg = f"the ticket could not be stapled to {path.name}"
            raise SystemExit(msg)
        print(f"stapler failed (attempt {attempt}), trying again", flush=True)
        time.sleep(30)
    run("/usr/bin/xcrun", "stapler", "validate", path)


def pack(app: Path, folder: Path) -> Path:
    """Pack ``app`` with a link to /Applications into a disk image named after it."""
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    name, version = info["CFBundleName"], info["CFBundleShortVersionString"]
    image = folder / f"{name.replace(' ', '-')}-{version}.dmg"
    with tempfile.TemporaryDirectory() as staging:
        # ditto keeps the extended attributes, which hold the start script's signature.
        run("/usr/bin/ditto", app, Path(staging) / app.name)
        (Path(staging) / "Applications").symlink_to("/Applications")
        # ULMO (LZMA) packs far tighter than the usual UDZO (zlib); macOS opens it from
        # 10.15 on, below the app's minimum of 12.
        # hdiutil on the hosted runners fails now and then with "Resource busy" (a scan of
        # the fresh files still holds them): try again a few times before giving up.
        for attempt in range(1, ATTEMPTS + 1):
            created = subprocess.run(  # noqa: S603 - Apple's tool
                ["/usr/bin/hdiutil", "create", "-volname", f"{name} {version}",
                 "-srcfolder", staging, "-format", "ULMO", "-ov", str(image)],
                check=False,
            )  # fmt: skip
            if created.returncode == 0:
                break
            if attempt == ATTEMPTS:
                msg = f"hdiutil could not pack {app.name}"
                raise SystemExit(msg)
            print(f"hdiutil failed (attempt {attempt}), trying again", flush=True)
            time.sleep(10)
    run("/usr/bin/hdiutil", "verify", image)
    print(f"{image}: {image.stat().st_size // 2**20} MB", flush=True)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    dmg = commands.add_parser("dmg")
    dmg.add_argument("app", type=Path)
    dmg.add_argument("folder", type=Path)
    commands.add_parser("sign").add_argument("paths", type=Path, nargs="+")
    commands.add_parser("notarize").add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "dmg":
        pack(args.app, args.folder)
    elif args.command == "sign":
        sign(args.paths)
    else:
        notarize(args.path)


if __name__ == "__main__":
    main()
