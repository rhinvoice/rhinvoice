"""The edges of the Idempotency-Key middleware: answers cut off, bodies left alone (ADR 0041)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from rhinvoice.api.idempotency import CHUNK, MAX_FINGERPRINTED_BODY, IdempotencyMiddleware
from rhinvoice.domain.idempotency.request import MAX_STORED_BODY

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from rhinvoice.api.container import Container

USER = UUID(int=1)


@dataclass
class User:
    id: UUID = USER


@dataclass
class Identity:
    def authenticate(self, token: str) -> User | None:
        return User() if token == "signed-in" else None


@dataclass
class Idempotency:
    calls: list[tuple[str, object]] = field(default_factory=list[tuple[str, object]])

    def begin(self, _user_id: UUID, _key: UUID, request: str) -> None:
        self.calls.append(("begin", request))

    def succeed(self, _user_id: UUID, _key: UUID, status_code: int, body: bytes | None) -> None:
        self.calls.append(("succeed", (status_code, body)))

    def fail(self, _user_id: UUID, _key: UUID) -> None:
        self.calls.append(("fail", None))


@dataclass
class Setup:
    identity: Identity = field(default_factory=Identity)
    idempotency: Idempotency = field(default_factory=Idempotency)


def scope(*headers: tuple[bytes, bytes], path: str = "/api/customers") -> Scope:
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": [
            (b"idempotency-key", str(uuid4()).encode()),
            (b"cookie", b"rhinvoice_session=signed-in"),
            *headers,
        ],
    }


def incoming(*messages: Message) -> Receive:
    queue = list(messages)

    async def receive() -> Message:
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    return receive


async def ignore(_message: Message) -> None:
    return None


def answer(content_type: bytes, *chunks: bytes) -> list[Message]:
    start: Message = {
        "type": "http.response.start",
        "status": 201,
        "headers": [(b"content-type", content_type)],
    }
    bodies: list[Message] = [
        {"type": "http.response.body", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    return [start, *bodies]


def run(
    setup: Setup,
    app: object,
    request: Scope,
    receive: Receive | None = None,
    send: Send = ignore,
) -> None:
    middleware = IdempotencyMiddleware(cast("ASGIApp", app), container=cast("Container", setup))
    empty: Message = {"type": "http.request", "body": b"", "more_body": False}
    asyncio.run(middleware(request, receive or incoming(empty), send))


def test_bodies_whose_size_is_unknown_or_too_large_are_left_alone() -> None:
    reached: list[Scope] = []

    async def app(request: Scope, _receive: Receive, _send: Send) -> None:
        reached.append(request)

    setup = Setup()
    for headers in (
        (b"content-length", b"many"),
        (b"transfer-encoding", b"chunked"),
        (b"content-length", str(MAX_FINGERPRINTED_BODY + 1).encode()),
    ):
        run(setup, app, scope(headers))
    assert len(reached) == 3
    assert setup.idempotency.calls == []


def test_the_app_gets_the_body_once_and_then_what_follows() -> None:
    received: list[Message] = []

    async def app(_request: Scope, receive: Receive, send: Send) -> None:
        received.extend([await receive(), await receive()])
        for message in answer(b"application/json; charset=utf-8", b'{"id":', b'"1"}'):
            await send(message)

    setup = Setup()
    body = incoming(
        {"type": "http.request", "body": b'{"a":', "more_body": True},
        {"type": "http.request", "body": b"1}", "more_body": False},
    )
    run(setup, app, scope((b"content-length", b"7")), body)
    assert received == [
        {"type": "http.request", "body": b'{"a":1}', "more_body": False},
        {"type": "http.disconnect"},
    ]
    assert setup.idempotency.calls[-1] == ("succeed", (201, b'{"id":"1"}'))


def test_a_request_without_a_body_is_identified_too() -> None:
    async def app(_request: Scope, _receive: Receive, send: Send) -> None:
        for message in answer(b"application/json", b"{}"):
            await send(message)

    setup = Setup()
    run(setup, app, scope(), incoming({"type": "http.request", "body": b"", "more_body": False}))
    assert [name for name, _ in setup.idempotency.calls] == ["begin", "succeed"]


def test_a_request_whose_client_left_before_its_body_was_whole_does_not_run() -> None:
    reached: list[Scope] = []

    async def app(request: Scope, _receive: Receive, _send: Send) -> None:
        reached.append(request)

    setup = Setup()
    body = incoming(
        {"type": "http.request", "body": b'{"company_name":', "more_body": True},
        {"type": "http.disconnect"},
    )
    run(setup, app, scope(), body)
    assert reached == []
    assert setup.idempotency.calls == []


@pytest.mark.parametrize("size", [CHUNK - 1, CHUNK, 2 * CHUNK + 1])
def test_a_large_body_reaches_the_app_whole_in_parts(size: int) -> None:
    content = bytes(index % 251 for index in range(size))
    received: list[Message] = []

    async def app(_request: Scope, receive: Receive, send: Send) -> None:
        while not received or received[-1]["more_body"]:
            received.append(await receive())
        for message in answer(b"application/json", b"{}"):
            await send(message)

    setup = Setup()
    halves = [content[: size // 2], content[size // 2 :]]
    body = incoming(
        {"type": "http.request", "body": halves[0], "more_body": True},
        {"type": "http.request", "body": halves[1], "more_body": False},
    )
    run(setup, app, scope((b"content-length", str(size).encode())), body)
    assert b"".join(message["body"] for message in received) == content
    assert all(len(message["body"]) <= CHUNK for message in received)
    assert [name for name, _ in setup.idempotency.calls] == ["begin", "succeed"]


@pytest.mark.parametrize(
    "path",
    ["/api/auth/password", "/api/auth/totp/disable", "/api/backup/setup", "/api/mail/server"],
)
def test_requests_with_passwords_codes_or_keys_are_never_kept(path: str) -> None:
    reached: list[Scope] = []

    async def app(request: Scope, _receive: Receive, _send: Send) -> None:
        reached.append(request)

    setup = Setup()
    run(setup, app, scope(path=path))
    assert len(reached) == 1
    assert setup.idempotency.calls == []


def test_an_answer_given_in_full_counts_although_the_client_has_gone() -> None:
    async def app(_request: Scope, _receive: Receive, send: Send) -> None:
        for message in answer(b"application/json", b'{"id":"1"}'):
            await send(message)

    async def gone(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError

    setup = Setup()
    with pytest.raises(OSError):  # noqa: PT011 - the transport's own error
        run(setup, app, scope(), send=gone)
    assert setup.idempotency.calls[-1] == ("succeed", (201, b'{"id":"1"}'))


def test_a_request_that_breaks_off_frees_its_key() -> None:
    async def app(_request: Scope, _receive: Receive, send: Send) -> None:
        await send(answer(b"application/json", b"{}")[0])
        raise RuntimeError

    setup = Setup()
    with pytest.raises(RuntimeError):
        run(setup, app, scope())
    assert setup.idempotency.calls[-1] == ("fail", None)


def test_answers_that_are_not_json_or_too_large_are_not_kept() -> None:
    def app_answering(content_type: bytes, *chunks: bytes) -> object:
        async def app(_request: Scope, _receive: Receive, send: Send) -> None:
            for message in answer(content_type, *chunks):
                await send(message)

        return app

    setup = Setup()
    run(setup, app_answering(b"text/html", b"<p>Rechnung</p>"), scope())
    half = b"x" * (MAX_STORED_BODY // 2 + 1)
    run(setup, app_answering(b"application/json", half, half), scope())
    kept = [result for name, result in setup.idempotency.calls if name == "succeed"]
    assert kept == [(201, None), (201, None)]


def test_other_parts_of_an_answer_pass_through_untouched() -> None:
    trailers: Message = {"type": "http.response.trailers", "headers": [], "more_trailers": False}
    start, body = answer(b"application/json", b'{"id":"1"}')

    async def app(_request: Scope, _receive: Receive, send: Send) -> None:
        for message in (start, body, trailers):
            await send(message)

    sent: list[Message] = []

    async def record(message: Message) -> None:
        sent.append(message)

    setup = Setup()
    run(setup, app, scope(), send=record)
    assert sent == [start, body, trailers]
    assert setup.idempotency.calls[-1] == ("succeed", (201, b'{"id":"1"}'))
