"""A forgotten password over the API: a code in the data folder, or the administrator."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.conftest import CLIENT_HEADERS, EMAIL, PASSWORD, AppFactory

NEW_PASSWORD = "a new and long passphrase"
FILE = "Rhinvoice-Passwort-Password.txt"


def code_in(folder: Path) -> str:
    match = re.search(r"^Code: (\S+)$", (folder / FILE).read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_on_a_server_the_administrator_resets_it(user_client: TestClient) -> None:
    user_client.cookies.clear()
    assert user_client.get("/api/auth/password-reset").json() == {
        "method": "administrator",
        "location": None,
    }
    refused = user_client.post("/api/auth/password-reset")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "reset_by_administrator"


def test_without_docker_a_code_in_the_data_folder_resets_it(
    user_client: TestClient, app_factory: AppFactory, tmp_path: Path, no_windows: list[Path]
) -> None:
    session = user_client.cookies.get("rhinvoice_session")
    with TestClient(app_factory(reset_code_dir=tmp_path), headers=CLIENT_HEADERS) as client:
        assert client.get("/api/auth/password-reset").json() == {
            "method": "file",
            "location": str(tmp_path / FILE),
        }
        assert client.post("/api/auth/password-reset").status_code == 204
        assert no_windows == [tmp_path / FILE]  # shown to the computer's user
        text = (tmp_path / FILE).read_text(encoding="utf-8")
        assert EMAIL in text
        wrong = client.post(
            "/api/auth/password-reset/confirm",
            json={"email": EMAIL, "code": "AAAAA-AAAAA", "new_password": NEW_PASSWORD},
        )
        assert wrong.status_code == 409
        assert wrong.json()["error"]["code"] == "reset_code_invalid"
        confirmed = client.post(
            "/api/auth/password-reset/confirm",
            json={"email": EMAIL, "code": code_in(tmp_path), "new_password": NEW_PASSWORD},
        )
        assert confirmed.status_code == 204, confirmed.text
        assert not (tmp_path / FILE).exists()
        login = client.post("/api/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
        assert login.status_code == 200
        old = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert old.status_code == 401
    # The session from before the reset has ended.
    user_client.cookies.set("rhinvoice_session", session or "")
    assert user_client.get("/api/auth/me").status_code == 401


def test_the_public_demo_offers_no_reset(app_factory: AppFactory, tmp_path: Path) -> None:
    with TestClient(
        app_factory(demo=True, reset_code_dir=tmp_path), headers=CLIENT_HEADERS
    ) as client:
        assert client.post("/api/auth/password-reset").status_code == 403
        confirm = client.post(
            "/api/auth/password-reset/confirm",
            json={"email": EMAIL, "code": "AAAAA-AAAAA", "new_password": NEW_PASSWORD},
        )
        assert confirm.status_code == 403
