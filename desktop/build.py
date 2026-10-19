"""Assemble the program folder of the installation without Docker (ADR 0021).

    python desktop/build.py windows     (on Windows)
    python desktop/build.py macos       (on a Mac with Apple silicon)

writes the two parts of ADR 0022 into ``build/<target>``. Afterwards

    python desktop/build.py windows-beta
    python desktop/build.py macos-beta

derive Rhinvoice Beta from it (ADR 0030): the same runtime and app package under another
name, with its own identity and data folder, for release candidates. On Windows:

    install/                  what the setup installs (Inno Setup packs it)
      python/                 the runtime: a standalone CPython with rhinvoice_boot only
      postgresql/             the PostgreSQL distribution (with ICU)
      restic/                 restic for the backups (ADR 0023)
      runtime.json           {"generation": N}: what app packages may expect of it
                              (Rhinvoice Beta: {"generation": N, "edition": "beta"})
      app/                    the app package of this release (see below)
      Rhinvoice.ico
    rhinvoice-app-<version>-windows-x64.zip   the same app package, for updates
    install-beta/             the same as install/, as Rhinvoice Beta (windows-beta)

On macOS the same parts sit in ``Rhinvoice.app/Contents/Resources``; the bundle starts
``Contents/MacOS/Rhinvoice``, a script that runs a copy of the interpreter from
``Contents/MacOS`` (so that macOS shows Rhinvoice's name and icon) with PYTHONHOME set to
the bundled Python, plus a headless Chromium for the PDFs (macOS has no Edge).
``Rhinvoice Beta.app`` beside it is the copy that macos-beta renames and signs again.

An app package holds ``site-packages/`` (Rhinvoice and its locked dependencies),
``static/`` (the built web interface: build frontend/dist first) and ``manifest.json``.

Every download is pinned in sources.json and checked against its SHA-256. Needs uv.
Only the standard library: it runs before anything else is installed.
"""

# A build script reports its steps on the console; it is no package.
# ruff: noqa: T201, INP001

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import os
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
EDITIONS = {
    "stable": {"name": "Rhinvoice", "identifier": "ch.webberz.rhinvoice", "icon": "Rhinvoice"},
    # Rhinvoice's icon with a striped edge at the bottom, to tell the two apart.
    "beta": {
        "name": "Rhinvoice Beta",
        "identifier": "ch.webberz.rhinvoice.beta",
        "icon": "Rhinvoice-Beta",
    },
}
"""Rhinvoice, and Rhinvoice Beta for release candidates (ADR 0030): the name is that of the
program, of its macOS bundle and of its folders (rhinvoice_boot.NAMES). Never change an
identifier: macOS knows an app by it."""


def write_runtime(install: Path, edition: str) -> None:
    """Describe the runtime for the boot and the app packages; "stable" names no edition."""
    runtime: dict[str, object] = {"generation": RUNTIME_GENERATION}
    if edition != "stable":
        runtime["edition"] = edition
    (install / "runtime.json").write_text(json.dumps(runtime) + "\n", encoding="utf-8")


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


