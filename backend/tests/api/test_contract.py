# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false
"""Property-based API contract test with schemathesis.

schemathesis' decorators are not fully typed; the relaxed pyright rules
below only affect this file.

Every operation in the OpenAPI schema is called with generated (valid and
invalid) data. Responses must not be server errors and must match the
documented schema, status codes and authentication rules.
"""

import os
from typing import Any

import pytest
import schemathesis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, settings
from schemathesis.generation.case import Case as GenericCase

from tests.api.conftest import CLIENT_HEADERS

COOKIE = "rhinvoice_session"
# schemathesis itself annotates cases as Case[Any].
type Case = GenericCase[Any]


def _current_token(_case: Case, context: schemathesis.AuthContext) -> str:
    app: Any = context.app
    return str(app.state.session_cookie)


@schemathesis.auth(cache_by_key=_current_token)
class SessionCookieAuth:
    """Logs in once per test and sends the session cookie with every case."""

    def get(self, case: Case, ctx: schemathesis.AuthContext) -> str:
        return _current_token(case, ctx)

    def set(self, case: Case, data: str, ctx: schemathesis.AuthContext) -> None:  # noqa: ARG002
        case.cookies = {**(case.cookies or {}), COOKIE: data}


@pytest.fixture
def api_schema(app: FastAPI, user_client: TestClient) -> schemathesis.BaseSchema:
    app.state.session_cookie = user_client.cookies.get(COOKIE)
    return schemathesis.openapi.from_asgi("/api/openapi.json", app)


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@settings(
    max_examples=int(os.environ.get("CONTRACT_MAX_EXAMPLES", "25")),
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
def test_api_contract(case: Case) -> None:
    case.call_and_validate(headers=CLIENT_HEADERS)
