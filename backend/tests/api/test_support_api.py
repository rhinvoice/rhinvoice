from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.conftest import CLIENT_HEADERS, EMAIL, PASSWORD, AppFactory


def test_the_report_needs_a_login(client: TestClient) -> None:
    assert client.get("/api/support/report").status_code == 401


def test_a_server_reports_without_a_log(user_client: TestClient) -> None:
    body = user_client.get("/api/support/report").json()
    assert body["installation"] == "server"
    assert body["log"] is None
    assert body["version"]
    assert body["system"]


def test_the_program_reports_the_end_of_its_log(app_factory: AppFactory, tmp_path: Path) -> None:
    log = tmp_path / "rhinvoice.log"
    log.write_text("INFO: started\nERROR: no printer\n", encoding="utf-8")
    with TestClient(app_factory(log_file=log), headers=CLIENT_HEADERS) as client:
        setup = {"email": EMAIL, "display_name": "Anna Muster", "password": PASSWORD}
        assert client.post("/api/auth/setup", json=setup).status_code == 201
        body = client.get("/api/support/report").json()
    assert body["installation"] == "desktop"
    assert body["log"] == "INFO: started\nERROR: no printer"
