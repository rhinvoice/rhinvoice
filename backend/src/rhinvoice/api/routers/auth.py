from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import Field

from rhinvoice.api.dependencies import (
    NOT_IN_DEMO,
    SESSION_COOKIE,
    ContainerDep,
    CurrentUser,
    SessionToken,
    get_current_user,
)
from rhinvoice.api.schemas import ERROR_RESPONSES, NOT_BLANK_PATTERN, ApiModel
from rhinvoice.application.identity.handlers import (
    ChangePassword,
    CreateUser,
    DisableTotp,
    Login,
)
from rhinvoice.domain.identity.session import ABSOLUTE_TIMEOUT
from rhinvoice.domain.identity.user import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from rhinvoice.domain.shared.email import EMAIL_PATTERN

if TYPE_CHECKING:
    from rhinvoice.domain.identity.user import User


router = APIRouter(prefix="/api/auth", tags=["auth"], responses=ERROR_RESPONSES)


class LoginRequest(ApiModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)
    totp_code: str | None = Field(default=None, max_length=10)


class SetupRequest(ApiModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    display_name: str = Field(max_length=200, pattern=NOT_BLANK_PATTERN)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class UserResponse(ApiModel):
    id: UUID
    email: str
    display_name: str
    totp_enabled: bool

    @classmethod
    def of(cls, user: User) -> UserResponse:
        return cls(
            id=user.id,
            email=str(user.email),
            display_name=user.display_name,
            totp_enabled=user.totp_enabled,
        )


class SetupStatus(ApiModel):
    needs_setup: bool


class ChangePasswordRequest(ApiModel):
    current_password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class TotpSetupResponse(ApiModel):
    secret: str
    provisioning_uri: str


class TotpCodeRequest(ApiModel):
    code: str = Field(max_length=10)


class DisableTotpRequest(ApiModel):
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    code: str = Field(max_length=10)


def _set_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ABSOLUTE_TIMEOUT.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


@router.get("/setup")
def setup_status(container: ContainerDep) -> SetupStatus:
    """Tell the frontend whether the first user still has to be created."""
    # A public demo has its login; it never asks visitors to set one up.
    needs_setup = not container.settings.demo and not container.identity.has_users()
    return SetupStatus(needs_setup=needs_setup)


@router.post("/setup", status_code=status.HTTP_201_CREATED, dependencies=[NOT_IN_DEMO])
def setup(body: SetupRequest, container: ContainerDep, response: Response) -> UserResponse:
    """Create the first user. Only possible while no user exists."""
    identity = container.identity
    user = identity.create_first_user(
        CreateUser(email=body.email, display_name=body.display_name, password=body.password),
    )
    result = identity.login(Login(email=body.email, password=body.password))
    _set_session_cookie(response, result.token, secure=container.settings.cookie_secure)
    return UserResponse.of(user)


@router.post("/login")
def login(body: LoginRequest, container: ContainerDep, response: Response) -> UserResponse:
    result = container.identity.login(
        Login(email=body.email, password=body.password, totp_code=body.totp_code),
    )
    _set_session_cookie(response, result.token, secure=container.settings.cookie_secure)
    return UserResponse.of(result.user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_user)],
)
def logout(container: ContainerDep, token: SessionToken, response: Response) -> None:
    container.identity.logout(token)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.of(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, dependencies=[NOT_IN_DEMO])
def change_password(
    body: ChangePasswordRequest,
    user: CurrentUser,
    token: SessionToken,
    container: ContainerDep,
) -> None:
    container.identity.change_password(
        ChangePassword(
            user_id=user.id,
            current_password=body.current_password,
            new_password=body.new_password,
            current_token=token,
        ),
    )


@router.post("/totp/setup", dependencies=[NOT_IN_DEMO])
def totp_setup(user: CurrentUser, container: ContainerDep) -> TotpSetupResponse:
    setup_result = container.identity.begin_totp_setup(user.id)
    return TotpSetupResponse(
        secret=setup_result.secret,
        provisioning_uri=setup_result.provisioning_uri,
    )


@router.post("/totp/confirm", dependencies=[NOT_IN_DEMO])
def totp_confirm(body: TotpCodeRequest, user: CurrentUser, container: ContainerDep) -> UserResponse:
    return UserResponse.of(container.identity.confirm_totp(user.id, body.code))


@router.post("/totp/disable", dependencies=[NOT_IN_DEMO])
def totp_disable(
    body: DisableTotpRequest,
    user: CurrentUser,
    container: ContainerDep,
) -> UserResponse:
    command = DisableTotp(user_id=user.id, password=body.password, code=body.code)
    return UserResponse.of(container.identity.disable_totp(command))
