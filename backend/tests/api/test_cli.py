import io
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import uvicorn
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from sqlalchemy import Engine, insert, text

from rhinvoice.api import cli
from rhinvoice.api.container import Container, OwnServices, build_container
from rhinvoice.api.settings import Settings
from rhinvoice.application.backup.ports import BackupTarget, Snapshot
from rhinvoice.application.backup.worker import BackupWorker
from rhinvoice.application.document.handlers import LineInput
from rhinvoice.application.identity.handlers import Login
from rhinvoice.domain.document.lines import LineKind, PriceMode
from rhinvoice.domain.recurring.plan import Interval, InvoiceTemplate, PlanAction, RecurringPlan
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency
from rhinvoice.infrastructure.db.migrate import NotADemoDatabaseError, alembic_config
from rhinvoice.infrastructure.db.tables import backup_runs
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from rhinvoice.infrastructure.scheduling import PeriodicJob
from tests.unit.domain import factories

PASSWORD = "correct horse battery"


HEAD = str(ScriptDirectory.from_config(alembic_config("postgresql://")).get_current_head())


def scripted_getpass(*answers: str) -> Callable[[str], str]:
    remaining = iter(answers)

    def getpass(_prompt: str) -> str:
        return next(remaining)

    return getpass


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, database_url: str, engine: Engine) -> Engine:
    monkeypatch.setenv("RHINVOICE_DATABASE_URL", database_url)
    return engine


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RHINVOICE_DATABASE_URL", raising=False)
    settings = Settings()
    assert settings.cookie_secure is True
    assert settings.run_migrations is True
    assert settings.static_dir is None
    assert str(settings.zone) == "Europe/Zurich"


