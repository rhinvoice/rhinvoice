"""Maps domain and application errors onto HTTP responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette import status
from starlette.exceptions import HTTPException
from starlette.routing import compile_path

from rhinvoice.api.schemas import ErrorBody, ErrorResponse
from rhinvoice.application.errors import (
    AuthenticationError,
    ConflictError,
    DeliveryError,
    DemoLockedError,
    NotFoundError,
    UnavailableError,
)
from rhinvoice.domain.shared.errors import DomainError, InvalidStateError, ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import FastAPI, Request

STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (InvalidStateError, status.HTTP_409_CONFLICT),
    (ValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (UnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (DeliveryError, status.HTTP_502_BAD_GATEWAY),
    (DemoLockedError, status.HTTP_403_FORBIDDEN),
)


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=dict(details or {})))
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


# Unique constraints that can be hit by concurrent requests although the use cases
# check them first; they become a 409 with the affected field instead of a 500.
UNIQUE_VIOLATIONS: dict[str, tuple[str, str]] = {
    "uq_customers_number": ("number", "this number is already taken"),
    "uq_articles_number": ("number", "this number is already taken"),
    "uq_users_email": ("email", "a user with this e-mail already exists"),
    "uq_documents_type_number": ("number", "this number is already taken"),
    "uq_reminders_invoice_level": (
        "level",
        "this reminder was written at the same time, please reload",
    ),
    "uq_bank_accounts_default_per_currency": (
        "is_default",
        "another default account was saved at the same time, please try again",
    ),
}


def integrity_error_response(error: IntegrityError) -> JSONResponse:
    diagnostics = getattr(error.orig, "diag", None)
    constraint = getattr(diagnostics, "constraint_name", None)
    field, message = UNIQUE_VIOLATIONS.get(
        str(constraint),
        ("", "the change conflicts with existing data, please reload and try again"),
    )
    return error_response(
        status.HTTP_409_CONFLICT,
        "conflict",
        message,
        {field: message} if field else None,
    )


def allowed_methods(request: Request) -> list[str]:
    """Collect the documented methods of *all* operations on a path.

    Starlette only reports the methods of the first matching route, which is
    wrong when GET and POST are separate routes on the same path. The OpenAPI
    schema is the contract, so it is the source of truth here.
    """
    app: FastAPI = request.app
    # The most specific templates win, like in routing: "/documents/preview" is
    # not "/documents/{document_id}" although both patterns match it.
    matches: dict[int, set[str]] = {}
    for template, operations in app.openapi()["paths"].items():
        regex, _, params = compile_path(template)
        if regex.fullmatch(request.url.path):
            matches.setdefault(len(params), set()).update(method.upper() for method in operations)
    return sorted(matches[min(matches)]) if matches else []


def status_for(error: DomainError) -> int:
    for error_type, status_code in STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return status_code
    return status.HTTP_400_BAD_REQUEST


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, error: DomainError) -> JSONResponse:
        return error_response(status_for(error), error.code, error.message, error.details)

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(_request: Request, error: IntegrityError) -> JSONResponse:
        return integrity_error_response(error)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, error: HTTPException) -> JSONResponse:
        code = "bad_request" if error.status_code == status.HTTP_400_BAD_REQUEST else "http_error"
        headers = dict(error.headers or {})
        if error.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            headers["Allow"] = ", ".join(allowed_methods(request))
        return error_response(error.status_code, code, str(error.detail), headers=headers)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        details: dict[str, str] = {}
        for item in error.errors():
            location = ".".join(str(part) for part in item["loc"] if part != "body")
            details[location or "body"] = str(item["msg"])
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "the request is invalid",
            details,
        )
