"""Command line interface: ``rhinvoice serve | migrate | user create | demo``."""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import TYPE_CHECKING

from rhinvoice.api.container import build_container
from rhinvoice.api.settings import Settings
from rhinvoice.application.demo.handlers import DEMO_EMAIL
from rhinvoice.application.identity.handlers import CreateUser
from rhinvoice.domain.shared.errors import DomainError
from rhinvoice.infrastructure.db.migrate import (
    NewerDatabaseError,
    NotADemoDatabaseError,
    require_known_schema,
    reset_demo_database,
    upgrade,
)
from rhinvoice.infrastructure.scheduling import PeriodicJob

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from rhinvoice.api.container import Container


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        msg = "passwords do not match"
        raise SystemExit(msg)
    return password


def _user_create(args: argparse.Namespace, settings: Settings) -> int:
    container = build_container(settings)
    try:
        user = container.identity.create_user(
            CreateUser(email=args.email, display_name=args.name, password=_read_password(args)),
        )
    except DomainError as error:
        sys.stderr.write(f"error: {error.message}\n")
        return 1
    finally:
        container.engine.dispose()
    sys.stdout.write(f"created user {user.email}\n")
    return 0


FIRST_RECURRING_RUN = 60
"""Seconds after the start before recurring invoices are looked at."""


def _demo(args: argparse.Namespace, settings: Settings) -> int:
    container = build_container(settings)
    try:
        result = container.demo.seed(documents=not args.without_documents)
    except DomainError as error:
        sys.stderr.write(f"error: {error.message}\n")
        return 1
    finally:
        container.engine.dispose()
    sys.stdout.write(
        f"demo data: {result.customers} customers, {result.articles} articles, "
        f"{result.bank_accounts} bank accounts, {result.invoices} invoices, "
        f"{result.quotes} quotes, {result.imported} old invoices taken over\n"
    )
    return 0


def reset_demo(settings: Settings, container: Container) -> None:
    """Start the public demo afresh: empty database, demo login, company and data.

    The API answers 503 meanwhile, so that no visitor slips into the empty database.
    """
    container.demo_reset.set()
    try:
        reset_demo_database(settings.database_url, DEMO_EMAIL)
        container.demo.install(settings.demo_country)
        # Visitors come for the cockpit, not for the setup checklist.
        container.onboarding.dismiss()
    finally:
        container.demo_reset.clear()


def _known_schema(settings: Settings) -> bool:
    """Tell whether this version knows the database's schema; say why not otherwise."""
    try:
        require_known_schema(settings.database_url)
    except NewerDatabaseError as error:
        sys.stderr.write(f"error: {error}\n")
        return False
    return True


def _migrate(_args: argparse.Namespace, settings: Settings) -> int:
    if not _known_schema(settings):
        return 1
    upgrade(settings.database_url)
    sys.stdout.write("database is up to date\n")
    return 0


def _serve(args: argparse.Namespace, settings: Settings) -> int:
    return serve(settings, args.host, args.port, args.forwarded_allow_ips)


def serve(settings: Settings, host: str, port: int, forwarded_allow_ips: str = "127.0.0.1") -> int:
    """Run the web server until it is stopped (also used by the installation without Docker)."""
    import uvicorn  # noqa: PLC0415 - only needed for this command

    from rhinvoice.api.app import create_app  # noqa: PLC0415

    if not _known_schema(settings):
        return 1
    if settings.run_migrations:
        upgrade(settings.database_url)
    container = build_container(settings)
    jobs: list[PeriodicJob] = []
    if settings.demo:
        try:
            reset_demo(settings, container)
        except NotADemoDatabaseError as error:
            sys.stderr.write(f"error: {error}\n")
            return 1
        jobs.append(
            PeriodicJob(
                lambda: reset_demo(settings, container),
                interval=settings.demo_reset_interval,
                first_delay=settings.demo_reset_interval,
                name="demo reset",
            )
        )
    elif settings.recurring:
        # A demo writes no recurring invoices: they could send mail.
        jobs.append(
            PeriodicJob(
                container.recurring.run_due,
                interval=settings.recurring_interval,
                first_delay=FIRST_RECURRING_RUN,
                name="recurring invoices",
            )
        )
    for job in jobs:
        job.start()
    try:
        uvicorn.run(
            create_app(container),
            host=host,
            port=port,
            proxy_headers=True,
            forwarded_allow_ips=forwarded_allow_ips,
        )
    finally:
        for job in jobs:
            job.stop()
    return 0


def _recurring(_args: argparse.Namespace, settings: Settings) -> int:
    """Write the due recurring invoices now (the web server does it every few minutes)."""
    container = build_container(settings)
    try:
        runs = container.recurring.run_due()
        names = {view.plan.id: view.plan.name for view in container.recurring.plans()}
    finally:
        container.engine.dispose()
    for run in runs:
        problem = f" ({run.code}: {run.message})" if run.code else ""
        name = names.get(run.plan_id, str(run.plan_id))
        sys.stdout.write(f"{name} {run.period_start.isoformat()} {run.outcome.value}{problem}\n")
    sys.stdout.write(f"recurring invoices: {len(runs)} written\n")
    # Non-zero for cron and monitoring when an invoice needs attention.
    return 1 if any(run.code for run in runs) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rhinvoice")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the web server")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - runs inside a container
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--forwarded-allow-ips", default="127.0.0.1")
    serve.set_defaults(handler=_serve)

    recurring = commands.add_parser("recurring", help="write the due recurring invoices now")
    recurring.set_defaults(handler=_recurring)

    migrate = commands.add_parser("migrate", help="apply database migrations")
    migrate.set_defaults(handler=_migrate)

    user = commands.add_parser("user", help="manage users").add_subparsers(
        dest="user_command",
        required=True,
    )
    create = user.add_parser("create", help="create a user")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin instead of prompting",
    )
    create.set_defaults(handler=_user_create)

    demo = commands.add_parser(
        "demo", help="fill a new installation with demo customers, articles and documents"
    )
    demo.add_argument(
        "--without-documents",
        action="store_true",
        help="only customers, articles and bank accounts, no invoices or quotes",
    )
    demo.set_defaults(handler=_demo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace, Settings], int] = args.handler
    return handler(args, Settings())
