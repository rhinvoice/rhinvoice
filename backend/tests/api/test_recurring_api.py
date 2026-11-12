"""Recurring invoice plans through the API."""

from datetime import timedelta
from typing import cast
from uuid import uuid4

from fastapi.testclient import TestClient

from rhinvoice.api.container import Container
from tests.api.conftest import NOW
from tests.api.test_documents_api import post

TODAY = NOW.date()


def plan_body(customer_id: str, **fields: object) -> dict[str, object]:
    return {
        "name": "Hosting",
        "customer_id": customer_id,
        "interval": "monthly",
        "start_date": str(TODAY),
        "action": "issue",
        "template": {
            "currency": "CHF",
            "lines": [
                {"description": "Hosting", "quantity": "1", "unit": "MON", "unit_price": "29"},
            ],
            "subject": "Hosting",
        },
        **fields,
    }


def with_template(body: dict[str, object], **changes: object) -> dict[str, object]:
    template = cast("dict[str, object]", body["template"])
    return {**body, "template": {**template, **changes}}


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/recurring").status_code == 401


def test_a_plan_from_creation_to_its_invoice(
    user_client: TestClient, customer_id: str, container: Container
) -> None:
    created = post(user_client, "/api/recurring", plan_body(customer_id), status=201)
    assert created["name"] == "Hosting"
    assert (created["customer_name"], created["customer_archived"]) == ("Beispiel AG", False)
    assert created["next_date"] == str(TODAY)
    assert created["period_end"] == str(TODAY + timedelta(days=30))
    assert created["total"] == "31.35"
    assert created["template"]["lines"][0]["unit_price"] == "29"
    assert created["template"]["discount_value"] is None
    assert (created["active"], created["finished"], created["runs"]) == (True, False, [])
    plan_id = created["id"]
    assert [plan["id"] for plan in user_client.get("/api/recurring").json()] == [plan_id]

    changed = user_client.put(
        f"/api/recurring/{plan_id}", json=plan_body(customer_id, name="Hosting Plus")
    )
    assert changed.json()["name"] == "Hosting Plus"
    assert post(user_client, f"/api/recurring/{plan_id}/pause")["active"] is False
    assert post(user_client, f"/api/recurring/{plan_id}/resume")["active"] is True

    [run] = container.recurring.run_due()
    plan = user_client.get(f"/api/recurring/{plan_id}").json()
    assert plan["runs"] == [
        {
            "period_start": str(TODAY),
            "at": "2026-01-15T09:00:00Z",
            "outcome": "issued",
            "document_id": str(run.document_id),
            "code": "",
            "message": "",
        }
    ]
    invoice = user_client.get(f"/api/documents/{run.document_id}").json()
    assert (invoice["status"], invoice["service_from"], invoice["subject"]) == (
        "issued",
        str(TODAY),
        "Hosting",
    )
    assert user_client.delete(f"/api/recurring/{plan_id}").status_code == 204
    assert user_client.get(f"/api/recurring/{plan_id}").status_code == 404
    # The invoice stays.
    assert user_client.get(f"/api/documents/{run.document_id}").status_code == 200


def test_plans_pass_field_values_to_their_invoices(
    user_client: TestClient, customer_id: str, container: Container
) -> None:
    body = with_template(plan_body(customer_id), fields={"contract": "V-7", "project": ""})
    created = post(user_client, "/api/recurring", body, status=201)
    assert created["template"]["fields"] == {"contract": "V-7"}
    [run] = container.recurring.run_due()
    invoice = user_client.get(f"/api/documents/{run.document_id}").json()
    assert invoice["fields"] == {"contract": "V-7"}


def test_plans_keep_running_when_their_layout_is_deleted(
    user_client: TestClient, customer_id: str, container: Container
) -> None:
    trust = post(user_client, "/api/print-layouts", {"name": "Treuhand"}, status=201)
    body = with_template(plan_body(customer_id), print_layout_id=trust["id"])
    created = post(user_client, "/api/recurring", body, status=201)
    assert created["template"]["print_layout_id"] == trust["id"]
    unknown = with_template(body, print_layout_id="00000000-0000-0000-0000-000000000009")
    refused = user_client.put(f"/api/recurring/{created['id']}", json=unknown)
    assert refused.status_code == 422
    user_client.delete(f"/api/print-layouts/{trust['id']}")
    [run] = container.recurring.run_due()
    invoice = user_client.get(f"/api/documents/{run.document_id}").json()
    assert (invoice["status"], invoice["print_layout_id"]) == ("issued", None)


def test_plan_rules(user_client: TestClient, customer_id: str) -> None:
    past = user_client.post(
        "/api/recurring", json=plan_body(customer_id, start_date=str(TODAY - timedelta(days=1)))
    )
    assert past.status_code == 422
    assert past.json()["error"]["code"] == "plan_start_in_past"
    empty = plan_body(customer_id)
    empty["template"] = {"currency": "CHF", "lines": []}
    assert user_client.post("/api/recurring", json=empty).json()["error"]["code"] == "no_positions"
    assert user_client.post("/api/recurring", json=plan_body(str(uuid4()))).status_code == 422
    assert user_client.post(f"/api/recurring/{uuid4()}/pause").status_code == 404
