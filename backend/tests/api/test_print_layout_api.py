from fastapi.testclient import TestClient

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
}


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/print-layout").status_code == 401
    assert client.put("/api/print-layout", json=DEFAULT).status_code == 401
    assert client.post("/api/print-layout/preview", json=DEFAULT).status_code == 401


def test_layout_and_preview(user_client: TestClient) -> None:
    assert user_client.get("/api/print-layout").json() == DEFAULT
    classic = {**DEFAULT, "template": "classic", "footer_accounts": "all", "e_invoice": False}
    assert user_client.put("/api/print-layout", json=classic).json() == classic
    assert user_client.get("/api/print-layout").json() == classic
    assert (
        user_client.put("/api/print-layout", json={**DEFAULT, "font": "comic"}).status_code == 422
    )
    refused = user_client.post("/api/print-layout/preview", json=DEFAULT)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "preview_needs_customer"
    user_client.put(
        "/api/company",
        json={
            "name": "Muster GmbH",
            "address": {"postal_code": "8001", "city": "Zürich", "country": "CH"},
            "default_currency": "CHF",
        },
    )
    customer = user_client.post(
        "/api/customers",
        json={
            "kind": "company",
            "company_name": "Beispiel AG",
            "address": {"postal_code": "3011", "city": "Bern", "country": "CH"},
        },
    )
    assert customer.status_code == 201, customer.text
    preview = user_client.post("/api/print-layout/preview", json={**DEFAULT, "template": "plain"})
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("text/html")
    assert '<body class="template-plain' in preview.text
