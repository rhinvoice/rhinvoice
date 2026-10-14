"""A public demo: how to get in, and what it refuses."""

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rhinvoice.api.middleware import MAX_BODY_BYTES
from rhinvoice.application.demo.handlers import DEMO_EMAIL, DEMO_PASSWORD
from rhinvoice.application.identity.handlers import CreateUser
from rhinvoice.domain.shared.country import Country
from tests.api.conftest import CLIENT_HEADERS, EMAIL, PASSWORD, AppFactory
from tests.api.test_masterdata_api import ADDRESS

if TYPE_CHECKING:
    from rhinvoice.api.container import Container

LINKS = "CH=https://ch.demo.example.org, DE=https://de.demo.example.org"


@pytest.fixture
def demo_app(app_factory: AppFactory) -> FastAPI:
    return app_factory(demo=True, demo_country=Country.CH, demo_links=LINKS)


@pytest.fixture
def demo_client(demo_app: FastAPI) -> Iterator[TestClient]:
    """Log a visitor in to a demo whose login exists (the reset creates it)."""
    container: Container = demo_app.state.container
    container.identity.create_first_user(
        CreateUser(email=EMAIL, display_name="Demo", password=PASSWORD)
    )
    with TestClient(demo_app, headers=CLIENT_HEADERS) as client:
        login = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert login.status_code == 200, login.text
        yield client


def test_a_normal_installation_is_no_demo(client: TestClient) -> None:
    response = client.get("/api/demo")
    assert response.json() == {
        "enabled": False,
        "country": None,
        "email": None,
        "password": None,
        "reset_minutes": None,
        "links": [],
    }
    assert "X-Robots-Tag" not in response.headers


def test_the_demo_tells_how_to_get_in(demo_client: TestClient) -> None:
    demo_client.post("/api/auth/logout")
    response = demo_client.get("/api/demo")
    assert response.json() == {
        "enabled": True,
        "country": "CH",
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "reset_minutes": 60,
        # Its own country is not linked.
        "links": [{"country": "DE", "url": "https://de.demo.example.org"}],
    }
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/auth/setup"),
        ("post", "/api/auth/password"),
        ("post", "/api/auth/totp/setup"),
        ("post", "/api/auth/totp/confirm"),
        ("post", "/api/auth/totp/disable"),
        ("put", "/api/company/logo"),
        ("delete", "/api/company/logo"),
        ("put", "/api/mail/server"),
        ("post", "/api/mail/test"),
        ("post", "/api/documents/00000000-0000-0000-0000-000000000000/mail"),
        ("post", "/api/reminders/00000000-0000-0000-0000-000000000000/mail"),
        ("post", "/api/documents/00000000-0000-0000-0000-000000000000/files"),
        ("post", "/api/backup"),
        ("put", "/api/backup/setup"),
        ("get", "/api/backup/key"),
        ("post", "/api/backup/key/confirmed"),
        ("post", "/api/imports/customers/preview"),
        ("post", "/api/imports/invoices"),
        ("post", "/api/imports/articles/templates"),
        ("delete", "/api/imports/templates/00000000-0000-0000-0000-000000000000"),
        ("get", "/api/imports/invoices/templates"),
    ],
)
def test_the_demo_refuses_what_would_lock_others_out_send_mail_or_take_files(
    demo_client: TestClient, method: str, path: str
) -> None:
    response = demo_client.request(method, path, json={})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "demo_locked"


def test_the_demo_company_keeps_its_country(demo_client: TestClient) -> None:
    company = {"name": "Muster GmbH", "address": ADDRESS, "default_currency": "CHF"}
    assert demo_client.put("/api/company", json=company).status_code == 200
    moved = demo_client.put(
        "/api/company",
        json={**company, "address": {**ADDRESS, "postal_code": "10115", "country": "DE"}},
    )
    assert moved.status_code == 403
    assert moved.json()["error"]["code"] == "demo_locked"


def test_the_demo_login_is_never_locked(demo_client: TestClient) -> None:
    demo_client.post("/api/auth/logout")
    for _ in range(8):
        wrong = demo_client.post("/api/auth/login", json={"email": EMAIL, "password": "x" * 12})
        assert wrong.status_code == 401
    right = demo_client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert right.status_code == 200, right.text


def test_the_demo_never_asks_for_a_first_user(demo_app: FastAPI) -> None:
    with TestClient(demo_app, headers=CLIENT_HEADERS) as client:
        assert client.get("/api/auth/setup").json() == {"needs_setup": False}


def test_nobody_gets_in_while_the_demo_is_reset(demo_client: TestClient, demo_app: FastAPI) -> None:
    container: Container = demo_app.state.container
    container.demo_reset.set()
    try:
        response = demo_client.get("/api/customers")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "demo_resetting"
        assert response.headers["Retry-After"] == "60"
        assert demo_client.get("/api/health").status_code == 200
    finally:
        container.demo_reset.clear()
    assert demo_client.get("/api/customers").status_code == 200


def test_the_demo_slows_down_floods(demo_app: FastAPI) -> None:
    with TestClient(demo_app, headers=CLIENT_HEADERS) as client:
        wrong = {"email": EMAIL, "password": "x" * 12}
        statuses = [client.post("/api/auth/login", json=wrong).status_code for _ in range(11)]
        assert statuses == [401] * 10 + [429]
        limited = client.post("/api/auth/login", json=wrong)
        assert limited.json()["error"]["code"] == "rate_limited"
        # Reading goes on.
        assert client.get("/api/demo").status_code == 200


def test_the_demo_takes_no_uploads(demo_client: TestClient) -> None:
    """Whatever a shared demo stored, every visitor could open: it takes no files at all."""
    response = demo_client.post(
        "/api/imports/invoices",
        files={
            "file": ("rechnungen.csv", b"Nummer\nR20150001\n", "text/csv"),
            "files": ("R20150001.pdf", b"%PDF-1.4 invoice", "application/pdf"),
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "demo_locked"
    large = demo_client.post(
        "/api/imports/invoices",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )
    assert large.status_code == 413
