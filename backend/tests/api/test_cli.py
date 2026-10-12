import io
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import uvicorn
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from sqlalchemy import Engine, text

from rhinvoice.api import cli
from rhinvoice.api.container import Container
from rhinvoice.api.settings import Settings
from rhinvoice.application.document.handlers import LineInput
from rhinvoice.domain.document.lines import LineKind, PriceMode
from rhinvoice.domain.recurring.plan import Interval, InvoiceTemplate, PlanAction, RecurringPlan
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency
from rhinvoice.infrastructure.db.migrate import NotADemoDatabaseError, alembic_config
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


def test_migrate(env: Engine, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["migrate"]) == 0
    assert capsys.readouterr().out == "database is up to date\n"
    assert env is not None


@pytest.mark.parametrize(("run_migrations", "recurring"), [("true", "true"), ("false", "false")])
def test_serve_runs_uvicorn(
    env: Engine,
    monkeypatch: pytest.MonkeyPatch,
    run_migrations: str,
    recurring: str,
) -> None:
    calls: list[dict[str, Any]] = []
    migrations: list[str] = []
    monkeypatch.setenv("RHINVOICE_RUN_MIGRATIONS", run_migrations)
    monkeypatch.setenv("RHINVOICE_RECURRING", recurring)
    jobs: list[str] = []

    class RecordingJob(PeriodicJob):
        def start(self) -> None:
            jobs.append("start")
            super().start()

        def stop(self, timeout: float = 30) -> None:
            jobs.append("stop")
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
    assert len(migrations) == (1 if run_migrations == "true" else 0)
    # The web server writes due recurring invoices in the background, unless switched off.
    assert jobs == (["start", "stop"] if recurring == "true" else [])
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
        "demo data: 9 customers, 8 articles, 2 bank accounts, 0 invoices, 0 quotes\n"
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
