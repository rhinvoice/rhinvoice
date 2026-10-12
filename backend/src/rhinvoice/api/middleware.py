"""Security related middleware.

CSRF: the session cookie is ``SameSite=Strict`` and every state changing
request must carry the ``X-Rhinvoice-Client`` header. Browsers do not allow
cross-site requests with custom headers without a CORS preflight, which this
API never grants (OWASP "custom request header" defence, see ADR 0003).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware

from rhinvoice.api.errors import error_response

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

    from rhinvoice.api.rate_limit import DemoLimits

CLIENT_HEADER = "x-rhinvoice-client"
MAX_BODY_BYTES = 2 * 1024 * 1024
"""Largest accepted request body (the logo upload is limited to 1 MB)."""
MAX_IMPORT_BODY_BYTES = 6 * 1024 * 1024
"""Import files may have 5 MB, plus the form around them."""
IMPORT_PATH = "/api/imports/"
HEALTH_PATH = "/api/health"
LOGIN_PATH = "/api/auth/login"
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
        noindex: bool = False,
        resetting: Callable[[], bool] = lambda: False,
        limits: DemoLimits | None = None,
    ) -> None:
        super().__init__(app)
        self._noindex = noindex
        self._resetting = resetting
        self._limits = limits

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response
        if (
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
        elif _declared_size(request) > _body_limit(request):
            response = error_response(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "too_large",
                "the request is too large",
            )
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if self._noindex:
            # A public demo is shared and reset every hour: not for search engines.
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def _limited(self, request: Request) -> bool:
        """Whether a client of the public demo sent too many changes or logins."""
        if (
            self._limits is None
            or request.method in SAFE_METHODS
            or not request.url.path.startswith("/api/")
        ):
            return False
        client = request.client.host if request.client is not None else "unknown"
        if request.url.path == LOGIN_PATH and not self._limits.logins.allow(client):
            return True
        return not self._limits.changes.allow(client)


def _body_limit(request: Request) -> int:
    return MAX_IMPORT_BODY_BYTES if request.url.path.startswith(IMPORT_PATH) else MAX_BODY_BYTES


def _declared_size(request: Request) -> int:
    """Content-Length of the request; chunked uploads are limited by the proxy."""
    value = request.headers.get("content-length", "0")
    return int(value) if value.isdigit() else 0
