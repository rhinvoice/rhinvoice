from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rhinvoice.api.container import Container
from tests.api.conftest import NOW
from tests.api.test_documents_api import FakePdf, create, post

TODAY = NOW.date()


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/dunning").status_code == 401
    assert client.get("/api/dunning/levels").status_code == 401


def invoice_number(client: TestClient, invoice_id: str) -> str:
    return str(client.get(f"/api/documents/{invoice_id}").json()["number"])


def test_overdue_invoices_get_reminders(
    user_client: TestClient, customer_id: str, app: FastAPI, container: Container
) -> None:
    due = TODAY - timedelta(days=20)
    invoice = create(
        user_client,
        customer_id,
        issue_date=str(due - timedelta(days=30)),
        due_date=str(due),
    )
    post(user_client, f"/api/documents/{invoice['id']}/issue")
    [item] = user_client.get("/api/dunning").json()
    assert item["invoice"]["id"] == invoice["id"]
    assert item["reminders"] == []
    assert item["days_overdue"] == 20
    assert item["next"] == {
        "level": 1,
        "due_on": str(due + timedelta(days=7)),
        "due": True,
        "fee": "0.00",
        "deadline": str(TODAY + timedelta(days=10)),
    }
    path = f"/api/documents/{invoice['id']}/reminders"
    reminder = post(user_client, path, {"level": 1}, status=201)
    # A second click with the level it saw: refused, nothing more written.
    again = user_client.post(path, json={"level": 1})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "reminder_level_changed"
    early = user_client.post(path, json={"level": 2})
    assert early.json()["error"]["code"] == "reminder_not_due"
    assert (reminder["level"], reminder["fee"], reminder["due_date"]) == (
        1,
        "0.00",
        str(TODAY + timedelta(days=10)),
    )
    assert reminder["total"] == reminder["open_amount"]
    listed = user_client.get(f"/api/documents/{invoice['id']}/reminders").json()
    assert [r["id"] for r in listed] == [reminder["id"]]
    html = user_client.get(f"/api/reminders/{reminder['id']}/html")
    assert html.status_code == 200
    assert "<h1>Zahlungserinnerung</h1>" in html.text
    # Without a PDF service (tests): 503.
    assert user_client.get(f"/api/reminders/{reminder['id']}/pdf").status_code == 503
    app.state.container = replace(
        container, printing=replace(container.printing, pdf_renderer=FakePdf())
    )
    pdf = user_client.get(f"/api/reminders/{reminder['id']}/pdf?download=true")
    assert pdf.content == b"%PDF-reminder 1"
    number = invoice_number(user_client, invoice["id"])
    assert pdf.headers["content-disposition"] == (
        f'attachment; filename="Zahlungserinnerung {number}.pdf"; '
        f"filename*=UTF-8''Zahlungserinnerung%20{number}.pdf"
    )
    assert pdf.headers["cache-control"] == "no-store"
    history = user_client.get(f"/api/documents/{invoice['id']}").json()["events"]
    assert history[-1]["kind"] == "reminded"


def test_reminders_of_unknown_invoices(user_client: TestClient) -> None:
    missing = user_client.get(f"/api/documents/{uuid4()}/reminders")
    assert missing.status_code == 404


def test_reminders_need_an_overdue_invoice(user_client: TestClient, customer_id: str) -> None:
    invoice = create(user_client, customer_id)
    refused = user_client.post(
        f"/api/documents/{invoice['id']}/reminders", json={"level": 1, "early": True}
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "not_remindable"


def test_levels(user_client: TestClient) -> None:
    levels = user_client.get("/api/dunning/levels").json()
    assert [level["level"] for level in levels] == [1, 2, 3]
    assert [level["fee"] for level in levels] == ["0.00", "0.00", "0.00"]
    changed = [{**level, "fee": "5"} for level in levels]
    saved = user_client.put("/api/dunning/levels", json=changed)
    assert saved.status_code == 200, saved.text
    assert [level["fee"] for level in saved.json()] == ["5.00", "5.00", "5.00"]
    assert user_client.put("/api/dunning/levels", json=changed[:2]).status_code == 422
    duplicate = [changed[0], changed[0], changed[2]]
    refused = user_client.put("/api/dunning/levels", json=duplicate)
    assert refused.json()["error"]["code"] == "levels_incomplete"
    too_much = [{**changed[0], "fee": "1000.05"}, changed[1], changed[2]]
    assert user_client.put("/api/dunning/levels", json=too_much).status_code == 422
