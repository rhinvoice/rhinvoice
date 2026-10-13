from datetime import timedelta

import pyotp
from fastapi.testclient import TestClient

from tests.api.conftest import CLIENT_HEADERS, EMAIL, NOW, PASSWORD, AppFactory


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_unreachable_database(app_factory: AppFactory) -> None:
    broken = app_factory(database_url="postgresql+psycopg://nobody:x@127.0.0.1:1/none")
    with TestClient(broken) as client:
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unreachable"}


def test_setup_flow(client: TestClient) -> None:
    assert client.get("/api/auth/setup").json() == {"needs_setup": True}
    response = client.post(
        "/api/auth/setup",
        json={"email": EMAIL, "display_name": "Anna Muster", "password": PASSWORD},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert body["display_name"] == "Anna Muster"
    assert body["totp_enabled"] is False
    cookie = response.headers["set-cookie"]
    assert "rhinvoice_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Max-Age=2592000" in cookie
    assert client.get("/api/auth/setup").json() == {"needs_setup": False}
    assert client.get("/api/auth/me").json()["email"] == EMAIL


def test_setup_is_only_possible_once(user_client: TestClient) -> None:
    response = user_client.post(
        "/api/auth/setup",
        json={"email": "ben@example.com", "display_name": "Ben", "password": PASSWORD},
    )
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": "setup has already been completed",
            "details": {},
        },
    }


def test_secure_cookie_flag(app_factory: AppFactory) -> None:
    with TestClient(app_factory(cookie_secure=True), headers=CLIENT_HEADERS) as client:
        response = client.post(
            "/api/auth/setup",
            json={"email": EMAIL, "display_name": "Anna", "password": PASSWORD},
        )
    assert "Secure" in response.headers["set-cookie"]


def test_login_logout(user_client: TestClient) -> None:
    user_client.post("/api/auth/logout")
    assert user_client.get("/api/auth/me").status_code == 401
    wrong = user_client.post("/api/auth/login", json={"email": EMAIL, "password": "nope nope"})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "authentication_failed"
    response = user_client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL
    assert user_client.get("/api/auth/me").status_code == 200
    logout = user_client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert 'rhinvoice_session=""' in logout.headers["set-cookie"]


def test_me_requires_login(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "not_logged_in",
        "message": "not logged in",
        "details": {},
    }
    # Unlike a wrong password, an ended session has its own code: the interface logs out.
    client.cookies.set("rhinvoice_session", "forged")
    expired = client.get("/api/auth/me")
    assert expired.status_code == 401
    assert expired.json()["error"] == {
        "code": "session_expired",
        "message": "session expired, please log in again",
        "details": {},
    }


def test_change_password(user_client: TestClient) -> None:
    response = user_client.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": "a brand new password"},
    )
    assert response.status_code == 204
    user_client.post("/api/auth/logout")
    login = user_client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": "a brand new password"},
    )
    assert login.status_code == 200


def test_totp_flow(user_client: TestClient) -> None:
    setup = user_client.post("/api/auth/totp/setup").json()
    assert setup["provisioning_uri"].startswith("otpauth://totp/Rhinvoice:")
    totp = pyotp.TOTP(setup["secret"])
    # Codes of consecutive time steps (within the ±1 step window): each one is used once.
    previous_code = totp.at(NOW - timedelta(seconds=30))
    confirm = user_client.post("/api/auth/totp/confirm", json={"code": previous_code})
    assert confirm.status_code == 200
    assert confirm.json()["totp_enabled"] is True

    user_client.post("/api/auth/logout")
    needs_code = user_client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert needs_code.status_code == 401
    assert needs_code.json()["error"]["code"] == "totp_required"
    replay = user_client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD, "totp_code": previous_code},
    )
    assert replay.status_code == 401
    login = user_client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD, "totp_code": totp.at(NOW)},
    )
    assert login.status_code == 200

    next_code = totp.at(NOW + timedelta(seconds=30))
    disabled = user_client.post(
        "/api/auth/totp/disable",
        json={"password": PASSWORD, "code": next_code},
    )
    assert disabled.status_code == 200
    assert disabled.json()["totp_enabled"] is False
