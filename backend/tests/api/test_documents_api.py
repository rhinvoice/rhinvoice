import hashlib
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rhinvoice.api.container import Container
from rhinvoice.application.document.printing import PrintModel, ReminderPrint
from rhinvoice.domain.shared.clock import FixedClock

type Json = dict[str, Any]

LINES = [
    {"description": "Beratung", "quantity": "10", "unit": "HUR", "unit_price": "150"},
    {"kind": "text", "description": "Phase 2"},
    {
        "description": "Kaffee",
        "quantity": "3",
        "unit": "C62",
        "unit_price": "12.35",
        "tax_category": "reduced",
    },
]


def create(client: TestClient, customer_id: str, **fields: object) -> Json:
    body = {"type": "invoice", "customer_id": customer_id, "lines": LINES, **fields}
    response = client.post("/api/documents", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


def post(client: TestClient, path: str, body: Json | None = None, status: int = 200) -> Json:
    response = client.post(path, json=body)
    assert response.status_code == status, response.text
    return dict(response.json())


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/dashboard").status_code == 401


def test_create_calculates_totals(user_client: TestClient, customer_id: str) -> None:
    document = create(user_client, customer_id, subject="Website", discount_value="10")
    assert document["status"] == "draft"
    assert document["display_status"] == "draft"
    assert document["number"] is None
    assert document["recipient"]["name"] == "Beispiel AG"
    assert document["treatment"] == "domestic"
    assert [line["amount"] for line in document["lines"]] == ["1500.00", None, "37.05"]
    assert [line["tax_rate"] for line in document["lines"]] == [None, None, None]
    totals = document["totals"]
    assert totals["subtotal"] == "1537.05"
    assert totals["discount"] == "153.71"
    assert totals["net"] == "1383.34"
    assert [(group["rate"], group["tax"]) for group in totals["groups"]] == [
        ("8.1", "109.35"),
        ("2.6", "0.87"),
    ]
    assert totals["total"] == "1493.55"
    assert document["open_amount"] == totals["total"]
    assert [event["kind"] for event in document["events"]] == ["created"]
    loaded = user_client.get(f"/api/documents/{document['id']}")
    assert loaded.json() == document


def test_update_replaces_the_draft(user_client: TestClient, customer_id: str) -> None:
    document = create(user_client, customer_id)
    body = {
        "customer_id": customer_id,
        "lines": [LINES[0]],
        "price_mode": "gross",
        "treatment_override": "export",
        "override_reason": "Lieferung ins Ausland",
    }
    response = user_client.put(f"/api/documents/{document['id']}", json=body)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert len(updated["lines"]) == 1
    assert updated["treatment"] == "export"
    assert updated["treatment_overridden"] is True
    assert updated["totals"]["total"] == "1500.00"
    assert [event["kind"] for event in updated["events"]] == ["created", "tax_overridden"]


def test_invoice_lifecycle(user_client: TestClient, customer_id: str) -> None:
    draft = create(user_client, customer_id, lines=[LINES[0]])
    path = f"/api/documents/{draft['id']}"
    issued = post(user_client, f"{path}/issue")
    assert issued["status"] == "issued"
    assert issued["number"] is not None
    assert issued["issue_date"] == "2026-01-15"
    assert issued["due_date"] == "2026-02-14"
    assert issued["lines"][0]["tax_rate"] == "8.1"
    assert issued["totals"]["total"] == "1621.50"

    frozen = user_client.put(path, json={"customer_id": customer_id})
    assert frozen.status_code == 409
    assert user_client.delete(path).status_code == 409

    partly = post(user_client, f"{path}/payments", {"paid_on": "2026-01-14", "amount": "621.50"})
    assert partly["status"] == "partially_paid"
    assert partly["paid_amount"] == "621.50"
    assert partly["open_amount"] == "1000.00"
    too_much = user_client.post(
        f"{path}/payments", json={"paid_on": "2026-01-14", "amount": "1000.01"}
    )
    assert too_much.status_code == 422
    assert too_much.json()["error"]["code"] == "payment_exceeds_open_amount"

    paid = post(user_client, f"{path}/mark-paid", {"paid_on": "2026-01-15"})
    assert paid["status"] == "paid"
    assert paid["display_status"] == "paid"
    assert paid["open_amount"] == "0.00"
    assert [payment["amount"] for payment in paid["payments"]] == ["621.50", "1000.00"]

    payment_id = paid["payments"][1]["id"]
    removed = user_client.delete(f"{path}/payments/{payment_id}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "partially_paid"
    assert user_client.delete(f"{path}/payments/{payment_id}").status_code == 404

    page = user_client.get("/api/documents", params={"type": "invoice"}).json()
    assert page["total"] == 1
    assert page["items"][0]["open_amount"] == "1000.00"


def test_cancel_issues_a_cancellation(user_client: TestClient, customer_id: str) -> None:
    invoice = create(user_client, customer_id)
    path = f"/api/documents/{invoice['id']}"
    assert user_client.post(f"{path}/cancel").status_code == 409  # drafts are deleted instead
    post(user_client, f"{path}/issue")
    cancelled = post(user_client, f"{path}/cancel")
    assert cancelled["status"] == "cancelled"
    assert cancelled["display_status"] == "cancelled"
    cancellation = user_client.get(f"/api/documents/{cancelled['cancelled_by_id']}").json()
    assert cancellation["type"] == "cancellation"
    assert cancellation["status"] == "issued"
    assert cancellation["source_id"] == invoice["id"]
    assert cancellation["totals"]["total"] == "-" + cancelled["totals"]["total"]
    assert user_client.post(f"{path}/cancel").status_code == 409
    duplicate = user_client.post(f"/api/documents/{cancellation['id']}/duplicate")
    assert duplicate.status_code == 409


def test_quote_flow(user_client: TestClient, customer_id: str) -> None:
    quote = create(user_client, customer_id, type="quote")
    path = f"/api/documents/{quote['id']}"
    assert user_client.post(f"{path}/accept").status_code == 409
    sent = post(user_client, f"{path}/issue")
    assert sent["status"] == "sent"
    assert sent["due_date"] == "2026-02-14"
    accepted = post(user_client, f"{path}/accept")
    assert accepted["status"] == "accepted"

    invoice = post(user_client, f"{path}/convert", status=201)
    assert invoice["type"] == "invoice"
    assert invoice["status"] == "draft"
    assert invoice["source_id"] == quote["id"]
    assert len(invoice["lines"]) == len(LINES)
    converted = user_client.get(path).json()
    assert converted["status"] == "accepted"
    assert converted["converted_to_id"] == invoice["id"]
    again = user_client.post(f"{path}/convert")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_converted"
    assert converted["events"][-1] == {
        "at": converted["events"][-1]["at"],
        "kind": "converted",
        "detail": invoice["id"],
    }

    other = create(user_client, customer_id, type="quote")
    post(user_client, f"/api/documents/{other['id']}/issue")
    declined = post(user_client, f"/api/documents/{other['id']}/decline")
    assert declined["status"] == "declined"


def test_duplicate_and_delete_drafts(user_client: TestClient, customer_id: str) -> None:
    original = create(user_client, customer_id, subject="Original")
    copy = post(user_client, f"/api/documents/{original['id']}/duplicate", status=201)
    assert copy["id"] != original["id"]
    assert copy["subject"] == "Original"
    assert copy["source_id"] is None
    assert {line["id"] for line in copy["lines"]}.isdisjoint(
        line["id"] for line in original["lines"]
    )
    assert user_client.delete(f"/api/documents/{copy['id']}").status_code == 204
    assert user_client.get(f"/api/documents/{copy['id']}").status_code == 404


def test_search_filters_and_sorts(
    user_client: TestClient, customer_id: str, clock: FixedClock
) -> None:
    def create_later(**fields: object) -> Json:
        clock.set(clock.now() + timedelta(minutes=1))
        return create(user_client, customer_id, **fields)

    first = create_later(subject="Gartenpflege")
    second = create_later(subject="Webdesign")
    quote = create_later(type="quote", subject="Webshop")
    post(user_client, f"/api/documents/{second['id']}/issue")

    def ids(**params: str | list[str]) -> list[str]:
        response = user_client.get("/api/documents", params=params)
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    assert ids(type="invoice") == [second["id"], first["id"]]
    assert ids(type=["invoice", "quote"], sort="created_at", direction="asc") == [
        first["id"],
        second["id"],
        quote["id"],
    ]
    assert ids(q="web") == [quote["id"], second["id"]]
    assert ids(status="issued") == [second["id"]]
    assert ids(status=["draft", "overdue"], type="invoice") == [first["id"]]
    assert ids(customer_id=customer_id, type="quote") == [quote["id"]]
    assert user_client.get("/api/documents", params={"status": "unknown"}).status_code == 422


def test_list_facets_and_bulk_payments(user_client: TestClient, customer_id: str) -> None:
    first = post(user_client, f"/api/documents/{create(user_client, customer_id)['id']}/issue")
    second = post(user_client, f"/api/documents/{create(user_client, customer_id)['id']}/issue")
    draft = create(user_client, customer_id)

    page = user_client.get("/api/documents", params={"type": "invoice", "year": 2026}).json()
    assert page["years"] == [2026]
    assert page["status_counts"] == [
        {"status": "draft", "count": 1},
        {"status": "issued", "count": 2},
    ]
    assert page["totals"] == [
        {"currency": "CHF", "count": 2, "total": "3319.00", "open": "3319.00"},
    ]
    assert user_client.get("/api/documents", params={"year": 2025}).json()["items"] == []
    assert user_client.get("/api/documents", params={"year": 1800}).status_code == 422

    # Without a date: today on the server.
    paid = post(
        user_client,
        "/api/documents/mark-paid",
        {"document_ids": [first["id"], second["id"]]},
    )
    assert sorted(item["document_id"] for item in paid["payments"]) == sorted(
        [first["id"], second["id"]]
    )
    page = user_client.get("/api/documents", params={"type": "invoice"}).json()
    assert page["totals"][0]["open"] == "0.00"
    assert {"status": "paid", "count": 2} in page["status_counts"]

    refused = user_client.post(
        "/api/documents/mark-paid",
        json={"document_ids": [draft["id"]], "paid_on": "2026-01-15"},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "cannot_mark_paid"
    assert refused.json()["error"]["details"] == {"document": draft["id"]}
    empty = user_client.post(
        "/api/documents/mark-paid", json={"document_ids": [], "paid_on": "2026-01-15"}
    )
    assert empty.status_code == 422

    undone = user_client.post("/api/documents/remove-payments", json={"payments": paid["payments"]})
    assert undone.status_code == 204, undone.text
    assert user_client.get(f"/api/documents/{first['id']}").json()["status"] == "issued"
    again = user_client.post("/api/documents/remove-payments", json={"payments": paid["payments"]})
    assert again.status_code == 404


def test_unknown_documents_are_not_found(user_client: TestClient, customer_id: str) -> None:
    unknown = "/api/documents/00000000-0000-0000-0000-000000000000"
    assert user_client.get(unknown).status_code == 404
    assert user_client.post(f"{unknown}/issue").status_code == 404
    missing_customer = user_client.post(
        "/api/documents",
        json={"type": "invoice", "customer_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing_customer.status_code == 422
    assert list(missing_customer.json()["error"]["details"]) == ["customer_id"]
    cancellation = user_client.post(
        "/api/documents", json={"type": "cancellation", "customer_id": customer_id}
    )
    assert cancellation.status_code == 422


def test_line_validation_names_the_line(user_client: TestClient, customer_id: str) -> None:
    body = {
        "type": "invoice",
        "customer_id": customer_id,
        "lines": [LINES[0], {"description": "", "quantity": "1"}],
    }
    response = user_client.post("/api/documents", json=body)
    assert response.status_code == 422
    assert list(response.json()["error"]["details"]) == ["lines.1.description"]


def test_dashboard(user_client: TestClient, customer_id: str) -> None:
    empty = user_client.get("/api/dashboard").json()
    assert empty == {
        "figures": [],
        "revenue": [],
        "recent": [],
        "aging": [],
        "expected": [],
        "overdue": [],
        "quotes": [],
        "top_customers": [],
        "days_to_pay": [],
        "today": "2026-01-15",
        "year_to_date": [],
    }
    invoice = create(user_client, customer_id, lines=[LINES[0]])
    post(user_client, f"/api/documents/{invoice['id']}/issue")
    overview = user_client.get("/api/dashboard").json()
    assert overview["figures"] == [
        {
            "currency": "CHF",
            "open": "1621.50",
            "overdue": "0.00",
            "paid": "0.00",
            "open_count": 1,
            "overdue_count": 0,
        },
    ]
    assert overview["revenue"] == [{"month": "2026-01-01", "currency": "CHF", "net": "1500.00"}]
    assert [(item["document"]["id"], item["event"]) for item in overview["recent"]] == [
        (invoice["id"], "issued"),
        (invoice["id"], "created"),
    ]
    assert overview["aging"] == [
        {
            "currency": "CHF",
            "not_due": "1621.50",
            "late_30": "0.00",
            "late_60": "0.00",
            "late_more": "0.00",
        }
    ]
    assert len(overview["expected"]) == 6
    assert sum(Decimal(week["amount"]) for week in overview["expected"]) == Decimal("1621.50")
    assert overview["overdue"] == []
    assert overview["top_customers"] == [
        {
            "customer_id": customer_id,
            "customer_name": "Beispiel AG",
            "currency": "CHF",
            "net": "1500.00",
        }
    ]
    assert (overview["quotes"], overview["days_to_pay"]) == ([], [])
    assert overview["year_to_date"] == [
        {"currency": "CHF", "current": "1500.00", "previous": "0.00"}
    ]


def test_preview_calculates_without_saving(user_client: TestClient, customer_id: str) -> None:
    body = {"type": "invoice", "customer_id": customer_id, "lines": LINES, "discount_value": "10"}
    preview = post(user_client, "/api/documents/preview", body)
    assert preview["treatment"] == "domestic"
    assert preview["notice"] == ""
    assert preview["line_amounts"] == ["1500.00", None, "37.05"]
    assert preview["totals"]["total"] == "1493.55"
    assert preview["rates"] == {
        "standard": "8.1",
        "reduced": "2.6",
        "special": "3.8",
        "zero": "0",
        "exempt": "0",
    }
    assert user_client.get("/api/documents").json()["total"] == 0
    invalid = user_client.post(
        "/api/documents/preview", json={**body, "lines": [{"description": "x", "unit": "XYZ"}]}
    )
    assert invalid.status_code == 422


def test_documents_render_as_html(user_client: TestClient, customer_id: str) -> None:
    body = {"type": "invoice", "customer_id": customer_id, "lines": LINES, "subject": "Website"}
    preview = user_client.post("/api/documents/render", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"] == "text/html; charset=utf-8"
    assert "<h1>Rechnung</h1>" in preview.text
    assert user_client.get("/api/documents").json()["total"] == 0

    created = create(user_client, customer_id)
    issued = post(user_client, f"/api/documents/{created['id']}/issue")
    page = user_client.get(f"/api/documents/{created['id']}/html")
    assert page.status_code == 200
    assert f'<span class="number">{issued["number"]}</span>' in page.text
    missing = user_client.get("/api/documents/00000000-0000-0000-0000-000000000000/html")
    assert missing.status_code == 404


class FakePdf:
    def __init__(self) -> None:
        self.calls = 0
        self.e_invoices: list[bytes | None] = []

    def pdf(self, model: PrintModel, e_invoice: bytes | None = None) -> bytes:
        self.calls += 1
        self.e_invoices.append(e_invoice)
        return f"%PDF-{model.view.document.number} {self.calls}".encode()

    def reminder_pdf(self, reminder: ReminderPrint) -> bytes:
        return f"%PDF-reminder {reminder.reminder.level}".encode()


def test_documents_as_pdf(
    user_client: TestClient, customer_id: str, app: FastAPI, container: Container
) -> None:
    created = create(user_client, customer_id)
    path = f"/api/documents/{created['id']}/pdf"
    unavailable = user_client.get(path)
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "unavailable"

    fake = FakePdf()
    app.state.container = replace(
        container, printing=replace(container.printing, pdf_renderer=fake)
    )
    draft = user_client.get(path)
    assert draft.status_code == 200
    assert draft.headers["content-type"] == "application/pdf"
    assert draft.headers["content-disposition"] == (
        "inline; filename=\"Rechnung (Entwurf).pdf\"; filename*=UTF-8''Rechnung%20%28Entwurf%29.pdf"
    )
    assert draft.headers["cache-control"] == "no-store"
    assert "etag" not in draft.headers

    issued = post(user_client, f"/api/documents/{created['id']}/issue")
    # Archived right when issuing: later downloads return that file.
    assert fake.calls == 2
    first = user_client.get(path, params={"download": "true"})
    number = issued["number"]
    assert first.headers["content-disposition"] == (
        f"attachment; filename=\"Rechnung {number}.pdf\"; filename*=UTF-8''Rechnung%20{number}.pdf"
    )
    assert first.headers["cache-control"] == "private, max-age=31536000"
    assert first.headers["etag"] == f'"{hashlib.sha256(first.content).hexdigest()}"'
    again = user_client.get(path)
    assert again.content == first.content
    assert fake.calls == 2
    cancelled = post(user_client, f"/api/documents/{created['id']}/cancel")
    assert fake.calls == 3
    cancellation_pdf = user_client.get(f"/api/documents/{cancelled['cancelled_by_id']}/pdf")
    assert (
        cancellation_pdf.content == f"%PDF-{cancellation_number(user_client, cancelled)} 3".encode()
    )


def cancellation_number(client: TestClient, cancelled: Json) -> str:
    response = client.get(f"/api/documents/{cancelled['cancelled_by_id']}")
    return str(response.json()["number"])
