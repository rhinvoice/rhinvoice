"""Check an installed Rhinvoice without Docker the way a user meets it (ADR 0021).

    python desktop/smoke_test.py <install folder>

Starts the installed program on the user's empty data folder (without window), creates the first
user and the company, fills in the demo data, prints an invoice as PDF, sets up a backup
folder and waits for the first backup (ADR 0023), kills the program
and starts it again (the database left running must be taken over), installs an update and
a broken update (taken back, ADR 0022), ends it the way Windows asks a program to close, and
restores the backup with ``--restore latest``. For Rhinvoice Beta (ADR 0030) it checks
the same on Rhinvoice Beta's own data folder, and that the program uses no other.
Only the standard library: it runs beside the installation, not inside it.
"""

# A test script reports its steps on the console; it is no package.
# ruff: noqa: T201, INP001, S310

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HEADERS = {"X-Rhinvoice-Client": "smoke-test", "Content-Type": "application/json"}
START_SECONDS = 180
NOT_RUNNING = 3
PDF_MIN_BYTES = 10_000
BACKUP_SECONDS = 180
"""The worker looks every 30 seconds; pg_dump and restic take a few seconds."""


class Api:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}/api"
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def call(self, method: str, path: str, body: object = None) -> tuple[int, bytes]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data, HEADERS, method=method)
        with self.opener.open(request, timeout=120) as response:
            return response.status, response.read()

    def json(self, method: str, path: str, body: object = None) -> Any:  # noqa: ANN401 - JSON
        return json.loads(self.call(method, path, body)[1])


def smoke_log(data: Path) -> Path:
    """Name the log of the program's output, beside its data folder (one per edition)."""
    return data.parent / f"{data.name.lower().replace(' ', '-')}-smoke-test.log"


class Program:
    def __init__(self, install: Path, data: Path) -> None:
        self.install = install
        self.data = data
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> int:
        """Start the program; return its port once the web interface answers."""
        python = self.install / "python" / "python.exe"
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        output = smoke_log(self.data).open("ab")
        self.process = subprocess.Popen(  # noqa: S603 - the installed program
            [python, "-P", "-m", "rhinvoice_boot", "--no-browser"],
            creationflags=flags,
            stdout=output,
            stderr=subprocess.STDOUT,
            # Every line in the log right away, also the last ones before a failure.
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        deadline = time.monotonic() + START_SECONDS
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                msg = f"the program ended with {self.process.returncode}"
                raise SystemExit(msg)
            port = self.port()
            if port and answers(port):
                return port
            time.sleep(1)
        msg = "the program did not answer in time"
        raise SystemExit(msg)

    def port(self) -> int | None:
        config = self.data / "rhinvoice.json"
        return int(json.loads(config.read_text())["port"]) if config.exists() else None

    def running(self) -> subprocess.Popen[bytes]:
        if self.process is None:
            msg = "the program was not started"
            raise SystemExit(msg)
        return self.process

    def kill(self) -> None:
        self.running().kill()
        self.running().wait()

    def close(self) -> None:
        """Ask the program to end, as Windows does when the user logs off."""
        self.running().send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT))
        self.running().wait(timeout=60)
        # After an update the program may run as a child of the boot: give it time to end.
        deadline = time.monotonic() + 60
        while self.database_running() and time.monotonic() < deadline:
            time.sleep(1)

    def state(self) -> dict[str, Any]:
        state: dict[str, Any] = json.loads((self.data / "app" / "state.json").read_text())
        return state

    def confirmed(self, version: str) -> dict[str, Any]:
        """Wait until ``version`` confirmed itself (just after its interface first answered)."""
        deadline = time.monotonic() + 30
        while self.state().get("active") != version and time.monotonic() < deadline:
            time.sleep(0.5)
        return self.state()

    def put_update(self, version: str) -> Path:
        """Put a copy of the installed app package into the data folder as ``version``."""
        package = self.data / "app" / "versions" / version
        shutil.copytree(self.install / "app", package)
        manifest = json.loads((package / "manifest.json").read_text())
        # A candidate's package carries its number; the copy stands for a final release.
        manifest.pop("candidate", None)
        (package / "manifest.json").write_text(json.dumps({**manifest, "version": version}))
        return package

    def database_url(self) -> str:
        password = json.loads((self.data / "rhinvoice.json").read_text())["database_password"]
        port = (self.data / "database" / "postmaster.pid").read_text().splitlines()[3]
        return f"postgresql+psycopg://rhinvoice:{password}@127.0.0.1:{port}/rhinvoice"

    def database_running(self) -> bool:
        pg_ctl = self.install / "postgresql" / "bin" / "pg_ctl.exe"
        status = subprocess.run(  # noqa: S603 - the installed tool
            [pg_ctl, "status", f"--pgdata={self.data / 'database'}"], check=False
        )
        return status.returncode != NOT_RUNNING


