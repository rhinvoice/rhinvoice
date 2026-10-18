"""Bodies without a length, other sites on 127.0.0.1 and sign-in floods (ADR 0034)."""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from rhinvoice.api.middleware import (
    MAX_BODY_BYTES,
    MAX_FILE_BODY_BYTES,
    BodyLimitMiddleware,
    BodyTooLargeError,
)
from rhinvoice.api.routers.documents import file_disposition
from tests.api.conftest import CLIENT_HEADERS, EMAIL, AppFactory

CHUNK = b"x" * (1024 * 1024)
DOCUMENT = "00000000-0000-0000-0000-000000000001"


def chunks(size: int, start: bytes = b"") -> Iterator[bytes]:
    """Send a body in chunks: it declares no Content-Length."""
    yield start
    sent = len(start)
    while sent < size:
        part = CHUNK[: size - sent]
        sent += len(part)
        yield part


def test_a_chunked_body_is_counted_and_refused_past_its_limit(client: TestClient) -> None:
    response = client.post(
        "/api/customers",
        content=chunks(MAX_BODY_BYTES + 1, b'{"name": "'),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_large"
    # The answer passes the security middleware like any other.
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_a_chunked_upload_is_refused_before_the_login_is_checked(client: TestClient) -> None:
    boundary = "rhinvoice-boundary"
    start = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="a.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    response = client.post(
        f"/api/documents/{DOCUMENT}/files",
        content=chunks(MAX_FILE_BODY_BYTES + 1, start),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_large"


def test_a_chunked_body_within_its_limit_is_read(client: TestClient) -> None:
    body = b'{"email": "anna@example.com", "password": "not the right one"}'
    response = client.post(
        "/api/auth/login",
        content=iter([body[:10], body[10:]]),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401


async def _reading(scope: Scope, receive: Receive, send: Send) -> None:
    """Read the whole body and let the refusal pass up."""
    del scope, send
    while (await receive()).get("more_body", False):
        pass


async def _answering_first(scope: Scope, receive: Receive, send: Send) -> None:
    """Start the answer before reading the body."""
    del scope
    await send({"type": "http.response.start", "status": 200, "headers": []})
    try:
        await _reading({}, receive, send)
    except BodyTooLargeError:
        await send({"type": "http.response.body", "body": b"late"})


async def _failing(scope: Scope, receive: Receive, send: Send) -> None:
    del scope, receive, send
    msg = "a bug of the app"
    raise RuntimeError(msg)


async def _call(app: BodyLimitMiddleware, body: bytes) -> list[Message]:
    sent: list[Message] = []
    parts = [body[: len(body) // 2], body[len(body) // 2 :]]

    async def receive() -> Message:
        part = parts.pop(0)
        return {"type": "http.request", "body": part, "more_body": bool(parts)}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "path": "/api/customers", "method": "POST", "headers": []}
    await app(scope, receive, send)
    return sent


def test_the_body_limit_answers_413_when_the_app_lets_the_refusal_pass() -> None:
    sent = asyncio.run(_call(BodyLimitMiddleware(_reading), b"x" * (MAX_BODY_BYTES + 1)))
    assert sent[0]["status"] == 413


def test_the_body_limit_keeps_quiet_after_the_app_has_answered() -> None:
    sent = asyncio.run(_call(BodyLimitMiddleware(_answering_first), b"x" * (MAX_BODY_BYTES + 1)))
    # Only the start the app sent before; nothing after the refusal, no second answer.
    assert [message["type"] for message in sent] == ["http.response.start"]


def test_the_body_limit_passes_other_errors_on() -> None:
    with pytest.raises(RuntimeError, match="a bug of the app"):
        asyncio.run(_call(BodyLimitMiddleware(_failing), b"{}"))


def test_an_app_that_caught_the_refusal_gets_no_more_body() -> None:
    caught: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await _reading(scope, receive, send)
        except BodyTooLargeError:
            caught.append("first")
        with pytest.raises(BodyTooLargeError):
            await receive()
        caught.append("again")

    sent = asyncio.run(_call(BodyLimitMiddleware(app), b"x" * (MAX_BODY_BYTES + 1)))
    assert caught == ["first", "again"]
    assert sent[0]["status"] == 413


def test_the_body_limit_passes_other_messages_on() -> None:
    received: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, send
        received.append(await receive())

    async def disconnect() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        del message

    scope: Scope = {"type": "http", "path": "/api/customers", "method": "POST", "headers": []}
    asyncio.run(BodyLimitMiddleware(app)(scope, disconnect, send))
    assert received == [{"type": "http.disconnect"}]


LOCAL = "http://127.0.0.1:8123"


@pytest.fixture
def local_app(app_factory: AppFactory) -> FastAPI:
    return app_factory(local_port=8123)


@pytest.mark.parametrize("base_url", [LOCAL, "http://localhost:8123", "http://LOCALHOST:8123"])
def test_the_desktop_server_answers_its_own_address(local_app: FastAPI, base_url: str) -> None:
    with TestClient(local_app, base_url=base_url) as client:
        assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize(
    "base_url", ["http://rebound.example:8123", "http://127.0.0.1:8124", "http://10.0.0.5:8123"]
)
def test_the_desktop_server_refuses_other_addresses(local_app: FastAPI, base_url: str) -> None:
    with TestClient(local_app, base_url=base_url) as client:
        response = client.get("/api/health")
    assert response.status_code == 421
    assert response.json()["error"]["code"] == "host_rejected"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_the_desktop_server_refuses_changes_from_other_sites(local_app: FastAPI) -> None:
    with TestClient(local_app, base_url=LOCAL, headers=CLIENT_HEADERS) as client:
        wrong = {"email": EMAIL, "password": "x" * 12}
        foreign = client.post(
            "/api/auth/login", json=wrong, headers={"Origin": "http://rebound.example:8123"}
        )
        assert foreign.status_code == 403
        assert foreign.json()["error"]["code"] == "origin_rejected"
        # Its own pages, and programs that send no Origin, get through.
        own = client.post("/api/auth/login", json=wrong, headers={"Origin": LOCAL})
        assert own.status_code == 401
        assert client.post("/api/auth/login", json=wrong).status_code == 401
        # Reading needs no Origin check: the Host check already keeps other sites out.
        read = client.get("/api/health", headers={"Origin": "http://rebound.example:8123"})
        assert read.status_code == 200


def test_a_server_answers_any_address(client: TestClient) -> None:
    """With Docker the reverse proxy decides which names reach Rhinvoice."""
    response = client.get("/api/health", headers={"Host": "invoices.example.org"})
    assert response.status_code == 200


def test_every_installation_slows_down_sign_in_floods(client: TestClient) -> None:
    wrong = {"email": EMAIL, "password": "x" * 12}
    statuses = [client.post("/api/auth/login", json=wrong).status_code for _ in range(11)]
    assert statuses == [401] * 10 + [429]
    assert client.post("/api/auth/password-reset").status_code == 429
    reset = {"email": EMAIL, "code": "123456", "new_password": "y" * 12}
    assert client.post("/api/auth/password-reset/confirm", json=reset).status_code == 429
    change = {"current_password": "x" * 12, "new_password": "y" * 12}
    assert client.post("/api/auth/password", json=change).status_code == 429
    # Other changes are not limited outside the public demo.
    others = {client.post("/api/auth/logout").status_code for _ in range(70)}
    assert others == {401}


def test_password_resets_count_as_sign_ins(client: TestClient) -> None:
    reset = {"email": EMAIL, "code": "123456", "new_password": "y" * 12}
    statuses = [
        client.post("/api/auth/password-reset/confirm", json=reset).status_code for _ in range(11)
    ]
    assert statuses[-1] == 429
    assert 429 not in statuses[:-1]


def test_attachment_names_lose_their_control_characters() -> None:
    disposition = file_disposition('Scans/a\r\nSet-Cookie: x\x00\x7f"\\ü.pdf', download=True)
    assert disposition == (
        'attachment; filename="aSet-Cookie: x___.pdf"; '
        "filename*=UTF-8''aSet-Cookie%3A%20x%22%5C%C3%BC.pdf"
    )
    assert file_disposition("Scan.pdf", download=False) == (
        "inline; filename=\"Scan.pdf\"; filename*=UTF-8''Scan.pdf"
    )
