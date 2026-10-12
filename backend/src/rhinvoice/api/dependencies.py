"""FastAPI dependencies shared by all routers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request
from fastapi.security import APIKeyCookie

from rhinvoice.application.errors import AuthenticationError, DemoLockedError

if TYPE_CHECKING:
    from rhinvoice.api.container import Container
    from rhinvoice.domain.identity.user import User

SESSION_COOKIE = "rhinvoice_session"

# Documents the cookie authentication in the OpenAPI schema; the check itself
# happens in get_session_token so that the error format stays consistent.
session_cookie = APIKeyCookie(name=SESSION_COOKIE, auto_error=False)


def get_container(request: Request) -> Container:
    return cast("Container", request.app.state.container)


def get_session_token(token: Annotated[str | None, Depends(session_cookie)]) -> str:
    if not token:
        raise AuthenticationError("not logged in")
    return token


def get_current_user(
    request: Request,
    token: Annotated[str, Depends(get_session_token)],
) -> User:
    user = get_container(request).identity.authenticate(token)
    if user is None:
        raise AuthenticationError("session expired, please log in again")
    return user


def refuse_in_demo(request: Request) -> None:
    """Refuse what would lock other visitors of a public demo out, or send mail from it."""
    if get_container(request).settings.demo:
        raise DemoLockedError("this is not possible in the public demo")


NOT_IN_DEMO = Depends(refuse_in_demo)
"""For ``dependencies=[NOT_IN_DEMO]`` on routes a public demo must not offer."""

ContainerDep = Annotated["Container", Depends(get_container)]
CurrentUser = Annotated["User", Depends(get_current_user)]
SessionToken = Annotated[str, Depends(get_session_token)]
