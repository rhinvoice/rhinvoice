"""Writing off invoices over the API."""

from datetime import timedelta

from fastapi.testclient import TestClient

from rhinvoice.domain.shared.clock import FixedClock
from tests.api.test_documents_api import LINES, create, post


def issued(client: TestClient, customer_id: str) -> str:
    draft = create(client, customer_id, lines=[LINES[0]])
    path = f"/api/documents/{draft['id']}"
    post(client, f"{path}/issue")
    return path


def test_endpoints_require_login(client: TestClient) -> None:
    unknown = "/api/documents/00000000-0000-0000-0000-000000000000/write-off"
    assert client.post(unknown, json={}).status_code == 401
    assert client.delete(unknown).status_code == 401
    assert client.get("/api/bad-debts").status_code == 401


def test_write_off_and_later_payment(
    user_client: TestClient, customer_id: str, clock: FixedClock
) -> None:
    path = issued(user_client, customer_id)
    open_invoice = user_client.get(path).json()
    assert open_invoice["write_off"] is None
    assert open_invoice["written_off_amount"] == "0.00"
    post(user_client, f"{path}/payments", {"paid_on": "2026-01-15", "amount": "621.50"})

    lost = post(
        user_client,
        f"{path}/write-off",
        {"written_off_on": "2026-01-15", "reason": "gone", "note": " Konkurs "},
    )
    assert lost["status"] == "written_off"
    assert lost["display_status"] == "written_off"
    assert lost["open_amount"] == "0.00"
    assert lost["paid_amount"] == "621.50"
    assert lost["written_off_amount"] == "1000.00"
    write_off = lost["write_off"]
    assert (
        write_off["written_off_on"],
        write_off["amount"],
        write_off["tax"],
        write_off["reason"],
        write_off["note"],
    ) == ("2026-01-15", "1000.00", "74.93", "gone", "Konkurs")
    assert lost["events"][-1]["kind"] == "written_off"
    assert lost["events"][-1]["detail"] == "1000.00 2026-01-15 gone"
    assert [payment["after_write_off"] for payment in lost["payments"]] == [False]

    # Neither reminded nor cancelled nor written off twice.
    assert user_client.post(f"{path}/cancel").status_code == 409
    again = user_client.post(
        f"{path}/write-off", json={"written_off_on": "2026-01-15", "reason": "other"}
    )
    assert again.status_code == 409
    before = user_client.delete(f"{path}/payments/{lost['payments'][0]['id']}")
    assert before.status_code == 409
    assert before.json()["error"]["code"] == "payment_before_write_off"

    page = user_client.get(
        "/api/documents", params={"type": "invoice", "status": "written_off"}
    ).json()
    assert [(item["display_status"], item["open_amount"]) for item in page["items"]] == [
        ("written_off", "0.00")
    ]
    assert {"status": "written_off", "count": 1} in page["status_counts"]

    # A payment counts as recovered when it is recorded after the write-off.
    clock.set(clock.now() + timedelta(minutes=1))
    partly = post(user_client, f"{path}/payments", {"paid_on": "2026-01-15", "amount": "400"})
    assert partly["status"] == "written_off"
    assert partly["written_off_amount"] == "600.00"
    assert partly["write_off"]["amount"] == "1000.00"
    assert [payment["after_write_off"] for payment in partly["payments"]] == [False, True]
    too_much = user_client.post(
        f"{path}/payments", json={"paid_on": "2026-01-15", "amount": "600.01"}
    )
    assert too_much.status_code == 422

    years = user_client.get("/api/bad-debts").json()
    assert years == [
        {
            "year": 2026,
            "currency": "CHF",
            "written_off": "1000.00",
            "recovered": "400.00",
            "loss": "600.00",
            "net": "555.04",
            "tax": "44.96",
        },
    ]

    whole = post(user_client, f"{path}/payments", {"paid_on": "2026-01-15", "amount": "600"})
    assert whole["status"] == "paid"
    assert whole["written_off_amount"] == "0.00"
    assert whole["write_off"] is not None


def test_taking_a_write_off_back(user_client: TestClient, customer_id: str) -> None:
    path = issued(user_client, customer_id)
    assert user_client.delete(f"{path}/write-off").status_code == 409
    post(user_client, f"{path}/write-off", {"written_off_on": "2026-01-15", "reason": "other"})
    reopened = user_client.delete(f"{path}/write-off")
    assert reopened.status_code == 200, reopened.text
    body = reopened.json()
    assert body["status"] == "issued"
    assert body["write_off"] is None
    assert body["open_amount"] == "1621.50"
    assert body["events"][-1]["kind"] == "write_off_removed"
    assert user_client.get("/api/bad-debts").json() == []


def test_write_off_validation(user_client: TestClient, customer_id: str) -> None:
    path = issued(user_client, customer_id)
    future = user_client.post(
        f"{path}/write-off", json={"written_off_on": "2026-01-16", "reason": "gone"}
    )
    assert future.status_code == 422
    assert future.json()["error"]["code"] == "write_off_date_in_future"
    early = user_client.post(
        f"{path}/write-off", json={"written_off_on": "2026-01-14", "reason": "gone"}
    )
    assert early.status_code == 422
    assert early.json()["error"]["code"] == "write_off_before_invoice"
    assert list(early.json()["error"]["details"]) == ["written_off_on"]
    unknown_reason = user_client.post(
        f"{path}/write-off", json={"written_off_on": "2026-01-15", "reason": "bored"}
    )
    assert unknown_reason.status_code == 422
    unknown = "/api/documents/00000000-0000-0000-0000-000000000000/write-off"
    assert (
        user_client.post(
            unknown, json={"written_off_on": "2026-01-15", "reason": "gone"}
        ).status_code
        == 404
    )
    assert user_client.delete(unknown).status_code == 404
    draft = create(user_client, customer_id)
    refused = user_client.post(
        f"/api/documents/{draft['id']}/write-off",
        json={"written_off_on": "2026-01-15", "reason": "gone"},
    )
    assert refused.status_code == 409
