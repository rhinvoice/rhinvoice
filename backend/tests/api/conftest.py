from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from rhinvoice.api.app import create_app
from rhinvoice.api.container import Container, build_container
from rhinvoice.api.settings import Settings
from rhinvoice.domain.shared.clock import FixedClock
from tests.api.test_masterdata_api import ADDRESS
from tests.unit.domain.factories import CH_IBAN

NOW = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
CLIENT_HEADERS = {"X-Rhinvoice-Client": "test"}
EMAIL = "anna@example.com"
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def no_windows(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Never open the code file of a forgotten password on the machine running the tests."""
    opened: list[Path] = []
    monkeypatch.setattr("rhinvoice.api.container.open_with_system", opened.append)
    return opened


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def container(database_url: str, engine: Engine, clock: FixedClock) -> Iterator[Container]:
    assert engine is not None  # truncates tables after each test
    built = build_container(Settings(database_url=database_url, cookie_secure=False), clock)
    yield built
    built.engine.dispose()


type AppFactory = Callable[..., FastAPI]


@pytest.fixture
def app_factory(container: Container) -> Iterator[AppFactory]:
    """Build extra apps with modified settings; their engines are disposed afterwards."""
    built: list[Container] = []

    def factory(**settings_updates: object) -> FastAPI:
        settings = container.settings.model_copy(update=settings_updates)
        extra = build_container(settings, container.clock)
        built.append(extra)
        return create_app(extra)

    yield factory
    for extra in built:
        extra.engine.dispose()


@pytest.fixture
def app(container: Container) -> FastAPI:
    return create_app(container)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, headers=CLIENT_HEADERS) as test_client:
        yield test_client


@pytest.fixture
def user_client(client: TestClient) -> TestClient:
    """Return a client logged in as the first user."""
    response = client.post(
        "/api/auth/setup",
        json={"email": EMAIL, "display_name": "Anna Muster", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return client


@pytest.fixture
def customer_id(user_client: TestClient) -> str:
    company = {
        "name": "Muster GmbH",
        "address": ADDRESS,
        "default_currency": "CHF",
        "vat_number": "CHE-123.456.788",
        "cash_rounding": True,
    }
    assert user_client.put("/api/company", json=company).status_code == 200
    account = {"currency": "CHF", "bank_name": "Musterbank", "holder": "Muster", "iban": CH_IBAN}
    assert user_client.post("/api/bank-accounts", json=account).status_code == 201
    customer = {"kind": "company", "company_name": "Beispiel AG", "address": ADDRESS}
    created = user_client.post("/api/customers", json=customer)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])