def answers(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            return bool(response.status == 200)  # noqa: PLR2004 - HTTP OK
    except OSError:
        return False


def step(text: str) -> None:
    print(f"--- {text}", flush=True)


def check(install: Path, data: Path) -> None:
    program = Program(install, data)
    step("first start on an empty data folder")
    first_port = program.start()
    api = Api(first_port)
    step("first user and company")
    api.call(
        "POST",
        "/auth/setup",
        {
            "display_name": "Anna Muster",
            "email": "anna@example.com",
            "password": "smoke-test-password",
        },
    )
    api.call(
        "PUT",
        "/company",
        {
            "name": "Muster GmbH",
            "default_currency": "CHF",
            "vat_number": "CHE-123.456.788",
            "address": {
                "street": "Bahnhofstrasse",
                "house_number": "1",
                "postal_code": "8001",
                "city": "Zürich",
                "country": "CH",
            },
        },
    )
    step("demo data")
    site_packages = install / "app" / "site-packages"
    demo = (
        f"import site; site.addsitedir(r'{site_packages}'); "
        "from rhinvoice.api.cli import main; raise SystemExit(main(['demo']))"
    )
    subprocess.run(  # noqa: S603 - the installed program
        [install / "python" / "python.exe", "-c", demo],
        env={**os.environ, "RHINVOICE_DATABASE_URL": program.database_url()},
        check=True,
    )
    step("the browser of this computer prints a page")
    print_directly(install)
    step("an invoice printed as PDF by the browser of this computer")
    [invoice, *_] = api.json("GET", "/documents?type=invoice&status=overdue")["items"]
    try:
        status, pdf = api.call("GET", f"/documents/{invoice['id']}/pdf")
    except urllib.error.HTTPError as error:
        msg = f"no PDF: {error} {error.read()[:500]!r}"
        raise SystemExit(msg) from error
    if status != 200 or not pdf.startswith(b"%PDF-") or len(pdf) < PDF_MIN_BYTES:  # noqa: PLR2004
        msg = f"no PDF: status {status}, {len(pdf)} bytes, {pdf[:40]!r}"
        raise SystemExit(msg)
    check_backup(program, api)
    step("killed, then started again: the database left running is taken over")
    program.kill()
    if not program.database_running():
        msg = "the database should still run after the program was killed"
        raise SystemExit(msg)
    port = program.start()
    if port != first_port:
        msg = f"the port changed from {first_port} to {port}"
        raise SystemExit(msg)
    if api.json("GET", "/documents?type=invoice")["total"] < 1:
        msg = "the invoices are gone after the restart"
        raise SystemExit(msg)
    check_updates(program, api)
    step("closed: the database stops with the program")
    program.close()
    if program.database_running():
        msg = "the database still runs after the program was closed"
        raise SystemExit(msg)
    check_restore(program, api)
    step("all good")


def check_restore(program: Program, api: Api) -> None:
    """Restore the backup as the docs describe it, then start again on the restored data."""
    step("the data is replaced with the latest backup (--restore latest)")
    restored = subprocess.run(  # noqa: S603 - the installed program
        [
            program.install / "python" / "python.exe",
            "-P",
            "-m",
            "rhinvoice_boot",
            "--restore",
            "latest",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    print(restored.stdout + restored.stderr)
    if restored.returncode != 0:
        msg = f"the restore failed: {restored.stderr[-1500:]}"
        raise SystemExit(msg)
    program.start()
    if api.json("GET", "/documents?type=invoice")["total"] < 1:
        msg = "the invoices are gone after the restore"
        raise SystemExit(msg)
    program.close()


PRINT_A_PAGE = """
import sys
from pathlib import Path
from rhinvoice.desktop.browser import find_chromium
from rhinvoice.infrastructure.rendering.chromium import LocalChromiumPrinter
import os, platform
browser = find_chromium(platform.system(), dict(os.environ), Path(sys.argv[1]))
print("browser:", browser)
printer = LocalChromiumPrinter(browser)
pdf = printer.print_pdf("<!doctype html><title>Test</title><p>Rhinvoice</p>")
printer.close()
print("PDF bytes:", len(pdf))
"""


def print_directly(install: Path) -> None:
    """Print one page with the installed program's browser, outside the web server."""
    site_packages = install / "app" / "site-packages"
    code = f"import site; site.addsitedir(r'{site_packages}')\n" + PRINT_A_PAGE
    result = subprocess.run(  # noqa: S603 - the installed program
        [install / "python" / "python.exe", "-c", code, install],
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout + result.stderr)
    if result.returncode != 0:
        msg = f"the browser could not print: {result.stderr[-1500:]}"
        raise SystemExit(msg)


def check_backup(program: Program, api: Api) -> None:
    """Set up a backup folder as on the settings page; the first backup must succeed (ADR 0023)."""
    step("a backup folder is set up; the first backup runs with the bundled restic")
    folder = program.data.parent / f"{program.data.name.replace(' ', '-')}-Backup"
    key = api.json("PUT", "/backup/setup", {"folder": str(folder)})["key"]
    if api.json("GET", "/backup/key")["key"] != key:
        msg = "the recovery key shown later is not the one shown at the setup"
        raise SystemExit(msg)
    if not api.json("POST", "/backup/key/confirmed")["key_confirmed"]:
        msg = "the recovery key was not confirmed"
        raise SystemExit(msg)
    deadline = time.monotonic() + BACKUP_SECONDS
    runs: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        runs = api.json("GET", "/backup")["runs"]
        if runs and runs[0]["status"] in {"succeeded", "failed"}:
            break
        time.sleep(5)
    if not runs or runs[0]["status"] != "succeeded":
        msg = f"the first backup did not succeed: {runs[:1]}"
        raise SystemExit(msg)
    # The key opens the backups: a restore would work.
    listed = subprocess.run(  # noqa: S603 - the installed tool
        [program.install / "restic" / "restic.exe", "snapshots", "--json", "--tag", "rhinvoice"],
        env={**os.environ, "RESTIC_REPOSITORY": str(folder), "RESTIC_PASSWORD": key},
        capture_output=True,
        text=True,
        check=True,
    )
    [snapshot] = json.loads(listed.stdout)
    if snapshot["id"] != runs[0]["snapshot_id"] and snapshot["short_id"] != runs[0]["snapshot_id"]:
        msg = f"the repository holds {snapshot['id']}, the run reported {runs[0]['snapshot_id']}"
        raise SystemExit(msg)


def check_updates(program: Program, api: Api) -> None:
    step("an update: the newer app package starts after a copy of the database")
    program.close()
    program.put_update("99.0.0")
    program.start()
    if (state := program.confirmed("99.0.0")).get("active") != "99.0.0":
        msg = f"the update did not become active: {state}"
        raise SystemExit(msg)
    if not (program.data / "backups" / "database-before-99.0.0" / "PG_VERSION").exists():
        msg = "no copy of the database was taken before the update"
        raise SystemExit(msg)
    if api.json("GET", "/documents?type=invoice")["total"] < 1:
        msg = "the invoices are gone after the update"
        raise SystemExit(msg)
    step("a broken update is taken back, the previous version starts")
    program.close()
    broken = program.put_update("99.0.1")
    shutil.rmtree(broken / "site-packages" / "rhinvoice")
    program.start()
    state = program.state()
    if state.get("active") != "99.0.0" or "99.0.1" not in state.get("failed", []):
        msg = f"the broken update was not taken back: {state}"
        raise SystemExit(msg)
    if api.json("GET", "/documents?type=invoice")["total"] < 1:
        msg = "the invoices are gone after taking the update back"
        raise SystemExit(msg)


def report(error: BaseException, data: Path) -> None:
    """Show why it failed as a GitHub annotation, readable without the run's log."""
    lines = [f"{type(error).__name__}: {error}"]
    logs = (
        smoke_log(data),
        data / "rhinvoice.log",
        data / "postgresql.log",
    )
    for log in logs:
        if log.exists():
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
            lines += [f"--- {log.name}", *tail]
    text = "\n".join(lines)
    print(text)
    print("::error title=Smoke test::" + text.replace("%", "%25").replace("\n", "%0A"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("install", type=Path)
    args = parser.parse_args()
    # The folder the program uses for this user, as on a real computer (a fresh one in CI).
    data = Path(os.environ["LOCALAPPDATA"]) / edition_name(args.install)
    if data.exists():
        msg = f"{data} exists: the smoke test needs a computer without {data.name} data"
        raise SystemExit(msg)
    others = {path: path.stat().st_mtime_ns for path in data.parent.glob("Rhinvoice*/*.json")}
    try:
        check(args.install, data)
        left_alone(others, data.name)
    except BaseException as error:
        report(error, data)
        raise


def left_alone(others: dict[Path, int], name: str) -> None:
    """Check that the files of other installations (Rhinvoice beside Rhinvoice Beta) stayed."""
    step("the data folders of other installations are left alone")
    touched = [p for p, t in others.items() if not p.exists() or p.stat().st_mtime_ns != t]
    if touched:
        msg = f"{name} changed the files of another installation: {touched}"
        raise SystemExit(msg)


def edition_name(install: Path) -> str:
    """Name the installed edition as its data folder is named (rhinvoice_boot.NAMES)."""
    runtime = json.loads((install / "runtime.json").read_text(encoding="utf-8"))
    return "Rhinvoice Beta" if runtime.get("edition") == "beta" else "Rhinvoice"


if __name__ == "__main__":
    main()
