"""The company's tax rates over the API (ADR 0044)."""

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.tax.presets import EXEMPT, REDUCED, STANDARD
from tests.api.test_masterdata_api import ADDRESS
from tests.unit.domain import factories

type Json = dict[str, Any]

EXEMPT_RATE = {
    "name": "Heilbehandlung",
    "category": "E",
    "values": [{"valid_from": "2024-01-01", "percent": "0"}],
    "exemption_reason": "§ 4 Nr. 14 UStG",
}


def test_tax_rates_need_a_login(client: TestClient) -> None:
    rate_id = factories.rate_id()
    for method, path in (
        ("GET", "/api/tax-rates"),
        ("POST", "/api/tax-rates"),
        ("GET", "/api/tax-rates/presets"),
        ("POST", "/api/tax-rates/presets/de_24_other"),
        ("PUT", f"/api/tax-rates/{rate_id}"),
        ("POST", f"/api/tax-rates/{rate_id}/hide"),
        ("POST", f"/api/tax-rates/{rate_id}/show"),
        ("DELETE", f"/api/tax-rates/{rate_id}"),
    ):
        assert client.request(method, path).status_code == 401, path


@pytest.mark.usefixtures("customer_id")
def test_the_company_starts_with_the_rates_of_its_country(user_client: TestClient) -> None:
    rates = user_client.get("/api/tax-rates").json()
    assert [(rate["preset"], rate["category"]) for rate in rates] == [
        ("standard", "S"),
        ("reduced", "S"),
        ("special", "S"),
        ("zero", "Z"),
        ("exempt", "E"),
    ]
    assert rates[0] == {
        "id": str(factories.rate_id(STANDARD)),
        "name": "Normalsatz",
        "category": "S",
        "values": [
            {"valid_from": "2011-01-01", "percent": "8"},
            {"valid_from": "2018-01-01", "percent": "7.7"},
            {"valid_from": "2024-01-01", "percent": "8.1"},
        ],
        "exemption_reason": "",
        "notice": "",
        "preset": "standard",
        "hidden": False,
        "in_use": False,
    }
    assert rates[4]["exemption_reason"] == "Steuerbefreite Leistung"


@pytest.mark.usefixtures("customer_id")
def test_own_rates_are_added_changed_hidden_and_deleted(user_client: TestClient) -> None:
    created = user_client.post("/api/tax-rates", json=EXEMPT_RATE)
    assert created.status_code == 201, created.text
    rate: Json = created.json()
    assert (rate["name"], rate["preset"], rate["in_use"], rate["hidden"]) == (
        "Heilbehandlung",
        None,
        False,
        False,
    )
    changed = user_client.put(
        f"/api/tax-rates/{rate['id']}", json={**EXEMPT_RATE, "notice": "Steuerfrei"}
    ).json()
    assert changed["notice"] == "Steuerfrei"
    assert user_client.post(f"/api/tax-rates/{rate['id']}/hide").json()["hidden"] is True
    assert user_client.post(f"/api/tax-rates/{rate['id']}/show").json()["hidden"] is False
    assert user_client.delete(f"/api/tax-rates/{rate['id']}").status_code == 204
    assert len(user_client.get("/api/tax-rates").json()) == 5


@pytest.mark.usefixtures("customer_id")
def test_refused_rates_say_why(user_client: TestClient) -> None:
    standard = str(factories.rate_id(STANDARD))
    cases: list[tuple[str, str, Json, int, str]] = [
        (
            "POST",
            "/api/tax-rates",
            {**EXEMPT_RATE, "exemption_reason": ""},
            422,
            "rate_exempt_needs_reason",
        ),
        (
            "POST",
            "/api/tax-rates",
            {**EXEMPT_RATE, "category": "S"},
            422,
            "rate_standard_needs_percent",
        ),
        (
            "POST",
            "/api/tax-rates",
            {**EXEMPT_RATE, "name": "normalsatz"},
            409,
            "tax_rate_name_taken",
        ),
        ("POST", "/api/tax-rates", {**EXEMPT_RATE, "values": []}, 422, "validation_error"),
        (
            "POST",
            "/api/tax-rates",
            {**EXEMPT_RATE, "values": [{"valid_from": "2024-01-01", "percent": "8.123"}]},
            422,
            "validation_error",
        ),
        ("PUT", f"/api/tax-rates/{standard}", EXEMPT_RATE, 422, "rate_category_fixed"),
        ("PUT", f"/api/tax-rates/{uuid4()}", EXEMPT_RATE, 404, "not_found"),
        ("POST", "/api/tax-rates/presets/ch_unknown", {}, 404, "unknown_preset"),
    ]
    for method, path, body, status, code in cases:
        response = user_client.request(method, path, json=body)
        assert (response.status_code, response.json()["error"]["code"]) == (status, code), path


