"""The company's units over the API (ADR 0046)."""

from typing import Any

from fastapi.testclient import TestClient

from rhinvoice.domain.catalog.unit_presets import PRESETS, START
from tests.unit.domain import factories

type Json = dict[str, Any]

QUINTAL = {
    "label": "dz",
    "code": "DTN",
    "labels": {"de": "", "en": "dt", "fr": "q", "it": "q"},
    "description": "Doppelzentner (100 kg)",
}


def test_units_need_a_login(client: TestClient) -> None:
    unit_id = factories.unit_id()
    for method, path in (
        ("GET", "/api/units"),
        ("POST", "/api/units"),
        ("GET", "/api/units/codes"),
        ("GET", "/api/units/presets"),
        ("POST", "/api/units/presets"),
        ("PUT", "/api/units/order"),
        ("PUT", f"/api/units/{unit_id}"),
        ("POST", f"/api/units/{unit_id}/remove"),
        ("POST", f"/api/units/{unit_id}/show"),
    ):
        assert client.request(method, path).status_code == 401, path


def test_every_installation_starts_with_the_units_of_before(user_client: TestClient) -> None:
    units = user_client.get("/api/units").json()
    assert [unit["code"] for unit in units] == [preset.key for preset in START]
    assert units[0] == {
        "id": str(factories.unit_id("C62")),
        "code": "C62",
        "label": "Stk.",
        "labels": {"de": "", "en": "pcs", "fr": "pce", "it": "pz."},
        "description": "",
        "preset": "C62",
        "hidden": False,
        "in_use": False,
    }
    codes = user_client.get("/api/units/codes").json()
    assert len(codes) == 2162
    assert {"code": "DTN", "name": "decitonne"} in codes


def test_own_units_are_added_changed_sorted_and_removed(user_client: TestClient) -> None:
    created = user_client.post("/api/units", json=QUINTAL)
    assert created.status_code == 201, created.text
    quintal = created.json()
    assert {key: quintal[key] for key in QUINTAL} == QUINTAL
    assert (quintal["preset"], quintal["hidden"], quintal["in_use"]) == (None, False, False)
    changed = user_client.put(
        f"/api/units/{quintal['id']}", json={"label": "Dz.", "code": "DTN"}
    ).json()
    assert (changed["label"], changed["labels"], changed["description"]) == (
        "Dz.",
        {"de": "", "en": "", "fr": "", "it": ""},
        "",
    )
    ids = [unit["id"] for unit in user_client.get("/api/units").json()]
    order = [ids[-1], *ids[:-1]]
    sorted_units = user_client.put("/api/units/order", json={"unit_ids": order}).json()
    assert [unit["id"] for unit in sorted_units] == order
    assert user_client.post(f"/api/units/{quintal['id']}/remove").json() == {"removal": "deleted"}
    assert len(user_client.get("/api/units").json()) == len(START)


def test_refused_units_say_why(user_client: TestClient) -> None:
    def error(response: Any) -> tuple[int, str]:  # noqa: ANN401 - a test client response
        return response.status_code, response.json()["error"]["code"]

    assert error(user_client.post("/api/units", json={**QUINTAL, "code": "HAR"})) == (
        422,
        "unit_code_unknown",
    )
    assert error(user_client.post("/api/units", json={**QUINTAL, "code": "dz"})) == (
        422,
        "validation_error",
    )
    assert error(user_client.post("/api/units", json={**QUINTAL, "label": "STK."})) == (
        409,
        "unit_label_taken",
    )
    assert error(user_client.put("/api/units/order", json={"unit_ids": []})) == (
        422,
        "unit_order_incomplete",
    )
    only = [unit["id"] for unit in user_client.get("/api/units").json()]
    for unit_id in only[1:]:
        user_client.post(f"/api/units/{unit_id}/remove")
    assert error(user_client.post(f"/api/units/{only[0]}/remove")) == (409, "unit_last_visible")
    assert error(user_client.post("/api/units/presets", json={"keys": ["har"]})) == (
        422,
        "validation_error",
    )
    assert error(user_client.post("/api/units/presets", json={"keys": ["QTL"]})) == (
        404,
        "unit_preset_unknown",
    )
    assert (
        user_client.put(f"/api/units/{factories.unit_id('XXX')}", json=QUINTAL).status_code == 404
    )


def test_units_in_use_are_hidden_and_come_back(user_client: TestClient, customer_id: str) -> None:
    hours = str(factories.unit_id("HUR"))
    line = {"description": "Beratung", "unit_price": "80", "unit_id": hours}
    body = {"type": "invoice", "customer_id": customer_id, "lines": [line]}
    draft = user_client.post("/api/documents", json=body).json()
    assert (draft["lines"][0]["unit_id"], draft["lines"][0]["unit_code"]) == (hours, "HUR")
    assert draft["lines"][0]["unit_label"] == "Std."
    assert user_client.post(f"/api/units/{hours}/remove").json() == {"removal": "hidden"}
    # The line keeps its unit; the catalogue offers it again.
    again = user_client.get(f"/api/documents/{draft['id']}").json()
    assert again["lines"][0]["unit_label"] == "Std."
    offers = user_client.get("/api/units/presets").json()
    assert [offer["key"] for offer in offers[: len(PRESETS) - len(START)]] == [
        preset.key for preset in PRESETS[len(START) :]
    ]
    assert offers[-1] == {
        "key": None,
        "unit_id": hours,
        "group": "time",
        "code": "HUR",
        "label": "Std.",
        "names": {"de": "Stunde", "en": "hour", "fr": "heure", "it": "ora"},
        "description": "",
    }
    taken = user_client.post("/api/units/presets", json={"keys": ["DTN"], "unit_ids": [hours]})
    assert [unit["code"] for unit in taken.json()][-2:] == ["HUR", "DTN"]
    hidden = user_client.post(f"/api/units/{hours}/remove").json()
    assert hidden == {"removal": "hidden"}
    shown = user_client.post(f"/api/units/{hours}/show").json()
    assert (shown["hidden"], shown["in_use"]) == (False, True)
