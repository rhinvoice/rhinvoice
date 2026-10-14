"""Check an installed Rhinvoice without Docker the way a user meets it (ADR 0021).

    python desktop/smoke_test.py <install folder>

Starts the installed program on an empty data folder (without window), creates the first
user and the company, fills in the demo data, prints an invoice as PDF, kills the program
and starts it again (the database left running must be taken over), and ends it the way
Windows asks a program to close. Only the standard library: it runs beside the
installation, not inside it.
"""

# A test script reports its steps on the console; it is no package.
# ruff: noqa: T201, INP001, S310

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

HEADERS = {"X-Rhinvoice-Client": "smoke-test", "Content-Type": "application/json"}
START_SECONDS = 180
NOT_RUNNING = 3
PDF_MIN_BYTES = 10_000


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


class Program:
    def __init__(self, install: Path, data: Path) -> None:
        self.install = install
        self.data = data
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> int:
        """Start the program; return its port once the web interface answers."""
        python = self.install / "python" / "python.exe"
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.data.mkdir(parents=True, exist_ok=True)
        output = (self.data.parent / "program.log").open("ab")
        self.process = subprocess.Popen(  # noqa: S603 - the installed program
            [python, "-m", "rhinvoice.desktop", "--no-browser", "--data-dir", self.data],
            creationflags=flags,
            stdout=output,
            stderr=subprocess.STDOUT,
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

    def close(self) -> int:
        """Ask the program to end, as Windows does when the user logs off."""
        self.running().send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT))
        return self.running().wait(timeout=60)

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
    subprocess.run(  # noqa: S603 - the installed program
        [
            install / "python" / "python.exe",
            "-c",
            "from rhinvoice.api.cli import main; raise SystemExit(main(['demo']))",
        ],
        env={**os.environ, "RHINVOICE_DATABASE_URL": program.database_url()},
        check=True,
    )
    step("an invoice printed as PDF by the browser of this computer")
    [invoice, *_] = api.json("GET", "/documents?type=invoice&status=overdue")["items"]
    status, pdf = api.call("GET", f"/documents/{invoice['id']}/pdf")
    if status != 200 or not pdf.startswith(b"%PDF-") or len(pdf) < PDF_MIN_BYTES:  # noqa: PLR2004
        msg = f"no PDF: status {status}, {len(pdf)} bytes, {pdf[:40]!r}"
        raise SystemExit(msg)
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
    step("closed: the database stops with the program")
    program.close()
    if program.database_running():
        msg = "the database still runs after the program was closed"
        raise SystemExit(msg)
    step("all good")


def report(error: BaseException, data: Path) -> None:
    """Show why it failed as a GitHub annotation, readable without the run's log."""
    lines = [f"{type(error).__name__}: {error}"]
    for log in (data.parent / "program.log", data / "rhinvoice.log", data / "postgresql.log"):
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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        data = Path(folder) / "Rhinvoice"
        try:
            check(args.install, data)
        except BaseException as error:
            report(error, data)
            raise


if __name__ == "__main__":
    main()
