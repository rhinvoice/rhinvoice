from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rhinvoice.api.container import Container
from rhinvoice.application.document.printing import PrintModel, ReminderPrint

DEFAULT = {
    "template": "modern",
    "logo_position": "right",
    "logo_size": "medium",
    "font": "sans",
    "sender_line": True,
    "contact": False,
    "position_numbers": True,
    "footer_accounts": "invoice_currency",
    "e_invoice": True,
    "info_block": [
        {"key": key, "shown": True, "label": ""}
        for key in ("number", "customer_number", "date", "due_date", "service_date", "reference")
    ],
}
ROWS = [
    {"key": "number", "shown": True, "label": ""},
    {"key": "project", "shown": True, "label": ""},
    {"key": "buyer_accounting", "shown": True, "label": ""},
    {"key": "custom-0a1b2c3d", "shown": True, "label": "Objekt"},
    *(
        {"key": key, "shown": key != "service_date", "label": ""}
        for key in ("customer_number", "date", "due_date", "service_date", "reference")
    ),
]


def set_up_company(client: TestClient) -> str:
    client.put(
        "/api/company",
        json={
            "name": "Muster GmbH",
            "address": {"postal_code": "8001", "city": "Zürich", "country": "CH"},
            "default_currency": "CHF",
        },
    )
    customer = client.post(
        "/api/customers",
        json={
            "kind": "company",
            "company_name": "Beispiel AG",
            "address": {"postal_code": "3011", "city": "Bern", "country": "CH"},
        },
    )
    assert customer.status_code == 201, customer.text
    return str(customer.json()["id"])


def test_endpoints_require_login(client: TestClient) -> None:
    some = "00000000-0000-0000-0000-000000000001"
    assert client.get("/api/print-layouts").status_code == 401
    assert client.post("/api/print-layouts", json={"name": "X"}).status_code == 401
    body = {"name": "X", "layout": DEFAULT}
    assert client.put(f"/api/print-layouts/{some}", json=body).status_code == 401
    assert client.post(f"/api/print-layouts/{some}/default").status_code == 401
    assert client.delete(f"/api/print-layouts/{some}").status_code == 401
    assert client.post("/api/print-layouts/preview", json=DEFAULT).status_code == 401
    assert client.post("/api/print-layouts/sample", json=DEFAULT).status_code == 401


def test_layouts_are_listed_added_saved_and_deleted(user_client: TestClient) -> None:
    [standard] = user_client.get("/api/print-layouts").json()
    assert (standard["name"], standard["is_default"], standard["layout"]) == (
        "Standard",
        True,
        DEFAULT,
    )
    created = user_client.post("/api/print-layouts", json={"name": " Treuhand "})
    assert created.status_code == 201, created.text
    trust = created.json()
    assert (trust["name"], trust["is_default"], trust["layout"]) == ("Treuhand", False, DEFAULT)
    listed = {**DEFAULT, "template": "classic", "info_block": ROWS}
    path = f"/api/print-layouts/{trust['id']}"
    saved = user_client.put(path, json={"name": "Treuhand", "layout": listed})
    assert saved.json()["layout"] == listed
    copy = user_client.post("/api/print-layouts", json={"name": "Behörden", "copy_of": trust["id"]})
    assert copy.json()["layout"] == listed
    taken = user_client.post("/api/print-layouts", json={"name": "standard"})
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "print_layout_name_taken"
    hidden_number = [{"key": "number", "shown": False, "label": ""}, *ROWS[1:]]
    refused = user_client.put(
        path, json={"name": "Treuhand", "layout": {**DEFAULT, "info_block": hidden_number}}
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["details"] == {"info_block": "the row number is always shown"}
    comic = user_client.put(path, json={"name": "Treuhand", "layout": {**DEFAULT, "font": "comic"}})
    assert comic.status_code == 422

    assert user_client.post(f"{path}/default").json()["is_default"]
    names = [
        (item["name"], item["is_default"]) for item in user_client.get("/api/print-layouts").json()
    ]
    assert names == [("Treuhand", True), ("Behörden", False), ("Standard", False)]
    default = user_client.delete(path)
    assert default.status_code == 409
    assert default.json()["error"]["code"] == "default_print_layout"
    assert user_client.delete(f"/api/print-layouts/{standard['id']}").status_code == 204
    assert user_client.delete(f"/api/print-layouts/{standard['id']}").status_code == 404


def test_customers_and_documents_choose_a_layout(user_client: TestClient) -> None:
    customer_id = set_up_company(user_client)
    trust = user_client.post("/api/print-layouts", json={"name": "Treuhand"}).json()
    assert user_client.get(f"/api/customers/{customer_id}").json()["print_layout_id"] is None
    body = {
        "kind": "company",
        "company_name": "Beispiel AG",
        "address": {"postal_code": "3011", "city": "Bern", "country": "CH"},
        "print_layout_id": trust["id"],
    }
    changed = user_client.put(f"/api/customers/{customer_id}", json=body)
    assert changed.json()["print_layout_id"] == trust["id"]
    unknown = user_client.put(
        f"/api/customers/{customer_id}",
        json={**body, "print_layout_id": "00000000-0000-0000-0000-000000000009"},
    )
    assert unknown.status_code == 422
    assert unknown.json()["error"]["details"] == {"print_layout_id": "unknown print layout"}
    draft = user_client.post(
        "/api/documents",
        json={
            "type": "invoice",
            "customer_id": customer_id,
            "lines": [{"description": "Beratung", "quantity": "1", "unit_price": "100"}],
            "print_layout_id": trust["id"],
        },
    ).json()
    assert draft["print_layout_id"] == trust["id"]
    # Deleting the layout leaves the customer and the draft with the default.
    user_client.delete(f"/api/print-layouts/{trust['id']}")
    assert user_client.get(f"/api/customers/{customer_id}").json()["print_layout_id"] is None
    assert user_client.get(f"/api/documents/{draft['id']}").json()["print_layout_id"] is None


class SamplePdf:
    def pdf(self, model: PrintModel, e_invoice: bytes | None = None) -> bytes:
        assert model.sample
        assert e_invoice is None
        return b"%PDF sample"

    def reminder_pdf(self, reminder: ReminderPrint) -> bytes:
        raise NotImplementedError


def test_preview_and_sample(user_client: TestClient, app: FastAPI, container: Container) -> None:
    refused = user_client.post("/api/print-layouts/preview", json=DEFAULT)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "company_not_set_up"
    set_up_company(user_client)
    preview = user_client.post("/api/print-layouts/preview", json={**DEFAULT, "template": "plain"})
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("text/html")
    assert '<body class="template-plain' in preview.text
    # Without a PDF service the sample says so.
    assert user_client.post("/api/print-layouts/sample", json=DEFAULT).status_code == 503
    app.state.container = replace(
        container, printing=replace(container.printing, pdf_renderer=SamplePdf())
    )
    sample = user_client.post("/api/print-layouts/sample", json=DEFAULT)
    assert sample.status_code == 200
    assert sample.content == b"%PDF sample"
    assert sample.headers["content-type"] == "application/pdf"
    assert sample.headers["content-disposition"].startswith("attachment")
