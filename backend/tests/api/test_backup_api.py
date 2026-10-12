from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert

from rhinvoice.infrastructure.db.tables import backup_runs


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