def run(*command: str | Path, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    # Flushed: the child writes to the same log, and its lines must come after this one.
    print("$", " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, env=env, check=True)  # noqa: S603 - build tools


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
    python = install / "python"
    unpack_single_folder(fetch(sources["python"]), python)
    if (python / "python.exe").exists():
        interpreter, site_packages = python / "python.exe", python / "Lib" / "site-packages"
    else:
        interpreter = python / "bin" / "python3"
        [site_packages] = python.glob("lib/python3.*/site-packages")
    shutil.copytree(
        BACKEND / "src" / "rhinvoice_boot",
        site_packages / "rhinvoice_boot",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    write_runtime(install, "stable")
    return interpreter


UNUSED_STDLIB = (
    "idlelib", "tkinter", "turtledemo", "turtle.py", "ensurepip", "venv", "pydoc_data",
    "lib2to3", "test", "config-3.*", "site-packages/pip", "site-packages/pip-*",
    "lib-dynload/_tkinter.*",
)  # fmt: skip
"""Parts of the standard library the program never uses: no GUI toolkit, no package
manager, no tests. check_imports tries the modules the program imports without them."""
UNUSED_RUNTIME = {
    "windows": (
        # Headers and import libraries for building extensions.
        "include", "libs",
        # Tcl/Tk for tkinter.
        "tcl", "DLLs/_tkinter.*", "DLLs/tcl*.dll", "DLLs/tk*.dll",
        # CPython's own test modules.
        "DLLs/_test*", "DLLs/_ctypes_test*", "DLLs/xxlimited*",
    ),
    "macos": (
        # Headers and files for building extensions; manual pages.
        "include", "share", "lib/pkgconfig", "bin/python3*-config",
        # Tcl/Tk for tkinter.
        "lib/tcl9*", "lib/tk9*", "lib/itcl*", "lib/thread*", "lib/libtcl*",
        # The command line tools that come with it.
        "bin/idle3*", "bin/pip*", "bin/pydoc3*",
        # The interpreter is linked statically; nothing loads the shared library.
        "lib/libpython*",
    ),
}  # fmt: skip
"""Per system, never mixed, and matched case-sensitively: on Windows "lib/thread*" would
otherwise remove Lib/threading.py."""


def trim_runtime(python: Path) -> None:
    """Remove what the bundled CPython brings but the program never uses.

    About 120 MB on Windows, most of it debug symbols; about 30 MB on macOS.
    """
    windows = (python / "python.exe").exists()
    [stdlib] = [python / "Lib"] if windows else list(python.glob("lib/python3.*"))
    runtime = UNUSED_RUNTIME["windows" if windows else "macos"]
    unused = [
        *(path for pattern in runtime for path in python.glob(pattern, case_sensitive=True)),
        *(path for pattern in UNUSED_STDLIB for path in stdlib.glob(pattern, case_sensitive=True)),
        # Debug symbols (Windows), and compiled files: Python writes those to the user's
        # cache on first use (rhinvoice_boot.use_bytecode_cache).
        *python.rglob("*.pdb", case_sensitive=True),
        *python.rglob("__pycache__", case_sensitive=True),
    ]
    for path in unused:
        print(f"trim {path.relative_to(python)}", flush=True)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


IMPORT_CHECK = """
import importlib, os, pkgutil, site, sys
failed = []


def tried(name):
    try:
        return importlib.import_module(name)
    except Exception as error:
        failed.append(f"{name}: {type(error).__name__}: {error}")
        return None


folder = sys.argv[1]
site.addsitedir(folder)
names = {module.name for module in pkgutil.iter_modules([folder])}
rhinvoice = tried("rhinvoice")
if rhinvoice is not None:
    names |= {m.name for m in pkgutil.walk_packages(rhinvoice.__path__, "rhinvoice.")}
names = {n for n in names if not n.endswith("__main__")} | set(sys.argv[2:])
for name in sorted(names):
    tried(name)
for line in failed:
    print(line)
    # Annotations can be read without the job's log (GitHub's API).
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title=Import check::{line}")
print(f"{len(failed)} modules failed" if failed else f"imported {len(names)} modules", flush=True)
raise SystemExit(1 if failed else 0)
"""
USED_MODULES = (
    # The boot, from the runtime itself.
    "rhinvoice_boot",
    # What uvicorn chooses when the server starts: the "auto" modules import the
    # implementations that are installed (httptools, websockets).
    "uvicorn.loops.auto", "uvicorn.loops.asyncio", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
)  # fmt: skip
"""Modules imported only at run time, beyond the top-level ones of the app package."""
USED_ON = {
    "windows": ("webview.platforms.winforms", "webview.platforms.edgechromium"),
    "macos": ("webview.platforms.cocoa", "uvicorn.loops.uvloop"),
}
"""The program window's backend and, where installed, uvloop."""


def check_imports(python: Path, package: Path, system: str) -> None:
    """Import every module of Rhinvoice, every library of the app package and USED_MODULES.

    With the bundled interpreter: a part of the standard library trimmed too much fails the
    build, not a user. Only what these modules import when imported is checked; a part a
    library loads later, in a function, is not.
    """
    run(
        python, "-c", IMPORT_CHECK, package / "site-packages", *USED_MODULES, *USED_ON[system],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )  # fmt: skip


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
    # The boot belongs to the runtime; a package must not bring its own. PyObjC's own tests
    # come with its wheel (macOS only).
    shutil.rmtree(site_packages / "rhinvoice_boot")
    shutil.rmtree(site_packages / "PyObjCTest", ignore_errors=True)
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


def install_restic(sources: dict[str, dict[str, str]], install: Path) -> None:
    """Unpack the restic that makes the backups (ADR 0023), named as the launcher expects."""
    archive = fetch(sources["restic"])
    folder = install / "restic"
    folder.mkdir()
    if archive.suffix == ".zip":
        # Windows: a zip with the single restic_<version>_windows_amd64.exe.
        with zipfile.ZipFile(archive) as zipped:
            [name] = zipped.namelist()
            (folder / "restic.exe").write_bytes(zipped.read(name))
        return
    # macOS: the program itself, compressed with bzip2.
    program = folder / "restic"
    program.write_bytes(bz2.decompress(archive.read_bytes()))
    program.chmod(0o755)


def install_static(package: Path) -> None:
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").exists():
        msg = "frontend/dist is missing: build the web interface first (pnpm run build)"
        raise SystemExit(msg)
    shutil.copytree(dist, package / "static")


def brand_windows_program(
    sources: dict[str, dict[str, str]], install: Path, edition: str = "stable"
) -> None:
    """Start as Rhinvoice.exe, so that the taskbar shows Rhinvoice's icon and name."""
    program = install / "python" / "Rhinvoice.exe"
    shutil.copy2(install / "python" / "pythonw.exe", program)
    name = EDITIONS[edition]["name"]
    run(
        fetch(sources["rcedit"]), program,
        "--set-icon", install / "Rhinvoice.ico",
        "--set-version-string", "FileDescription", name,
        "--set-version-string", "ProductName", name,
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
    install_restic(sources, install)
    brand_windows_program(sources, install)
    build_app_package(python, install / "app")
    trim_runtime(install / "python")
    check_imports(python, install / "app", "windows")
    zip_app_package(install / "app", out / f"rhinvoice-app-{version()}-windows-x64.zip")
    print(f"Rhinvoice {version()} (runtime {RUNTIME_GENERATION}) assembled in {out}")


def build_windows_beta(out: Path) -> None:
    """Copy the assembled program folder as Rhinvoice Beta (install-beta, ADR 0030).

    The setup gets its own AppId, folder and shortcuts from rhinvoice.iss (/DEdition=beta).
    """
    sources = json.loads((ROOT / "desktop" / "sources.json").read_text(encoding="utf-8"))["windows"]
    install, beta = out / "install", out / "install-beta"
    if not (install / "runtime.json").exists():
        msg = f"{install} is missing: assemble the program first (build.py windows)"
        raise SystemExit(msg)
    shutil.rmtree(beta, ignore_errors=True)
    shutil.copytree(install, beta)
    shutil.copy2(ROOT / "desktop" / "icons" / "Rhinvoice-Beta.ico", beta / "Rhinvoice.ico")
    write_runtime(beta, "beta")
    brand_windows_program(sources, beta, "beta")
    print(f"Rhinvoice Beta {version()} assembled in {beta}")


INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>{name}</string>
  <key>CFBundleDisplayName</key><string>{name}</string>
  <key>CFBundleIdentifier</key><string>{identifier}</string>
  <key>CFBundleExecutable</key><string>Rhinvoice</string>
  <key>CFBundleIconFile</key><string>Rhinvoice</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>{version}</string>
  <key>CFBundleVersion</key><string>{version}</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.business</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>Webberz, AGPL-3.0</string>
</dict>
</plist>
"""
MACOS_START = """#!/bin/sh
# __NAME__: start the boot with the bundled Python (ADR 0021, 0022). The interpreter
# lies in Contents/MacOS, so that macOS shows the app's name and icon. Caches and logs
# go to folders named after the edition, as the data folder does (ADR 0030).
contents="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONHOME="$contents/Resources/python"
# The bundle is signed: compiled files go to the user's cache, never into it. Set here,
# before Python imports anything; the boot passes it on (rhinvoice_boot.use_bytecode_cache).
export PYTHONPYCACHEPREFIX="$HOME/Library/Caches/__NAME__/pycache"
# Started from the Finder, the output would be lost: keep it where Console.app finds it.
if [ ! -t 1 ]; then
    mkdir -p "$HOME/Library/Logs/__NAME__"
    exec >>"$HOME/Library/Logs/__NAME__/rhinvoice.log" 2>&1
fi
# -P: the working folder is not searched for modules (rhinvoice_boot.START).
exec "$contents/MacOS/python3" -P -m rhinvoice_boot "$@"
"""


POSTGRES_PROGRAMS = {
    "postgres", "pg_ctl", "initdb", "psql", "createdb", "pg_dump", "pg_dumpall", "pg_restore",
    "pg_upgrade", "pg_isready", "pg_controldata", "pg_resetwal",
}  # fmt: skip
"""The server and the tools the runtime or a future upgrade use; Postgres.app has many more."""
POSTGRES_UNUSED_EXTENSIONS = ("postgis", "address_standardizer", "libpgrouting", "pgrouting")
"""PostGIS and pgRouting with their geodata libraries: three quarters of Postgres.app."""


def linked_libraries(binary: Path) -> list[Path]:
    """List the libraries a Mach-O file loads from beside itself (@loader_path)."""
    output = subprocess.run(  # noqa: S603 - a build tool
        ["/usr/bin/otool", "-L", str(binary)], capture_output=True, text=True, check=True
    ).stdout
    references = (line.strip().split(" ")[0] for line in output.splitlines()[1:])
    return [
        binary.parent / reference.removeprefix("@loader_path/")
        for reference in references
        if reference.startswith("@loader_path/")
    ]


def remove_unused_postgres_parts(postgresql: Path) -> None:
    for program in (postgresql / "bin").iterdir():
        if program.name not in POSTGRES_PROGRAMS:
            program.unlink()
    for folder in (
        postgresql / "lib" / "postgresql",
        postgresql / "share" / "postgresql" / "extension",
    ):
        for path in folder.iterdir():
            if path.name.startswith(POSTGRES_UNUSED_EXTENSIONS):
                path.unlink()
    for unused in ("doc", "man", "info", "gdal", "proj"):
        shutil.rmtree(postgresql / "share" / unused, ignore_errors=True)
    shutil.rmtree(postgresql / "lib" / "gdalplugins", ignore_errors=True)


def keep_needed_libraries(postgresql: Path) -> None:
    """Follow the libraries from the programs and modules, as the loader will; drop the rest."""
    pending = [
        *(postgresql / "bin").iterdir(),
        *(postgresql / "lib" / "postgresql").glob("*.dylib"),
    ]
    needed: set[str] = set()
    while pending:
        for library in linked_libraries(pending.pop()):
            real = library.resolve()
            if real.name not in needed:
                pending.append(real)
            needed |= {library.name, real.name}
    for path in (postgresql / "lib").iterdir():
        if not path.is_dir() and path.name not in needed:
            path.unlink()


def trim_postgres(postgresql: Path) -> None:
    """Keep the server, its tools and what they load, with only the arm64 code."""
    remove_unused_postgres_parts(postgresql)
    keep_needed_libraries(postgresql)
    for path in [*(postgresql / "bin").iterdir(), *(postgresql / "lib").rglob("*.dylib")]:
        if path.is_file() and not path.is_symlink() and is_universal(path):
            run("lipo", path, "-thin", "arm64", "-output", path)


def is_universal(binary: Path) -> bool:
    """Tell whether a Mach-O file holds code for more than one processor."""
    archs = subprocess.run(  # noqa: S603 - a build tool
        ["/usr/bin/lipo", "-archs", str(binary)], capture_output=True, text=True, check=False
    ).stdout.split()
    return len(archs) > 1


def install_postgres_from_app(sources: dict[str, dict[str, str]], install: Path) -> None:
    """Copy PostgreSQL out of the pinned Postgres.app disk image (relocatable, with ICU)."""
    with tempfile.TemporaryDirectory() as mount:
        run(
            "hdiutil",
            "attach",
            "-nobrowse",
            "-readonly",
            "-mountpoint",
            mount,
            fetch(sources["postgresql"]),
        )
        try:
            [version] = (Path(mount) / "Postgres.app" / "Contents" / "Versions").glob("1*")
            shutil.copytree(version, install / "postgresql", symlinks=True)
        finally:
            run("hdiutil", "detach", mount)
    shutil.rmtree(install / "postgresql" / "include", ignore_errors=True)
    trim_postgres(install / "postgresql")


def install_chromium(sources: dict[str, dict[str, str]], install: Path) -> None:
    """Unpack the headless Chromium that prints the PDFs, keeping its file modes."""
    with tempfile.TemporaryDirectory() as temporary:
        run("ditto", "-x", "-k", fetch(sources["chromium"]), temporary)
        [top] = list(Path(temporary).iterdir())
        shutil.move(top, install / "chromium")


def build_macos(out: Path) -> None:
    sources = json.loads((ROOT / "desktop" / "sources.json").read_text(encoding="utf-8"))
    sources = sources["macos-arm64"]
    bundle = out / "Rhinvoice.app"
    contents = bundle / "Contents"
    install = contents / "Resources"
    shutil.rmtree(out, ignore_errors=True)
    install.mkdir(parents=True)
    (contents / "MacOS").mkdir()
    python = install_runtime_python(sources, install)
    shutil.copy2(python.resolve(), contents / "MacOS" / "python3")
    brand_macos(bundle, "stable")
    install_postgres_from_app(sources, install)
    install_chromium(sources, install)
    install_restic(sources, install)
    build_app_package(python, install / "app")
    trim_runtime(install / "python")
    check_imports(python, install / "app", "macos")
    zip_app_package(install / "app", out / f"rhinvoice-app-{version()}-macos-arm64.zip")
    sign_ad_hoc(bundle)
    print(f"Rhinvoice {version()} (runtime {RUNTIME_GENERATION}) assembled in {bundle}")


def brand_macos(bundle: Path, edition: str) -> None:
    """Give the bundle the edition's name and identifier, start script and runtime.json."""
    contents = bundle / "Contents"
    names = EDITIONS[edition]
    plist = INFO_PLIST.format(version=version(), **names)
    (contents / "Info.plist").write_text(plist, encoding="utf-8")
    start = contents / "MacOS" / "Rhinvoice"
    start.write_text(MACOS_START.replace("__NAME__", names["name"]), encoding="utf-8")
    start.chmod(0o755)
    icon = ROOT / "desktop" / "icons" / f"{names['icon']}.icns"
    shutil.copy2(icon, contents / "Resources" / "Rhinvoice.icns")
    write_runtime(contents / "Resources", edition)


def build_macos_beta(out: Path) -> None:
    """Copy the assembled Rhinvoice.app as Rhinvoice Beta.app and sign it (ADR 0030)."""
    stable, beta = out / "Rhinvoice.app", out / "Rhinvoice Beta.app"
    if not (stable / "Contents" / "Info.plist").exists():
        msg = f"{stable} is missing: assemble the app first (build.py macos)"
        raise SystemExit(msg)
    shutil.rmtree(beta, ignore_errors=True)
    shutil.copytree(stable, beta, symlinks=True)
    brand_macos(beta, "beta")
    sign_ad_hoc(beta)
    print(f"Rhinvoice Beta {version()} assembled in {beta}")


def sign_ad_hoc(bundle: Path) -> None:
    """Sign without an Apple certificate, so that macOS offers "Open Anyway".

    Apple silicon runs no unsigned code, and a bundle whose parts were signed one by one
    (Python, PostgreSQL, Chromium) but not as a whole is reported as damaged.
    """
    run("codesign", "--force", "--deep", "--sign", "-", bundle)
    run("codesign", "--verify", "--deep", "--strict", "--verbose=2", bundle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    builds = {
        "windows": build_windows,
        "macos": build_macos,
        "windows-beta": build_windows_beta,
        "macos-beta": build_macos_beta,
    }
    parser.add_argument("target", choices=[*builds, "version"])
    parser.add_argument("--out", type=Path, help="default: build/<windows or macos>")
    args = parser.parse_args()
    if args.target == "version":
        print(version())
        return
    system = args.target.removesuffix("-beta")
    # The bundled interpreter installs the packages: it must run on this computer.
    needed = {"windows": "win32", "macos": "darwin"}[system]
    if sys.platform != needed:
        msg = f"the {system} program is assembled on {system}"
        raise SystemExit(msg)
    builds[args.target](args.out or ROOT / "build" / system)


if __name__ == "__main__":
    main()
