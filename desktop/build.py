"""Assemble the program folder of the installation without Docker (ADR 0021).

    python desktop/build.py windows

writes ``build/windows/app`` with the layout that ``rhinvoice.desktop.launcher`` expects:

    python/      a standalone CPython with Rhinvoice and its locked dependencies
    postgresql/  the PostgreSQL distribution (with ICU)
    static/      the built web interface (frontend/dist, build it first)
    Rhinvoice.ico

Every download is pinned in sources.json and checked against its SHA-256. Needs uv.
Only the standard library: it runs before anything else is installed.
"""

# A build script reports its steps on the console; it is no package.
# ruff: noqa: T201, INP001

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DOWNLOADS = ROOT / "build" / "downloads"
# Not needed to run the server; about a third of the PostgreSQL download.
POSTGRES_UNUSED = ("include", "doc", "symbols", "pgAdmin 4", "StackBuilder")


def version() -> str:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    return str(project["project"]["version"])


def fetch(source: dict[str, str]) -> Path:
    """Download once into build/downloads and refuse anything but the pinned file."""
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    target = DOWNLOADS / source["url"].rsplit("/", 1)[1]
    if not target.exists():
        print(f"download {source['url']}")
        with urllib.request.urlopen(source["url"]) as response, target.open("wb") as file:  # noqa: S310 - pinned https URLs
            shutil.copyfileobj(response, file)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != source["sha256"]:
        target.unlink()
        msg = f"{target.name}: SHA-256 {digest} is not the pinned {source['sha256']}"
        raise SystemExit(msg)
    return target


def run(*command: str | Path, cwd: Path = ROOT) -> None:
    print("$", " ".join(str(part) for part in command))
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)  # noqa: S603 - build tools


def unpack_single_folder(archive: Path, target: Path) -> None:
    """Unpack an archive whose content sits in one top folder, as ``target``."""
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as zipped:
                # zipfile drops absolute paths and ".." itself; the archive is pinned anyway.
                zipped.extractall(folder)  # noqa: S202
        else:
            with tarfile.open(archive) as tarred:
                tarred.extractall(folder, filter="data")
        [top] = list(folder.iterdir())
        shutil.move(top, target)


def install_python(sources: dict[str, dict[str, str]], app: Path, python: Path) -> None:
    unpack_single_folder(fetch(sources["python"]), app / "python")
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        requirements = folder / "requirements.txt"
        # Exactly the versions of uv.lock, with hashes; the window needs the "desktop" extra.
        run(
            "uv", "export", "--frozen", "--no-dev", "--extra", "desktop", "--no-emit-project",
            "--format", "requirements-txt", "--output-file", requirements, cwd=BACKEND,
        )  # fmt: skip
        run("uv", "build", "--wheel", "--out-dir", folder, cwd=BACKEND)
        [wheel] = folder.glob("rhinvoice-*.whl")
        uv_pip = ("uv", "pip", "install", "--python", python, "--link-mode", "copy")
        run(*uv_pip, "--require-hashes", "--requirement", requirements)
        run(*uv_pip, "--no-deps", wheel)


def install_postgres(sources: dict[str, dict[str, str]], app: Path) -> None:
    unpack_single_folder(fetch(sources["postgresql"]), app / "postgresql")
    for unused in POSTGRES_UNUSED:
        shutil.rmtree(app / "postgresql" / unused, ignore_errors=True)


def install_static(app: Path) -> None:
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").exists():
        msg = "frontend/dist is missing: build the web interface first (pnpm run build)"
        raise SystemExit(msg)
    shutil.copytree(dist, app / "static")


def brand_windows_program(sources: dict[str, dict[str, str]], app: Path) -> None:
    """Start as Rhinvoice.exe, so that the taskbar shows Rhinvoice's icon and name."""
    program = app / "python" / "Rhinvoice.exe"
    shutil.copy2(app / "python" / "pythonw.exe", program)
    run(
        fetch(sources["rcedit"]), program,
        "--set-icon", app / "Rhinvoice.ico",
        "--set-version-string", "FileDescription", "Rhinvoice",
        "--set-version-string", "ProductName", "Rhinvoice",
        "--set-version-string", "CompanyName", "Webberz",
        "--set-file-version", version(),
        "--set-product-version", version(),
    )  # fmt: skip


def build_windows(out: Path) -> None:
    sources = json.loads((ROOT / "desktop" / "sources.json").read_text(encoding="utf-8"))["windows"]
    app = out / "app"
    shutil.rmtree(out, ignore_errors=True)
    app.mkdir(parents=True)
    shutil.copy2(ROOT / "desktop" / "icons" / "Rhinvoice.ico", app / "Rhinvoice.ico")
    install_python(sources, app, app / "python" / "python.exe")
    install_postgres(sources, app)
    install_static(app)
    brand_windows_program(sources, app)
    print(f"Rhinvoice {version()} assembled in {app}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", choices=["windows", "version"])
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "windows")
    args = parser.parse_args()
    if args.target == "version":
        print(version())
        return
    if sys.platform != "win32":
        msg = "the Windows program folder is assembled on Windows (its Python runs there)"
        raise SystemExit(msg)
    build_windows(args.out)


if __name__ == "__main__":
    main()
