"""Requests repeated with the same Idempotency-Key run once (ADR 0041).

The web client sends a key with each request that changes something; the key belongs to one
intent, such as an opened form, and is renewed after a success. A repeat of the same request
with it, e.g. after its response was lost on the way, gets the stored response instead of
creating, paying or sending a second time. Requests without a key, or without a signed-in
user, are left as they are.
"""

from __future__ import annotations

from http import HTTPStatus
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING
from uuid import UUID

from starlette import status
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import Response

from rhinvoice.api.dependencies import SESSION_COOKIE
from rhinvoice.api.errors import error_response
from rhinvoice.domain.idempotency.request import MAX_STORED_BODY, Fingerprint, Verdict

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from rhinvoice.api.container import Container
    from rhinvoice.application.idempotency.handlers import Repeat

KEY_HEADER = "idempotency-key"
REPLAYED_HEADER = "Idempotent-Replayed"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MAX_FINGERPRINTED_BODY = 25 * 1024 * 1024
"""Bodies are kept until the request has run; larger ones (the invoice import of up to 200 MB,
which skips the numbers it has already) are left as they are."""
SPOOL_IN_MEMORY = 1024 * 1024
"""A body kept beyond this size goes to a temporary file, as Starlette keeps uploads."""
CHUNK = 64 * 1024
EXCLUDED_PATHS = ("/api/auth/", "/api/backup/setup", "/api/backup/key", "/api/mail/server")
"""Requests that carry passwords, codes or keys, or answer with them: neither a fingerprint of
their body nor their answer is stored."""
JSON = "application/json"

_REFUSALS: dict[Verdict, tuple[int, str, str]] = {
    Verdict.IN_PROGRESS: (
        status.HTTP_409_CONFLICT,
        "request_in_progress",
        "the first request with this key still runs",
    ),
    Verdict.UNFINISHED: (
        status.HTTP_409_CONFLICT,
        "request_unfinished",
        "it is unclear whether the first request with this key went through",
    ),
    Verdict.DONE: (
        status.HTTP_409_CONFLICT,
        "request_done",
        "a request with this key went through already",
    ),
    Verdict.REUSED: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "idempotency_key_reused",
        "this key belongs to another request",
    ),
}


class IdempotencyMiddleware:
    """Run each request with an Idempotency-Key once; answer its repeats from the first.

    Inside BodyLimitMiddleware: the body is counted before it is held here.
    """

    def __init__(self, app: ASGIApp, *, container: Container) -> None:
        self._app = app
        self._container = container

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        raw_key = headers.get(KEY_HEADER)
        if (
            raw_key is None
            or scope["method"] in SAFE_METHODS
            or not scope["path"].startswith("/api/")
            or scope["path"].startswith(EXCLUDED_PATHS)
            or not _fits(headers)
        ):
            await self._app(scope, receive, send)
            return
        try:
            key = UUID(raw_key)
        except ValueError:
            await error_response(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "invalid_idempotency_key",
                "the Idempotency-Key must be a UUID",
            )(scope, receive, send)
            return
        token = HTTPConnection(scope).cookies.get(SESSION_COOKIE)
        user = (
            None
            if not token
            else await run_in_threadpool(self._container.identity.authenticate, token)
        )
        if user is None:
            # The route answers that nobody is signed in; nothing to remember.
            await self._app(scope, receive, send)
            return
        query = scope.get("query_string", b"").decode("latin-1")
        request = Fingerprint(scope["method"], scope["path"], query)
        with SpooledTemporaryFile(max_size=SPOOL_IN_MEMORY) as body:
            if not await _keep(receive, body, request):
                # The client left before its request was whole: nothing runs, as without a key.
                return
            handlers = self._container.idempotency
            repeat = await run_in_threadpool(handlers.begin, user.id, key, request.hexdigest())
            if repeat is not None:
                await _answer(repeat)(scope, receive, send)
                return
            answer = _Answer(send)
            try:
                await self._app(scope, _replay(body, receive), answer.send)
            except BaseException:
                await run_in_threadpool(self._finish, user.id, key, answer)
                raise
            await run_in_threadpool(self._finish, user.id, key, answer)

    def _finish(self, user_id: UUID, key: UUID, answer: _Answer) -> None:
        handlers = self._container.idempotency
        if answer.succeeded:
            handlers.succeed(user_id, key, answer.status_code, answer.kept())
        else:
            # Not done, or not known to be done: the request may run again with this key.
            handlers.fail(user_id, key)


def _fits(headers: Headers) -> bool:
    """Whether the body may be held to identify the request (its size is declared)."""
    try:
        size = int(headers.get("content-length", "0"))
    except ValueError:
        return False
    return size <= MAX_FINGERPRINTED_BODY and (
        "content-length" in headers or "transfer-encoding" not in headers
    )


async def _keep(receive: Receive, body: SpooledTemporaryFile[bytes], request: Fingerprint) -> bool:
    """Keep the body for the app and add it to the fingerprint; False when it stays incomplete."""
    while True:
        message = await receive()
        if message["type"] != "http.request":
            return False
        chunk = message.get("body", b"")
        request.update(chunk)
        await run_in_threadpool(body.write, chunk)
        if not message.get("more_body", False):
            body.seek(0)
            return True


def _replay(body: SpooledTemporaryFile[bytes], receive: Receive) -> Receive:
    """Hand the app the body kept, then whatever comes after it (a disconnect)."""
    done = False

    async def replayed() -> Message:
        nonlocal done
        if done:
            return await receive()
        chunk = await run_in_threadpool(body.read, CHUNK)
        # A last chunk of exactly CHUNK bytes is followed by an empty one.
        done = len(chunk) < CHUNK
        return {"type": "http.request", "body": chunk, "more_body": not done}

    return replayed


def _answer(repeat: Repeat) -> Response:
    if repeat.verdict is Verdict.REPLAY:
        stored = repeat.stored
        return Response(
            content=stored.body,
            status_code=stored.status_code or HTTPStatus.OK,
            media_type=JSON,
            headers={REPLAYED_HEADER: "true"},
        )
    status_code, code, message = _REFUSALS[repeat.verdict]
    return error_response(status_code, code, message)


class _Answer:
    """The app's answer on its way out, kept when it is JSON and small enough."""

    def __init__(self, send: Send) -> None:
        self._send = send
        self.status_code = 0
        self._json = False
        self._chunks: list[bytes] = []
        self._size = 0
        self._complete = False

    @property
    def succeeded(self) -> bool:
        """A success whose answer was given in full (also when the client had gone by then)."""
        return HTTPStatus.OK <= self.status_code < HTTPStatus.MULTIPLE_CHOICES and self._complete

    def kept(self) -> bytes | None:
        if not self._json or self._size > MAX_STORED_BODY:
            return None
        return b"".join(self._chunks)

    async def send(self, message: Message) -> None:
        # Recorded before it is sent: a client that has gone does not lose the answer.
        if message["type"] == "http.response.start":
            self.status_code = message["status"]
            content_type = Headers(raw=message.get("headers", [])).get("content-type", "")
            self._json = content_type.split(";")[0].strip().lower() == JSON
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            self._size += len(chunk)
            if self._json and self._size <= MAX_STORED_BODY:
                self._chunks.append(chunk)
            if not message.get("more_body", False):
                self._complete = True
        await self._send(message)
