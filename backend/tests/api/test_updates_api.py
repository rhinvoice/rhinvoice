from collections.abc import Callable, Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from rhinvoice.api.app import create_app
from rhinvoice.api.container import Container
from rhinvoice.application.updates.handlers import UpdateHandlers
from rhinvoice.application.updates.ports import PackageFile, Release
from tests.api.conftest import CLIENT_HEADERS, EMAIL, PASSWORD

RELEASE = Release(
    version="0.7.0",
    notes_url="https://github.com/rhinvoice/rhinvoice/releases/tag/v0.7.0",
    runtime=1,
    packages={"windows-x64": PackageFile("https://example.org/app.zip", "ab" * 32, 1)},
)


class Feed:
    def latest(self) -> Release:
        return RELEASE


class Installer:
    platform = "windows-x64"
    setup = "windows-x64"
    runtime = 1

    def __init__(self) -> None:
        self.installed: list[str] = []
        self.taken_back: set[str] = set()

    def install(self, release: Release) -> None:
        self.installed.append(release.version)

    def failed(self, version: str) -> bool:
        return version in self.taken_back


type ClientFactory = Callable[[Installer | None], TestClient]


@pytest.fixture
def clients(container: Container) -> Iterator[ClientFactory]:
    """Log in to an app whose updates come from a fixed release, with or without installer."""
    opened: list[TestClient] = []

    def factory(installer: Installer | None) -> TestClient:
        updates = UpdateHandlers(Feed(), "0.6.2", container.clock, installer)
        updates.refresh()
        client = TestClient(create_app(replace(container, updates=updates)), headers=CLIENT_HEADERS)
        opened.append(client.__enter__())
        setup = {"email": EMAIL, "display_name": "Anna Muster", "password": PASSWORD}
        if client.post("/api/auth/setup", json=setup).status_code != 201:
            client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/updates").status_code == 401
    assert client.post("/api/updates/install").status_code == 401
    assert client.post("/api/updates/check").status_code == 401


def test_before_the_first_check_nothing_is_known(user_client: TestClient) -> None:
    body = user_client.get("/api/updates").json()
    assert body["latest"] is None
    assert body["action"] == "none"
    assert body["checked_at"] is None


def test_a_server_installation_is_told_the_release(clients: ClientFactory) -> None:
    client = clients(None)
    assert client.get("/api/updates").json() == {
        "current": "0.6.2",
        "latest": "0.7.0",
        "action": "command",
        "notes_url": "https://github.com/rhinvoice/rhinvoice/releases/tag/v0.7.0",
        "setup_url": None,
        "checked_at": "2026-01-15T09:00:00Z",
        "failed": False,
        "can_check": True,
    }
    refused = client.post("/api/updates/install")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "no_update"


def test_the_installation_without_docker_installs_it(clients: ClientFactory) -> None:
    installer = Installer()
    client = clients(installer)
    assert client.get("/api/updates").json()["action"] == "install"
    response = client.post("/api/updates/install")
    assert response.status_code == 202
    assert installer.installed == ["0.7.0"]


def test_a_check_on_request_answers_with_the_release(clients: ClientFactory) -> None:
    response = clients(Installer()).post("/api/updates/check")
    assert response.status_code == 200
    assert response.json()["action"] == "install"


def test_a_check_is_refused_when_it_is_switched_off(container: Container) -> None:
    updates = UpdateHandlers(None, "0.6.2", container.clock)
    with TestClient(
        create_app(replace(container, updates=updates)), headers=CLIENT_HEADERS
    ) as client:
        setup = {"email": EMAIL, "display_name": "Anna Muster", "password": PASSWORD}
        assert client.post("/api/auth/setup", json=setup).status_code == 201
        assert client.get("/api/updates").json()["can_check"] is False
        refused = client.post("/api/updates/check")
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "update_check_off"
