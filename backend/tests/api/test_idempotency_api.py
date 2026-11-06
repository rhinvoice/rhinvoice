"""A request repeated with the same Idempotency-Key runs once (ADR 0041)."""

import json
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from rhinvoice.api.container import Container
from rhinvoice.domain.idempotency.request import UNFINISHED_AFTER, fingerprint
from rhinvoice.domain.shared.clock import FixedClock
from tests.api.conftest import NOW
from tests.api.test_masterdata_api import ADDRESS

CUSTOMER = {"kind": "company", "company_name": "Beispiel AG", "address": ADDRESS}
BODY = json.dumps(CUSTOMER).encode()
JSON_HEADERS = {"content-type": "application/json"}


def customers(client: TestClient) -> int:
    total: int = client.get("/api/customers").json()["total"]
    return total


def user_id(client: TestClient) -> UUID:
    return UUID(client.get("/api/auth/me").json()["id"])


def test_a_repeat_gets_the_first_answer_and_creates_nothing(user_client: TestClient) -> None:
    key = str(uuid4())
    first = user_client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": key}
    )
    assert first.status_code == 201, first.text
    assert "Idempotent-Replayed" not in first.headers
    repeat = user_client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": key}
    )
    assert repeat.status_code == 201
    assert repeat.headers["Idempotent-Replayed"] == "true"
    assert repeat.headers["content-type"] == "application/json"
    assert repeat.json() == first.json()
    assert customers(user_client) == 1
    # A new intent has a new key: it runs.
    other = user_client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": str(uuid4())}
    )
    assert other.status_code == 201
    assert customers(user_client) == 2


def test_without_a_key_every_request_runs(user_client: TestClient) -> None:
    for _ in range(2):
        assert user_client.post("/api/customers", json=CUSTOMER).status_code == 201
    assert customers(user_client) == 2


def test_the_key_of_another_request_is_refused(user_client: TestClient) -> None:
    key = str(uuid4())
    first = user_client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": key}
    )
    assert first.status_code == 201
    other = json.dumps({**CUSTOMER, "company_name": "Andere AG"}).encode()
    refused = user_client.post(
        "/api/customers", content=other, headers={**JSON_HEADERS, "Idempotency-Key": key}
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "idempotency_key_reused"
    assert customers(user_client) == 1


def test_a_failed_request_frees_its_key_for_the_corrected_one(user_client: TestClient) -> None:
    key = str(uuid4())
    wrong = json.dumps({**CUSTOMER, "company_name": ""}).encode()
    failed = user_client.post(
        "/api/customers", content=wrong, headers={**JSON_HEADERS, "Idempotency-Key": key}
    )
    assert failed.status_code == 422
    corrected = user_client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": key}
    )
    assert corrected.status_code == 201
    assert customers(user_client) == 1


def test_a_repeat_while_the_first_runs_waits_and_one_cut_off_is_not_guessed(
    user_client: TestClient, container: Container, clock: FixedClock
) -> None:
    key = uuid4()
    # The first request is still running: its key is claimed, its answer not given yet.
    request = fingerprint("POST", "/api/customers", "", BODY)
    assert container.idempotency.begin(user_id(user_client), key, request) is None
    running = user_client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": str(key)}
    )
    assert running.status_code == 409
    assert running.json()["error"]["code"] == "request_in_progress"
    clock.set(NOW + UNFINISHED_AFTER)
    unclear = user_client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": str(key)}
    )
    assert unclear.status_code == 409
    assert unclear.json()["error"]["code"] == "request_unfinished"
    assert customers(user_client) == 0


def test_an_answer_that_is_not_kept_is_not_given_twice(
    user_client: TestClient, customer_id: str
) -> None:
    key = str(uuid4())
    draft = json.dumps(
        {
            "type": "invoice",
            "customer_id": customer_id,
            "lines": [{"description": "Beratung", "quantity": "1", "unit_price": "100"}],
        }
    ).encode()
    headers = {**JSON_HEADERS, "Idempotency-Key": key}
    page = user_client.post("/api/documents/render", content=draft, headers=headers)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    repeat = user_client.post("/api/documents/render", content=draft, headers=headers)
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "request_done"


def test_a_key_must_be_a_uuid(user_client: TestClient) -> None:
    refused = user_client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": "nochmals"}
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "invalid_idempotency_key"
    assert customers(user_client) == 0


def test_requests_that_change_nothing_or_have_no_user_are_left_alone(
    client: TestClient, user_client: TestClient
) -> None:
    key = str(uuid4())
    for _ in range(2):
        listed = user_client.get("/api/customers", headers={"Idempotency-Key": key})
        assert listed.status_code == 200
        assert "Idempotent-Replayed" not in listed.headers
    client.cookies.clear()
    anonymous = client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": key}
    )
    assert anonymous.status_code == 401
    client.cookies.set("rhinvoice_session", "ended")
    expired = client.post(
        "/api/customers", content=BODY, headers={**JSON_HEADERS, "Idempotency-Key": key}
    )
    assert expired.status_code == 401
