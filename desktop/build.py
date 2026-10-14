"""Assemble the program folder of the installation without Docker (ADR 0021).

    python desktop/build.py windows

writes the two parts of ADR 0022 into ``build/windows``:

    install/                  what the setup installs (Inno Setup packs it)
      python/                 the runtime: a standalone CPython with rhinvoice_boot only
      postgresql/             the PostgreSQL distribution (with ICU)
      runtime.json            {"generation": N}: what app packages may expect of it
      app/                    the app package of this release (see below)
      Rhinvoice.ico
    rhinvoice-app-<version>-windows-x64.zip   the same app package, for updates

An app package holds ``site-packages/`` (Rhinvoice and its locked dependencies),
``static/`` (the built web interface: build frontend/dist first) and ``manifest.json``.

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
RUNTIME_GENERATION = 1
"""Raise it when the runtime changes in a way app packages depend on (new Python or
PostgreSQL major version): packages built afterwards then need the new setup."""
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


def install_runtime_python(sources: dict[str, dict[str, str]], install: Path) -> Path:
    """Unpack CPython and put the boot into its site-packages; return its interpreter."""
    unpack_single_folder(fetch(sources["python"]), install / "python")
    shutil.copytree(
        BACKEND / "src" / "rhinvoice_boot",
        install / "python" / "Lib" / "site-packages" / "rhinvoice_boot",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (install / "runtime.json").write_text(
        json.dumps({"generation": RUNTIME_GENERATION}) + "\n", encoding="utf-8"
    )
    return install / "python" / "python.exe"


def build_app_package(python: Path, package: Path) -> None:
    """Install Rhinvoice with its locked dependencies for ``python`` into ``package``."""
    site_packages = package / "site-packages"
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
        uv_pip = ("uv", "pip", "install", "--python", python, "--target", site_packages)
        run(*uv_pip, "--require-hashes", "--requirement", requirements)
        run(*uv_pip, "--no-deps", wheel)
    # The boot belongs to the runtime; a package must not bring its own.
    shutil.rmtree(site_packages / "rhinvoice_boot")
    install_static(package)
    manifest = {"version": version(), "runtime": RUNTIME_GENERATION}
    (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def zip_app_package(package: Path, target: Path) -> None:
    """Pack the app package for updates; its files sit at the top of the archive."""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(package.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(package).as_posix())


def install_postgres(sources: dict[str, dict[str, str]], install: Path) -> None:
    unpack_single_folder(fetch(sources["postgresql"]), install / "postgresql")
    for unused in POSTGRES_UNUSED:
        shutil.rmtree(install / "postgresql" / unused, ignore_errors=True)


def install_static(package: Path) -> None:
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").exists():
        msg = "frontend/dist is missing: build the web interface first (pnpm run build)"
        raise SystemExit(msg)
    shutil.copytree(dist, package / "static")


def brand_windows_program(sources: dict[str, dict[str, str]], install: Path) -> None:
    """Start as Rhinvoice.exe, so that the taskbar shows Rhinvoice's icon and name."""
    program = install / "python" / "Rhinvoice.exe"
    shutil.copy2(install / "python" / "pythonw.exe", program)
    run(
        fetch(sources["rcedit"]), program,
        "--set-icon", install / "Rhinvoice.ico",
        "--set-version-string", "FileDescription", "Rhinvoice",
        "--set-version-string", "ProductName", "Rhinvoice",
        "--set-version-string", "CompanyName", "Webberz",
        "--set-file-version", version(),
        "--set-product-version", version(),
    )  # fmt: skip


def build_windows(out: Path) -> None:
    sources = json.loads((ROOT / "desktop" / "sources.json").read_text(encoding="utf-8"))["windows"]
    install = out / "install"
    shutil.rmtree(out, ignore_errors=True)
    install.mkdir(parents=True)
    shutil.copy2(ROOT / "desktop" / "icons" / "Rhinvoice.ico", install / "Rhinvoice.ico")
    python = install_runtime_python(sources, install)
    install_postgres(sources, install)
    brand_windows_program(sources, install)
    build_app_package(python, install / "app")
    zip_app_package(install / "app", out / f"rhinvoice-app-{version()}-windows-x64.zip")
    print(f"Rhinvoice {version()} (runtime {RUNTIME_GENERATION}) assembled in {out}")


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
