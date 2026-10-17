"""Mail settings and sending through the API, to a local mail server."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from aiosmtpd.controller import Controller
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rhinvoice.api.container import Container
from rhinvoice.infrastructure.mail.content import PrintedMailContent
from tests.api.conftest import NOW
from tests.api.test_documents_api import FakePdf, create, post
from tests.unit.test_smtp import HOST, Inbox, free_port

TODAY = NOW.date()
SERVER = {
    "host": HOST,
    "security": "none",
    "sender": "Rechnung@Muster.example",
    "sender_name": "Muster GmbH",
}


@pytest.fixture
def inbox() -> Inbox:
    return Inbox()


@pytest.fixture
def mailbox(inbox: Inbox) -> Iterator[int]:
    controller = Controller(inbox, hostname=HOST, port=free_port())
    controller.start()
    yield int(controller.port)
    controller.stop()


@pytest.fixture
def printing(app: FastAPI, container: Container) -> None:
    """PDFs from a fake renderer, for the documents and for the mails."""
    printing = replace(container.printing, pdf_renderer=FakePdf())
    app.state.container = replace(
        container,
        printing=printing,
        mail=replace(container.mail, content=PrintedMailContent(printing)),
    )


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/mail/server").status_code == 401
    assert client.get("/api/mail/templates").status_code == 401


def test_the_server_settings(user_client: TestClient, customer_id: str) -> None:
    del customer_id  # sets up the company
    empty = user_client.get("/api/mail/server").json()
    assert empty == {
        "configured": False,
        "host": "",
        "port": 587,
        "security": "starttls",
        "sender": "",
        "sender_name": "",
        "username": "",
        "password_set": False,
        "reply_to": "",
        "copy_to_sender": True,
    }
    body = {
        **SERVER,
        "port": 587,
        "security": "starttls",
        "username": "rechnung",
        "password": "geheim",
    }
    saved = user_client.put("/api/mail/server", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json() == {
        "configured": True,
        "host": HOST,
        "port": 587,
        "security": "starttls",
        "sender": "rechnung@muster.example",
        "sender_name": "Muster GmbH",
        "username": "rechnung",
        "password_set": True,
        "reply_to": "",
        "copy_to_sender": True,
    }
    assert "geheim" not in user_client.get("/api/mail/server").text
    wrong = user_client.put("/api/mail/server", json={**body, "sender": "rechnung"})
    assert wrong.status_code == 422
    assert wrong.json()["error"]["details"] == {
        "sender": "'rechnung' is not a valid e-mail address"
    }


def test_templates(user_client: TestClient, customer_id: str) -> None:
    del customer_id
    templates = user_client.get("/api/mail/templates").json()
    assert len(templates) == 24  # 6 kinds in 4 languages
    assert templates[0] == {
        "kind": "invoice",
        "language": "de",
        "subject": "Rechnung {nummer}",
        "body": templates[0]["default_body"],
        "default_subject": "Rechnung {nummer}",
        "default_body": templates[0]["default_body"],
        "customized": False,
    }
    saved = user_client.put(
        "/api/mail/templates/reminder_1/en", json={"subject": "Reminder {nummer}", "body": "Hi"}
    )
    assert saved.json()["customized"] is True
    unknown = user_client.put("/api/mail/templates/quote/de", json={"subject": "{x}", "body": "Hi"})
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_placeholder"


@pytest.mark.usefixtures("printing")
def test_an_invoice_goes_out_by_mail(
    user_client: TestClient, customer_id: str, mailbox: int, inbox: Inbox
) -> None:
    invoice = create(user_client, customer_id)
    path = f"/api/documents/{invoice['id']}/mail"
    draft = user_client.get(path)
    assert draft.status_code == 422
    assert draft.json()["error"]["code"] == "mail_draft"
    post(user_client, f"/api/documents/{invoice['id']}/issue")
    prepared = user_client.get(path).json()
    number = user_client.get(f"/api/documents/{invoice['id']}").json()["number"]
    assert prepared["to"] == []
    assert prepared["subject"] == f"Rechnung {number}"
    assert prepared["attachment"] == f"Rechnung {number}.pdf"
    assert prepared["copy_to"] is None
    assert "Muster GmbH" in prepared["body"]
    message = {"to": ["buchhaltung@kunde.example"], "subject": "Rechnung", "body": "Hallo"}
    unconfigured = user_client.post(path, json=message)
    assert unconfigured.status_code == 503
    assert unconfigured.json()["error"]["code"] == "mail_not_configured"

    assert user_client.put("/api/mail/server", json={**SERVER, "port": mailbox}).status_code == 200
    sent = post(user_client, path, message)
    assert sent["events"][-1]["kind"] == "emailed"
    assert sent["events"][-1]["detail"] == "buchhaltung@kunde.example"
    [envelope] = inbox.envelopes
    assert envelope.rcpt_tos == ["buchhaltung@kunde.example", "rechnung@muster.example"]
    received = inbox.parsed()
    assert received["Subject"] == "Rechnung"
    assert [part.get_filename() for part in received.iter_attachments()] == [
        f"Rechnung {number}.pdf"
    ]
    # A Swiss invoice without the details XRechnung needs cannot carry one.
    refused = user_client.post(path, json={**message, "xrechnung": True})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "e_invoice_incomplete"
    assert len(inbox.envelopes) == 1


def test_a_server_that_is_not_there(user_client: TestClient, customer_id: str) -> None:
    del customer_id
    user_client.put("/api/mail/server", json={**SERVER, "port": free_port()})
    failed = user_client.post("/api/mail/test", json={"to": "anna@example.com"})
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "mail_connection_failed"


def test_a_test_mail(user_client: TestClient, customer_id: str, mailbox: int, inbox: Inbox) -> None:
    del customer_id
    user_client.put("/api/mail/server", json={**SERVER, "port": mailbox})
    sent = user_client.post("/api/mail/test", json={"to": "anna@example.com"})
    assert sent.status_code == 204
    assert inbox.parsed()["Subject"] == "Rhinvoice: Test-E-Mail"


@pytest.mark.usefixtures("printing")
def test_a_reminder_goes_out_by_mail(
    user_client: TestClient, customer_id: str, mailbox: int, inbox: Inbox
) -> None:
    due = TODAY - timedelta(days=20)
    invoice = create(
        user_client, customer_id, issue_date=str(due - timedelta(days=30)), due_date=str(due)
    )
    post(user_client, f"/api/documents/{invoice['id']}/issue")
    reminder = post(user_client, f"/api/documents/{invoice['id']}/reminders", {"level": 1}, 201)
    path = f"/api/reminders/{reminder['id']}/mail"
    prepared = user_client.get(path).json()
    assert prepared["subject"].startswith("Zahlungserinnerung zur Rechnung ")
    user_client.put("/api/mail/server", json={**SERVER, "port": mailbox, "copy_to_sender": False})
    sent = post(user_client, path, {"to": ["a@example.com"], "subject": "Erinnerung", "body": "x"})
    assert (sent["id"], sent["events"][-1]["kind"], sent["events"][-1]["detail"]) == (
        invoice["id"],
        "reminder_emailed",
        "1 a@example.com",
    )
    [part] = list(inbox.parsed().iter_attachments())
    assert part.get_content() == b"%PDF-reminder 1"
    assert user_client.get(f"/api/reminders/{uuid4()}/mail").status_code == 404