def test_user_create_from_stdin(
    env: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{PASSWORD}\n"))
    code = cli.main(
        ["user", "create", "--email", "Anna@Example.com", "--name", "Anna", "--password-stdin"],
    )
    assert code == 0
    assert capsys.readouterr().out == "created user anna@example.com\n"
    with SqlUnitOfWork(env) as uow:
        assert uow.users.count() == 1


def test_user_create_prompts_twice(
    env: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("getpass.getpass", scripted_getpass(PASSWORD, PASSWORD))
    assert cli.main(["user", "create", "--email", "anna@example.com", "--name", "Anna"]) == 0
    with SqlUnitOfWork(env) as uow:
        assert uow.users.count() == 1


def test_user_create_rejects_mismatching_passwords(
    env: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("getpass.getpass", scripted_getpass(PASSWORD, "something else"))
    with pytest.raises(SystemExit, match=r"^passwords do not match$"):
        cli.main(["user", "create", "--email", "anna@example.com", "--name", "Anna"])
    with SqlUnitOfWork(env) as uow:
        assert uow.users.count() == 0


def test_user_create_reports_domain_errors(
    env: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    code = cli.main(
        ["user", "create", "--email", "anna@example.com", "--name", "Anna", "--password-stdin"],
    )
    assert code == 1
    assert capsys.readouterr().err == "error: password must be at least 12 characters long\n"
    assert env is not None


@pytest.mark.usefixtures("env")
def test_user_list_and_reset_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for email, name in (("zora@example.com", "Zora"), ("anna@example.com", "Anna Muster")):
        monkeypatch.setattr("sys.stdin", io.StringIO(f"{PASSWORD}\n"))
        cli.main(["user", "create", "--email", email, "--name", name, "--password-stdin"])
    capsys.readouterr()
    assert cli.main(["user", "list"]) == 0
    assert capsys.readouterr().out == "anna@example.com\tAnna Muster\nzora@example.com\tZora\n"

    monkeypatch.setattr(
        "getpass.getpass", scripted_getpass("a new long passphrase", "a new long passphrase")
    )
    assert cli.main(["user", "reset-password", "--email", " Anna@Example.com "]) == 0
    assert capsys.readouterr().out == "new password set for anna@example.com; its sessions ended\n"
    container = build_container(Settings())
    try:
        container.identity.login(Login(email="anna@example.com", password="a new long passphrase"))
    finally:
        container.engine.dispose()


def test_user_reset_password_reports_errors(
    env: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{PASSWORD}\n"))
    code = cli.main(["user", "reset-password", "--email", "nobody@example.com", "--password-stdin"])
    assert code == 1
    assert capsys.readouterr().err == "error: no user with e-mail nobody@example.com\n"
    assert env is not None


def test_migrate(env: Engine, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["migrate"]) == 0
    assert capsys.readouterr().out == "database is up to date\n"
    assert env is not None


@pytest.mark.parametrize(
    ("switched_on", "background"),
    [("true", ["update check", "recurring invoices"]), ("false", [])],
)
def test_serve_runs_uvicorn(
    env: Engine, monkeypatch: pytest.MonkeyPatch, switched_on: str, background: list[str]
) -> None:
    """Migrations, the update check and recurring invoices, all on or all off."""
    calls: list[dict[str, Any]] = []
    migrations: list[str] = []
    monkeypatch.setenv("RHINVOICE_RUN_MIGRATIONS", switched_on)
    monkeypatch.setenv("RHINVOICE_RECURRING", switched_on)
    monkeypatch.setenv("RHINVOICE_UPDATE_CHECK", switched_on)
    started: list[str] = []
    stopped: list[str] = []

    class RecordingJob(PeriodicJob):
        def start(self) -> None:
            started.append(self._thread.name)
            super().start()

        def stop(self, timeout: float = 30) -> None:
            stopped.append(self._thread.name)
            super().stop(timeout)

    monkeypatch.setattr(cli, "PeriodicJob", RecordingJob)
    monkeypatch.setattr(cli, "upgrade", migrations.append)

    def fake_run(app: FastAPI, **kwargs: Any) -> None:  # noqa: ANN401 - mirrors uvicorn.run
        assert isinstance(app, FastAPI)
        app.state.container.engine.dispose()
        calls.append(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert cli.main(["serve", "--port", "9000"]) == 0
    assert calls == [
        {
            "host": "0.0.0.0",  # noqa: S104 - asserting the container default
            "port": 9000,
            "proxy_headers": True,
            "forwarded_allow_ips": "127.0.0.1",
        },
    ]
    assert len(migrations) == (1 if switched_on == "true" else 0)
    # The web server looks for new releases and writes due recurring invoices in the
    # background, unless switched off; the jobs end with it.
    assert started == background
    assert stopped == background
    assert env is not None


def test_serve_resets_a_public_demo_and_keeps_doing_it(
    env: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RHINVOICE_DEMO", "true")
    monkeypatch.setenv("RHINVOICE_DEMO_COUNTRY", "AT")
    resets: list[str] = []
    jobs: list[str] = []

    class RecordingJob(PeriodicJob):
        def start(self) -> None:
            jobs.append(self._thread.name)
            self.run_once()

    def record_reset(settings: Settings, container: object) -> None:
        assert container is not None
        resets.append(settings.demo_country)

    monkeypatch.setattr(cli, "PeriodicJob", RecordingJob)
    monkeypatch.setattr(cli, "reset_demo", record_reset)

    def fake_run(app: FastAPI, **_: object) -> None:
        app.state.container.engine.dispose()

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert cli.main(["serve"]) == 0
    # Reset at the start and then by the job; a demo writes no recurring invoices.
    assert resets == ["AT", "AT"]
    assert jobs == ["demo reset"]
    assert env is not None


def test_serve_refuses_to_reset_a_real_installation(
    env: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RHINVOICE_DEMO", "true")

    def refuse(_settings: Settings, container: Container) -> None:
        container.engine.dispose()
        raise NotADemoDatabaseError("refusing to reset")

    monkeypatch.setattr(cli, "reset_demo", refuse)
    assert cli.main(["serve"]) == 1
    assert capsys.readouterr().err == "error: refusing to reset\n"
    assert env is not None


def test_demo_links_are_checked_at_the_start() -> None:
    settings = Settings(demo_links=" de=https://de.example.org ,, AT=https://at.example.org")
    assert settings.demo_link_list == [
        (Country.DE, "https://de.example.org"),
        (Country.AT, "https://at.example.org"),
    ]
    assert Settings().demo_link_list == []
    for wrong in ("DE", "DE=http://de.example.org", "XX=https://x.example.org"):
        with pytest.raises(ValueError, match="demo_links"):
            Settings(demo_links=wrong)


def test_dev_factory_builds_an_app(env: Engine) -> None:
    from rhinvoice.api import dev  # noqa: PLC0415 - imported where it is used

    application = dev.app()
    assert application.title == "Rhinvoice"
    application.state.container.engine.dispose()
    assert env is not None


def test_demo_data(env: Engine, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["demo"]) == 1
    assert capsys.readouterr().err == "error: set up the company first (the first-start wizard)\n"
    with SqlUnitOfWork(env) as uow:
        uow.company.save(factories.company(name="Demo GmbH"))
        uow.commit()
    assert cli.main(["demo", "--without-documents"]) == 0
    assert capsys.readouterr().out == (
        "demo data: 9 customers, 8 articles, 2 bank accounts, 0 invoices, 0 quotes, "
        "0 old invoices taken over\n"
    )
    # Never into an installation that has data.
    assert cli.main(["demo"]) == 1
    assert "without customers and documents" in capsys.readouterr().err


def test_recurring_invoices_now(env: Engine, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["recurring"]) == 0
    assert capsys.readouterr().out == "recurring invoices: 0 written\n"
    customer = factories.customer()
    with SqlUnitOfWork(env) as uow:
        uow.company.save(factories.company())
        uow.customers.add(customer)
        today = datetime.now(UTC).date() - timedelta(days=1)
        uow.recurring.add(
            RecurringPlan(
                id=new_id(),
                name="Hosting",
                customer_id=customer.id,
                interval=Interval.MONTHLY,
                start_date=today,
                next_date=today,
                action=PlanAction.ISSUE,
                template=InvoiceTemplate(
                    currency=Currency.CHF,
                    price_mode=PriceMode.NET,
                    lines=(
                        LineInput(
                            kind=LineKind.ITEM, description="Hosting", unit_price="29"
                        ).to_domain(0),
                    ),
                ),
                created_at=datetime.now(UTC),
            )
        )
        uow.commit()
    assert cli.main(["recurring"]) == 1
    # No bank account yet: the invoice stays a draft and says why.
    assert capsys.readouterr().out == (
        f"Hosting {today.isoformat()} draft (bank_account_missing: please add a bank account"
        " for CHF before issuing invoices in CHF)\nrecurring invoices: 1 written\n"
    )


def test_a_newer_database_is_refused(
    env: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    started: list[FastAPI] = []

    def fake_run(app: FastAPI, **_options: object) -> None:
        started.append(app)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    with env.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '9999'"))
    try:
        assert cli.main(["serve"]) == 1
        message = capsys.readouterr().err
        assert message.startswith(
            "error: the database was set up by a newer version of Rhinvoice (schema 9999); "
            "this version knows schemas up to "
        )
        assert "restore a backup of this version" in message
        assert cli.main(["migrate"]) == 1
        assert started == []
    finally:
        with env.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD}
            )


def test_a_server_in_a_thread_ends_when_asked_to(
    env: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The program window of the installation without Docker stops its server this way."""
    monkeypatch.setenv("RHINVOICE_RUN_MIGRATIONS", "false")
    monkeypatch.setenv("RHINVOICE_RECURRING", "false")
    monkeypatch.setenv("RHINVOICE_UPDATE_CHECK", "false")
    ended = threading.Event()

    class Server:
        def __init__(self, config: uvicorn.Config) -> None:
            assert (config.host, config.port) == ("127.0.0.1", 9001)
            assert isinstance(config.app, FastAPI)
            config.app.state.container.engine.dispose()
            self.should_exit = False

        def run(self) -> None:
            while not self.should_exit:
                ended.wait(0.01)
            ended.set()

    monkeypatch.setattr(uvicorn, "Server", Server)
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    assert cli.serve(Settings(), "127.0.0.1", 9001, stop=stop) == 0
    assert ended.is_set()
    assert env is not None


class OwnBackups:
    """The backup setup and archive of the installation without Docker, standing in."""

    def __init__(self) -> None:
        self.folder_set: str | None = None

    def target(self) -> BackupTarget:
        # Looks through the cloud folders: never every half minute (macOS may ask each time).
        msg = "the backup job asked for the folder suggestions"
        raise AssertionError(msg)

    def folder(self) -> str | None:
        return self.folder_set

    def set_up(self, folder: str) -> str:
        self.folder_set = folder
        return "K7QM"

    def recovery_key(self) -> str | None:
        return None

    def confirm_key(self) -> None:
        """Nothing to keep here."""

    def back_up(self) -> Snapshot:
        return Snapshot("4f3a9c1e", 1)

    def maintain(self, *, verify: bool) -> None:
        del verify


def test_the_installation_without_docker_makes_its_own_backups(
    env: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0023: a background job, once a folder is set up; runs left running fail."""
    monkeypatch.setenv("RHINVOICE_RECURRING", "false")
    monkeypatch.setenv("RHINVOICE_UPDATE_CHECK", "false")
    with env.begin() as connection:
        connection.execute(text("DELETE FROM backup_runs"))
        connection.execute(
            insert(backup_runs).values(
                started_at=datetime.now(UTC), reason="manual", status="running"
            )
        )
    jobs: list[tuple[str, PeriodicJob]] = []

    class RecordingJob(PeriodicJob):
        def __init__(
            self, job: Callable[[], object], *, interval: float, first_delay: float, name: str
        ) -> None:
            super().__init__(job, interval=interval, first_delay=first_delay, name=name)
            self.name = name

        def start(self) -> None:
            jobs.append((self.name, self))

        def stop(self, timeout: float = 30) -> None:
            del timeout

    monkeypatch.setattr(cli, "PeriodicJob", RecordingJob)

    def run_server(app: FastAPI, **_options: object) -> None:
        app.state.container.engine.dispose()

    ticks: list[BackupWorker] = []

    def tick(worker: BackupWorker) -> None:
        ticks.append(worker)

    monkeypatch.setattr(uvicorn, "run", run_server)
    monkeypatch.setattr(BackupWorker, "tick", tick)
    backups = OwnBackups()
    own = OwnServices(backup_setup=backups, backup_archive=backups)
    assert cli.serve(Settings(), "127.0.0.1", 9002, own=own) == 0
    [(name, job)] = jobs
    assert name == "backups"
    with env.begin() as connection:
        assert connection.execute(text("SELECT status FROM backup_runs")).scalar_one() == "failed"
    job.run_once()  # no folder yet: nothing to do
    assert ticks == []
    backups.folder_set = "/Users/anna/OneDrive/Rhinvoice-Backup"
    job.run_once()
    assert len(ticks) == 1
