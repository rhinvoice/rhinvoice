from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert

from rhinvoice.api.app import create_app
from rhinvoice.api.container import Container
from rhinvoice.application.backup.handlers import BackupHandlers
from rhinvoice.application.backup.ports import BackupFailed, BackupTarget, FolderSuggestion
from rhinvoice.infrastructure.db.tables import backup_runs
from tests.api.conftest import CLIENT_HEADERS, EMAIL, PASSWORD

ONEDRIVE = FolderSuggestion("OneDrive", "/Users/anna/OneDrive/Rhinvoice-Backup")


class Setup:
    """The folder and key of the installation without Docker, standing in."""

    def __init__(self) -> None:
        self.folder: str | None = None
        self.confirmed = False

    def target(self) -> BackupTarget:
        return BackupTarget(
            folder=self.folder, suggestions=[ONEDRIVE], key_confirmed=self.confirmed
        )

    def set_up(self, folder: str) -> str:
        if not folder.startswith("/"):
            msg = "choose the full path of a folder"
            raise BackupFailed(msg)
        self.folder = folder
        return "K7QM-2XWP"

    def recovery_key(self) -> str | None:
        return None if self.folder is None else "K7QM-2XWP"

    def confirm_key(self) -> None:
        self.confirmed = True


@pytest.fixture
def desktop_client(container: Container) -> Iterator[TestClient]:
    """Log in to an app of the installation without Docker."""
    backup = BackupHandlers(uow=container.backup.uow, clock=container.clock, setup=Setup())
    app = create_app(replace(container, backup=backup))
    with TestClient(app, headers=CLIENT_HEADERS) as client:
        setup = {"email": EMAIL, "display_name": "Anna Muster", "password": PASSWORD}
        assert client.post("/api/auth/setup", json=setup).status_code == 201
        yield client


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/backup").status_code == 401
    assert client.post("/api/backup").status_code == 401


def test_requests_need_a_backup_container(user_client: TestClient) -> None:
    assert user_client.get("/api/backup").json() == {
        "state": "not_set_up",
        "last_success": None,
        "requested_at": None,
        "runs": [],
    }
    refused = user_client.post("/api/backup")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "backup_not_set_up"


def test_runs_recorded_by_the_backup_container(user_client: TestClient, engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(backup_runs).values(
                started_at=datetime(2026, 3, 9, 8, 0, tzinfo=UTC),
                finished_at=datetime(2026, 3, 9, 8, 1, tzinfo=UTC),
                reason="document",
                status="succeeded",
                snapshot_id="52365e00",
                data_added=48_000,
                message=None,
            )
        )
    body = user_client.get("/api/backup").json()
    run = {
        "id": body["runs"][0]["id"],
        "started_at": "2026-03-09T08:00:00Z",
        "finished_at": "2026-03-09T08:01:00Z",
        "reason": "document",
        "status": "succeeded",
        "snapshot_id": "52365e00",
        "data_added": 48_000,
        "message": None,
    }
    assert body == {"state": "current", "last_success": run, "requested_at": None, "runs": [run]}
    requested = user_client.post("/api/backup")
    assert requested.status_code == 202, requested.text
    assert requested.json()["requested_at"] is not None
    assert user_client.get("/api/backup").json()["requested_at"] == requested.json()["requested_at"]


def test_the_setup_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/backup/setup").status_code == 401
    assert client.put("/api/backup/setup", json={"folder": "/x"}).status_code == 401
    assert client.get("/api/backup/key").status_code == 401
    assert client.post("/api/backup/key/confirmed").status_code == 401


def test_in_the_docker_setup_the_backup_container_is_set_up(user_client: TestClient) -> None:
    for response in (
        user_client.get("/api/backup/setup"),
        user_client.put("/api/backup/setup", json={"folder": "/x"}),
        user_client.get("/api/backup/key"),
        user_client.post("/api/backup/key/confirmed"),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "backup_by_container"


def test_the_installation_without_docker_sets_up_a_folder_and_key(
    desktop_client: TestClient,
) -> None:
    suggestion = {"name": "OneDrive", "path": "/Users/anna/OneDrive/Rhinvoice-Backup"}
    assert desktop_client.get("/api/backup/setup").json() == {
        "folder": None,
        "suggestions": [suggestion],
        "key_confirmed": False,
    }
    missing = desktop_client.get("/api/backup/key")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "backup_not_set_up"
    refused = desktop_client.put("/api/backup/setup", json={"folder": "Backup"})
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "backup_folder_unusable"
    set_up = desktop_client.put("/api/backup/setup", json={"folder": suggestion["path"]})
    assert set_up.status_code == 200, set_up.text
    assert set_up.json() == {"key": "K7QM-2XWP"}
    # The first backup is on its way: the page shows it as requested.
    assert desktop_client.get("/api/backup").json()["requested_at"] is not None
    assert desktop_client.get("/api/backup/key").json() == {"key": "K7QM-2XWP"}
    confirmed = desktop_client.post("/api/backup/key/confirmed")
    assert confirmed.json() == {
        "folder": suggestion["path"],
        "suggestions": [suggestion],
        "key_confirmed": True,
    }
    assert desktop_client.put("/api/backup/setup", json={"folder": ""}).status_code == 422
