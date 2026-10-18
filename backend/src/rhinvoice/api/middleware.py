"""Security related middleware.

CSRF: the session cookie is ``SameSite=Strict`` and every state changing
request must carry the ``X-Rhinvoice-Client`` header. Browsers do not allow
cross-site requests with custom headers without a CORS preflight, which this
API never grants (OWASP "custom request header" defence, see ADR 0003).

The installation without Docker answers only requests addressed to itself on 127.0.0.1
(DNS rebinding); request bodies are counted as they arrive, also without a
Content-Length (ADR 0034).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette import status
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

from rhinvoice.api.errors import error_response

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from rhinvoice.api.rate_limit import ClientLimits

CLIENT_HEADER = "x-rhinvoice-client"
MAX_BODY_BYTES = 2 * 1024 * 1024
"""Largest accepted request body (the logo upload is limited to 1 MB)."""
MAX_IMPORT_BODY_BYTES = 6 * 1024 * 1024
"""Import files may have 5 MB, plus the form around them."""
MAX_INVOICE_IMPORT_BODY_BYTES = 210 * 1024 * 1024
"""Invoices come with their PDF files: 200 MB, plus the list and the form."""
MAX_FILE_BODY_BYTES = 21 * 1024 * 1024
"""A PDF added to an imported invoice: 20 MB, plus the form."""
IMPORT_PATH = "/api/imports/"
DOCUMENTS_PATH = "/api/documents/"
FILES_SUFFIX = "/files"
INVOICE_IMPORT_PATH = "/api/imports/invoices"
MULTIPART = "multipart/form-data"
HEALTH_PATH = "/api/health"
LOGIN_PATH = "/api/auth/login"
SIGN_IN_PATHS = frozenset({LOGIN_PATH, "/api/auth/password"})
"""Requests that try a password: the login and the change of one's own password."""
PASSWORD_RESET_PATH = "/api/auth/password-reset"  # noqa: S105 - a path, no password
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; frame-src 'self' blob:; object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        demo: bool = False,
        resetting: Callable[[], bool] = lambda: False,
        limits: ClientLimits | None = None,
        local_port: int | None = None,
    ) -> None:
        super().__init__(app)
        self._demo = demo
        self._resetting = resetting
        self._limits = limits
        self._local = None if local_port is None else _LocalAddresses(local_port)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response
        if self._local is not None and not self._local.host_allowed(request):
            # A page of another site whose name now points at 127.0.0.1 (DNS rebinding).
            response = error_response(
                status.HTTP_421_MISDIRECTED_REQUEST,
                "host_rejected",
                "this server only answers requests to its own address",
            )
        elif self._local is not None and not self._local.origin_allowed(request):
            response = error_response(
                status.HTTP_403_FORBIDDEN,
                "origin_rejected",
                "requests from other sites are not accepted",
            )
        elif (
            request.url.path.startswith("/api/")
            and request.url.path != HEALTH_PATH
            and (self._resetting())
        ):
            # A public demo is being emptied and filled again: nobody gets in half way.
            response = error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "demo_resetting",
                "the demo is being reset, please try again in a minute",
                headers={"Retry-After": "60"},
            )
        elif self._limited(request):
            response = error_response(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "rate_limited",
                "too many requests, please slow down",
                headers={"Retry-After": "60"},
            )
        elif (
            request.url.path.startswith("/api/")
            and request.method not in SAFE_METHODS
            and not request.headers.get(CLIENT_HEADER)
        ):
            response = error_response(
                status.HTTP_403_FORBIDDEN,
                "csrf_rejected",
                f"missing {CLIENT_HEADER} header",
            )
        elif _declared_size(request) > body_limit(
            request.url.path, request.headers.get("content-type", ""), demo=self._demo
        ):
            response = _too_large()
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if self._demo:
            # A public demo is shared and reset every hour: not for search engines.
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def _limited(self, request: Request) -> bool:
        """Whether a client sent too many sign-ins, or too many changes to the public demo.

        The client is the address uvicorn reports: the proxy's own unless the proxy is
        trusted with ``--forwarded-allow-ips`` (``RHINVOICE_FORWARDED_ALLOW_IPS``).
        """
        path = request.url.path
        if self._limits is None or request.method in SAFE_METHODS or not path.startswith("/api/"):
            return False
        client = request.client.host if request.client is not None else "unknown"
        signs_in = path in SIGN_IN_PATHS or path.startswith(PASSWORD_RESET_PATH)
        if signs_in and not self._limits.logins.allow(client):
            return True
        changes = self._limits.changes
        return changes is not None and not changes.allow(client)