@pytest.mark.usefixtures("customer_id")
def test_rates_in_use_are_hidden_not_deleted(user_client: TestClient) -> None:
    reduced = str(factories.rate_id(REDUCED))
    book = user_client.post("/api/articles", json={"name": "Buch", "tax_rate_id": reduced})
    assert book.status_code == 201
    in_use = user_client.delete(f"/api/tax-rates/{reduced}")
    assert in_use.status_code == 409
    assert in_use.json()["error"]["code"] == "tax_rate_in_use"
    hidden = user_client.post(f"/api/tax-rates/{reduced}/hide").json()
    assert (hidden["hidden"], hidden["in_use"]) == (True, True)
    # New choices of a hidden rate are refused.
    refused = user_client.post("/api/articles", json={"name": "Heft", "tax_rate_id": reduced})
    assert refused.status_code == 422
    assert refused.json()["error"] == {
        "code": "tax_rate_hidden",
        "message": "the tax rate is hidden",
        "details": {"tax_rate_id": "the tax rate is hidden"},
    }


def test_presets_of_the_country(user_client: TestClient) -> None:
    missing = user_client.get("/api/tax-rates/presets")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "company_not_set_up"
    german = {
        "name": "Hof Beispiel",
        "address": {**ADDRESS, "postal_code": "10115", "city": "Berlin", "country": "DE"},
        "default_currency": "EUR",
        "vat_number": "DE123456789",
    }
    assert user_client.put("/api/company", json=german).status_code == 200
    presets = user_client.get("/api/tax-rates/presets").json()
    assert [preset["key"] for preset in presets] == [
        "de_24_forestry",
        "de_24_beverages",
        "de_24_other",
    ]
    assert presets[2] == {
        "key": "de_24_other",
        "name": "Landwirtschaft § 24 (7,8 %)",
        "category": "S",
        "values": [{"valid_from": "2025-01-01", "percent": "7.8"}],
        "notice": "Besteuerung nach Durchschnittssätzen (§ 24 UStG)",
        "exemption_reason": "",
        "sources": list(profile_of(Country.DE).scheme_presets[2].sources),
    }
    # Taken over once, with the Idempotency-Key of the web client.
    key = {"Idempotency-Key": str(uuid4())}
    taken = user_client.post("/api/tax-rates/presets/de_24_other", headers=key)
    assert taken.status_code == 201, taken.text
    again = user_client.post("/api/tax-rates/presets/de_24_other", headers=key)
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json() == taken.json()
    assert taken.json()["preset"] == "de_24_other"
    twice = user_client.post("/api/tax-rates/presets/de_24_other")
    assert twice.status_code == 409
    assert twice.json()["error"]["code"] == "preset_taken"
    assert [preset["key"] for preset in user_client.get("/api/tax-rates/presets").json()] == [
        "de_24_forestry",
        "de_24_beverages",
    ]


@pytest.mark.usefixtures("customer_id")
def test_lines_name_their_rate(user_client: TestClient, customer_id: str) -> None:
    exempt = str(factories.rate_id(EXEMPT))
    body = {
        "type": "invoice",
        "customer_id": customer_id,
        "lines": [
            {"description": "Kurs", "unit_price": "100", "tax_rate_id": exempt},
            {"description": "Gebühr", "unit_price": "20", "pass_through": True},
            {"description": "Beratung", "unit_price": "100"},
        ],
    }
    document = user_client.post("/api/documents", json=body).json()
    assert [
        (line["tax_rate_id"], line["tax_category"], line["tax_rate"]) for line in document["lines"]
    ] == [
        (exempt, "exempt", None),
        (None, "pass_through", None),
        (str(factories.rate_id(STANDARD)), "standard", None),
    ]
    issued = user_client.post(f"/api/documents/{document['id']}/issue").json()
    assert [line["tax_rate"] for line in issued["lines"]] == ["0", "0", "8.1"]
    unknown = {**body, "lines": [{"description": "x", "tax_rate_id": str(uuid4())}]}
    refused = user_client.post("/api/documents", json=unknown)
    assert refused.status_code == 422
    assert refused.json()["error"]["details"] == {"lines.0.tax_rate_id": "unknown tax rate"}
