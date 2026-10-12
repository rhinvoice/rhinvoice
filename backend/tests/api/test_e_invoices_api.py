from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rhinvoice.api.container import Container
from tests.api.test_documents_api import LINES, FakePdf, create, post
from tests.api.test_masterdata_api import ADDRESS


def test_endpoints_require_login(client: TestClient) -> None:
    unknown = "/api/documents/00000000-0000-0000-0000-000000000000"
    assert client.get(f"{unknown}/e-invoice").status_code == 401
    assert client.get(f"{unknown}/xrechnung").status_code == 401


def test_e_invoices_of_an_invoice(
    app: FastAPI, container: Container, user_client: TestClient, customer_id: str
) -> None:
    fake = FakePdf()
    app.state.container = replace(
        container, printing=replace(container.printing, pdf_renderer=fake)
    )
    # XRechnung asks for more than the company and customer have yet.
    lacking = post(user_client, f"/api/documents/{create(user_client, customer_id)['id']}/issue")
    # Issuing archived the PDF right away, with its e-invoice.
    assert fake.e_invoices[0] is not None
    status = user_client.get(f"/api/documents/{lacking['id']}/e-invoice")
    assert status.status_code == 200
    assert status.json() == {
        "enabled": True,
        "embedded": True,
        "zugferd_problems": [],
        "xrechnung_problems": [
            "buyer_reference_missing",
            "seller_email_missing",
            "seller_phone_missing",
            "buyer_email_missing",
        ],
    }
    refused = user_client.get(f"/api/documents/{lacking['id']}/xrechnung")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "e_invoice_incomplete"

    company = {
        "name": "Muster GmbH",
        "address": ADDRESS,
        "default_currency": "CHF",
        "vat_number": "CHE-123.456.788",
        "email": "info@muster.example",
        "phone": "+41 71 000 00 00",
    }
    assert user_client.put("/api/company", json=company).status_code == 200
    customer = {
        "kind": "company",
        "company_name": "Beispiel AG",
        "address": ADDRESS,
        "email": "einkauf@beispiel.example",
    }
    assert user_client.put(f"/api/customers/{customer_id}", json=customer).status_code == 200
    draft = create(user_client, customer_id, reference="04011000-1234512345-06")
    complete = post(user_client, f"/api/documents/{draft['id']}/issue")
    path = f"/api/documents/{complete['id']}"
    assert fake.e_invoices[-1] is not None
    assert fake.e_invoices[-1].startswith(b"<?xml")
    status = user_client.get(f"{path}/e-invoice").json()
    assert (status["embedded"], status["xrechnung_problems"]) == (True, [])
    xrechnung = user_client.get(f"{path}/xrechnung")
    assert xrechnung.status_code == 200
    assert xrechnung.headers["content-type"] == "application/xml"
    number = complete["number"]
    assert xrechnung.headers["content-disposition"] == (
        f'attachment; filename="XRechnung {number}.xml"; '
        f"filename*=UTF-8''XRechnung%20{number}.xml"
    )
    assert b"urn:xeinkauf.de:kosit:xrechnung_3.0" in xrechnung.content


def test_drafts_tell_what_they_will_be(user_client: TestClient, customer_id: str) -> None:
    draft = create(user_client, customer_id)
    status = user_client.get(f"/api/documents/{draft['id']}/e-invoice")
    assert status.status_code == 200
    assert (status.json()["embedded"], status.json()["zugferd_problems"]) == (None, [])
    assert user_client.get(f"/api/documents/{draft['id']}/xrechnung").status_code == 409
    quote = create(user_client, customer_id, type="quote")
    refused = user_client.get(f"/api/documents/{quote['id']}/e-invoice")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "not_an_e_invoice"


def test_the_preview_warns_before_issuing(user_client: TestClient, customer_id: str) -> None:
    body = {"type": "invoice", "customer_id": customer_id, "lines": LINES}
    preview = user_client.post("/api/documents/preview", json=body)
    assert preview.json()["e_invoice_problems"] == []
    # Reverse charge to a German business whose VAT number lacks the country code.
    customer = {
        "kind": "company",
        "company_name": "Kunde GmbH",
        "address": {"postal_code": "10115", "city": "Berlin", "country": "DE"},
        "vat_number": "123456789",
    }
    german = user_client.post("/api/customers", json=customer).json()["id"]
    lacking = user_client.post("/api/documents/preview", json={**body, "customer_id": german})
    assert lacking.json()["e_invoice_problems"] == ["buyer_vat_id_missing"]
