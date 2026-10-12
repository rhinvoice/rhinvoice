from typing import Any

from fastapi.testclient import TestClient

from tests.api.test_masterdata_api import ADDRESS

type Json = dict[str, Any]

RC = (
    "Übergang der Steuerschuld auf den Leistungsempfänger "
    "(Steuerschuldnerschaft des Leistungsempfängers, Reverse Charge)."
)


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/text-templates").status_code == 401
    assert client.get("/api/legal-notices").status_code == 401


def test_templates_crud_and_order(user_client: TestClient) -> None:
    assert user_client.get("/api/text-templates").json() == []
    for name, text in (("Fällig am", "Zahlbar bis {faellig}."), ("Zweck", "Nr. {nummer}")):
        seeded = {
            "kind": "payment",
            "document_type": "invoice",
            "language": "de",
            "name": name,
            "text": text,
            "is_default": True,
        }
        assert user_client.post("/api/text-templates", json=seeded).status_code == 201
    user_client.post(
        "/api/text-templates",
        json={
            **seeded,
            "name": "Zahlbar prompt ohne Abzug",
            "text": "Prompt.",
            "is_default": False,
        },
    )

    body: Json = {
        "kind": "payment",
        "document_type": "invoice",
        "language": "de",
        "name": "Skonto",
        "text": "Bei Zahlung bis {faellig} ohne Abzug.",
    }
    created = user_client.post("/api/text-templates", json=body)
    assert created.status_code == 201, created.text
    template = created.json()
    assert (template["position"], template["is_default"]) == (3, False)
    listed = user_client.get("/api/text-templates").json()
    assert [t["name"] for t in listed] == [
        "Fällig am",
        "Zweck",
        "Zahlbar prompt ohne Abzug",
        "Skonto",
    ]

    changed = user_client.put(
        f"/api/text-templates/{template['id']}", json={**body, "name": "Neu", "is_default": True}
    )
    assert changed.json()["name"] == "Neu"
    assert changed.json()["is_default"] is True

    moved = user_client.post(f"/api/text-templates/{template['id']}/move", json={"up": True})
    payments = [
        t["name"]
        for t in moved.json()
        if (t["document_type"], t["language"], t["kind"]) == ("invoice", "de", "payment")
    ]
    assert payments == ["Fällig am", "Zweck", "Neu", "Zahlbar prompt ohne Abzug"]

    unknown = user_client.post("/api/text-templates", json={**body, "text": "Bis {morgen}"})
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_placeholder"
    assert user_client.post("/api/text-templates", json={**body, "name": ""}).status_code == 422

    path = f"/api/text-templates/{template['id']}"
    assert user_client.delete(path).status_code == 204
    assert user_client.delete(path).status_code == 404


def test_legal_notices(user_client: TestClient) -> None:
    company = {
        "name": "Muster GmbH",
        "address": ADDRESS,
        "default_currency": "CHF",
        "vat_number": "CHE-123.456.788",
    }
    assert user_client.put("/api/company", json=company).status_code == 200
    notices = user_client.get("/api/legal-notices").json()
    reverse = next(
        n for n in notices if (n["treatment"], n["language"]) == ("reverse_charge", "de")
    )
    assert reverse == {
        "treatment": "reverse_charge",
        "language": "de",
        "text": RC,
        "default_text": RC,
        "customized": False,
    }
    path = "/api/legal-notices/reverse_charge/de"
    own = user_client.put(path, json={"text": "Steuerschuld beim Empfänger."}).json()
    assert (own["text"], own["customized"]) == ("Steuerschuld beim Empfänger.", True)
    reset = user_client.put(path, json={"text": ""}).json()
    assert (reset["text"], reset["customized"]) == (RC, False)
    domestic = user_client.put("/api/legal-notices/domestic/de", json={"text": "x"})
    assert domestic.status_code == 422
