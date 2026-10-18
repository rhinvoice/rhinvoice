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
from rhinvoice.api.schemas import ERROR_RESPONSES, NOT_BLANK_PATTERN, ApiModel, ErrorResponse
from rhinvoice.application.identity.handlers import (
    ChangePassword,
    CreateUser,
    DisableTotp,
    Login,
)
from rhinvoice.application.identity.reset import ConfirmReset, ResetMethod
from rhinvoice.domain.identity.session import ABSOLUTE_TIMEOUT
from rhinvoice.domain.identity.user import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from rhinvoice.domain.shared.email import EMAIL_PATTERN
from rhinvoice.infrastructure.identity.reset_file import FILE_NAME

if TYPE_CHECKING:
    from rhinvoice.domain.identity.user import User


router = APIRouter(prefix="/api/auth", tags=["auth"], responses=ERROR_RESPONSES)
# Sign-ins and password resets per client address (api.middleware, ADR 0034).
RATE_LIMITED: dict[int | str, dict[str, object]] = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": ErrorResponse,
        "description": "Too many sign-ins or password resets from this address",
    },
}


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


class PasswordResetInfo(ApiModel):
    method: ResetMethod
    """``file``: a code in the data folder of this computer; ``administrator``: the
    command ``rhinvoice user reset-password`` on the server."""
    location: str | None
    """Where the code's file lies (``file`` only)."""


class ConfirmResetRequest(ApiModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=40)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


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


@router.post("/login", responses=RATE_LIMITED)
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


@router.get("/password-reset")
def password_reset_info(container: ContainerDep) -> PasswordResetInfo:
    """Tell the login page how a forgotten password is reset in this installation."""
    reset = container.password_reset
    folder = container.settings.reset_code_dir
    location = None if folder is None else str(folder / FILE_NAME)
    return PasswordResetInfo(method=reset.method, location=location)


@router.post(
    "/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[NOT_IN_DEMO],
    responses=RATE_LIMITED,
)
def request_password_reset(container: ContainerDep) -> None:
    """Write a new one-time code where only this computer's user reads it."""
    container.password_reset.request()


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[NOT_IN_DEMO],
    responses=RATE_LIMITED,
)
def confirm_password_reset(body: ConfirmResetRequest, container: ContainerDep) -> None:
    container.password_reset.confirm(
        ConfirmReset(email=body.email, code=body.code, new_password=body.new_password)
    )


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[NOT_IN_DEMO],
    responses=RATE_LIMITED,
)
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
