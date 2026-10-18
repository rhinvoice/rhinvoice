import json
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from rhinvoice.api.app import operation_id
from rhinvoice.api.errors import allowed_methods, integrity_error_response, status_for
from rhinvoice.api.middleware import MAX_BODY_BYTES, MAX_IMPORT_BODY_BYTES, SECURITY_HEADERS
from rhinvoice.application.errors import AccountLockedError, ConflictError, NotFoundError
from rhinvoice.domain.shared.errors import (
    DomainError,
    InvalidStateError,
    ValidationError,
)
from tests.api.conftest import AppFactory


def test_state_changing_requests_need_client_header(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/api/auth/logout")
        assert response.status_code == 403
        assert response.json() == {
            "error": {
                "code": "csrf_rejected",
                "message": "missing x-rhinvoice-client header",
                "details": {},
            },
        }
        assert client.get("/api/health").status_code == 200


def test_security_headers_are_set(client: TestClient) -> None:
    response = client.get("/api/health")
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_request_validation_errors_use_error_format(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"email": "a@b.example"})
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "the request is invalid",
            "details": {"password": "Field required"},
        },
    }
    whole_body = client.post("/api/auth/login", content=b"[]")
    assert whole_body.status_code == 422
    assert list(whole_body.json()["error"]["details"]) == ["body"]


def test_schema_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/auth/setup",
        json={"email": "not-an-email", "display_name": "Anna", "password": "long enough pw"},
    )
    assert response.status_code == 422
    assert list(response.json()["error"]["details"]) == ["email"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (AccountLockedError("x"), 401),
        (NotFoundError("x"), 404),
        (ConflictError("x"), 409),
        (InvalidStateError("x"), 409),
        (ValidationError("f", "x"), 422),
        (DomainError("x"), 400),
    ],
)
def test_domain_errors_map_to_status_codes(error: DomainError, status: int) -> None:
    assert status_for(error) == status


def test_method_not_allowed_lists_all_methods(client: TestClient) -> None:
    response = client.delete("/api/auth/setup")
    assert response.status_code == 405
    assert response.headers["allow"] == "GET, POST"
    assert response.json()["error"]["code"] == "http_error"


def test_method_not_allowed_prefers_the_most_specific_path(user_client: TestClient) -> None:
    # "/api/documents/preview" also matches "/api/documents/{document_id}".
    response = user_client.request("PATCH", "/api/documents/preview")
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


def test_allowed_methods_of_unknown_paths(app: FastAPI) -> None:
    request = Request({"type": "http", "app": app, "path": "/nowhere", "headers": []})
    assert allowed_methods(request) == []


def test_malformed_json_is_a_bad_request(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_openapi_documents_cookie_auth(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    assert schema["components"]["securitySchemes"]["APIKeyCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "rhinvoice_session",
    }


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return tmp_path


def test_frontend_is_served_with_spa_fallback(app_factory: AppFactory, static_dir: Path) -> None:
    with TestClient(app_factory(static_dir=static_dir)) as client:
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert client.get("/favicon.svg").text == "<svg/>"
        index = client.get("/documents/123")
        assert index.text == "<html>app</html>"
        assert index.headers["cache-control"] == "no-cache"
        assert client.get("/").text == "<html>app</html>"
        assert client.get("/assets").text == "<html>app</html>"
        assert client.get("/../../etc/passwd").text == "<html>app</html>"
        assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}
        unknown_api = client.get("/api/unknown")
        assert unknown_api.status_code == 404
        assert unknown_api.json()["error"]["code"] == "http_error"
        assert client.get("/api").status_code == 404


def test_operation_ids_are_readable(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    ids = {
        operation["operationId"] for path in schema["paths"].values() for operation in path.values()
    }
    assert {"auth_login", "auth_logout", "auth_me", "system_health"} <= ids


def test_operation_id_without_tags() -> None:
    route = APIRoute("/x", endpoint=lambda: None, name="thing")
    assert operation_id(route) == "default_thing"


def test_number_rendering() -> None:
    from decimal import Decimal  # noqa: PLC0415

    from rhinvoice.api.schemas import plain_number, price_text  # noqa: PLC0415

    assert price_text(Decimal("150.0000")) == "150.00"
    assert price_text(Decimal("150.5")) == "150.50"
    assert price_text(Decimal("12.3450")) == "12.345"
    assert price_text(Decimal(0)) == "0.00"
    assert plain_number(Decimal("2.50")) == "2.5"
    assert plain_number(Decimal("10.00")) == "10"
    assert plain_number(Decimal("0.00")) == "0"


class _Diagnostics:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _DriverError(Exception):
    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("duplicate key")
        self.diag = _Diagnostics(constraint_name)


def _integrity_error(constraint_name: str | None) -> IntegrityError:
    return IntegrityError("INSERT …", None, _DriverError(constraint_name))


def test_unique_violations_become_conflicts_on_the_field(app: FastAPI) -> None:
    def race() -> None:
        raise _integrity_error("uq_customers_number")

    app.add_api_route("/api/test-race", race)
    with TestClient(app) as client:
        response = client.get("/api/test-race")
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "conflict",
        "message": "this number is already taken",
        "details": {"number": "this number is already taken"},
    }


@pytest.mark.parametrize("constraint", ["ck_something_else", None])
def test_other_integrity_errors_are_generic_conflicts(constraint: str | None) -> None:
    response = integrity_error_response(_integrity_error(constraint))
    assert response.status_code == 409
    assert json.loads(bytes(response.body))["error"] == {
        "code": "conflict",
        "message": "the change conflicts with existing data, please reload and try again",
        "details": {},
    }


def test_integrity_errors_without_diagnostics_are_generic_conflicts() -> None:
    error = IntegrityError("INSERT …", None, Exception("no diagnostics"))
    assert integrity_error_response(error).status_code == 409


def test_oversized_requests_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/customers",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_large"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_import_files_may_be_larger(client: TestClient) -> None:
    larger = client.post(
        "/api/imports/customers/preview",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    # Not refused for its size, but as a broken form (read before the login is checked).
    assert larger.status_code == 400
    too_large = client.post(
        "/api/imports/customers/preview",
        content=b"x" * (MAX_IMPORT_BODY_BYTES + 1),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert too_large.status_code == 413