class _LocalAddresses:
    """The addresses of a server on 127.0.0.1 (the installation without Docker)."""

    def __init__(self, port: int) -> None:
        self._hosts = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})
        self._origins = frozenset(f"http://{host}" for host in self._hosts)

    def host_allowed(self, request: Request) -> bool:
        return request.headers.get("host", "").lower() in self._hosts

    def origin_allowed(self, request: Request) -> bool:
        """Let changes come without an Origin (not from a browser), never from another one."""
        origin = request.headers.get("origin")
        return request.method in SAFE_METHODS or origin is None or origin.lower() in self._origins


class BodyTooLargeError(Exception):
    """The request body grew beyond its limit while it arrived."""


class BodyLimitMiddleware:
    """Count the bytes of each request body as they arrive; refuse it past its limit.

    SecurityMiddleware refuses a body whose Content-Length is too large before it is read.
    A body sent in chunks declares no length: only counting stops it before it fills the
    memory (anonymous requests too, since the body is read before the login is checked).
    """

    def __init__(self, app: ASGIApp, *, demo: bool = False) -> None:
        self._app = app
        self._demo = demo

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        content_type = Headers(scope=scope).get("content-type", "")
        limit = body_limit(scope["path"], content_type, demo=self._demo)
        body = _CountedBody(receive, limit)
        try:
            await self._app(scope, body.receive, body.send_to(send))
        except Exception:
            # Whatever the app made of the refused body; the answer is a 413.
            if not body.exceeded:
                raise
        if body.exceeded and not body.answered:
            await _too_large()(scope, receive, send)


class _CountedBody:
    def __init__(self, receive: Receive, limit: int) -> None:
        self._receive = receive
        self._limit = limit
        self._received = 0
        self.exceeded = False
        self.answered = False
        """The app had started its answer before the body grew too large."""

    async def receive(self) -> Message:
        if self.exceeded:
            # An app that caught the refusal gets no more of the body either.
            raise BodyTooLargeError
        message = await self._receive()
        if message["type"] == "http.request":
            self._received += len(message.get("body", b""))
            if self._received > self._limit:
                self.exceeded = True
                raise BodyTooLargeError
        return message

    def send_to(self, send: Send) -> Send:
        async def guarded(message: Message) -> None:
            if self.exceeded:
                # The app's answer to a body it never got whole; ours follows.
                return
            self.answered = True
            await send(message)

        return guarded


def _too_large() -> Response:
    return error_response(
        status.HTTP_413_CONTENT_TOO_LARGE,
        "too_large",
        "the request is too large",
    )


def body_limit(path: str, content_type: str = "", *, demo: bool = False) -> int:
    """Return the largest body accepted for a path and content type.

    Only uploads (multipart forms, whose files go to temporary files) get the larger limits;
    any other body on those paths would be held in memory as a whole.
    """
    if demo or not content_type.lower().startswith(MULTIPART):
        # A public demo takes no uploads (imports, files, logo): it never reads large bodies.
        return MAX_BODY_BYTES
    if path.startswith(INVOICE_IMPORT_PATH):
        return MAX_INVOICE_IMPORT_BODY_BYTES
    if path.startswith(DOCUMENTS_PATH) and path.endswith(FILES_SUFFIX):
        return MAX_FILE_BODY_BYTES
    return MAX_IMPORT_BODY_BYTES if path.startswith(IMPORT_PATH) else MAX_BODY_BYTES


def _declared_size(request: Request) -> int:
    """Content-Length of the request; a chunked body is counted by BodyLimitMiddleware."""
    value = request.headers.get("content-length", "0")
    return int(value) if value.isdigit() else 0
