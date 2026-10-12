import json

from fastapi.testclient import TestClient

ADDRESS = {"postal_code": "8001", "city": "Zürich", "country": "CH"}
CUSTOMERS = (
    "KdNr;Firma;Strasse;PLZ_Ort;Bemerkung\n"
    "10042;Bergbahnen Muster AG;Dorfstrasse 1;CH-9470 Buchs SG;Stammkunde (Müller)\n"
    "10017;Holzbau Beispiel GmbH;Feldweg 3;;\n"
).encode("cp1252")


def upload(content: bytes = CUSTOMERS) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("kunden.csv", content, "text/csv")}


def set_up_company(client: TestClient) -> None:
    saved = client.put(
        "/api/company", json={"name": "Muster GmbH", "address": ADDRESS, "default_currency": "CHF"}
    )
    assert saved.status_code == 200, saved.text


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.post("/api/imports/customers/preview", files=upload()).status_code == 401
    assert client.post("/api/imports/customers", files=upload()).status_code == 401
    assert client.get("/api/imports/customers/templates").status_code == 401


def test_preview_then_import(user_client: TestClient) -> None:
    set_up_company(user_client)
    preview = user_client.post("/api/imports/customers/preview", files=upload())
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert (body["file_type"], body["encoding"], body["delimiter"]) == ("csv", "Windows-1252", ";")
    assert body["headers"] == ["KdNr", "Firma", "Strasse", "PLZ_Ort", "Bemerkung"]
    assert body["sample"][0][1] == "Bergbahnen Muster AG"
    assert body["mapping"] == {
        "number": 0,
        "company_name": 1,
        "street": 2,
        "postal_city": 3,
        "note": 4,
    }
    assert {"key": "company_name", "required": False} in body["fields"]
    assert body["counts"] == {"new": 1, "updated": 0, "skipped": 0, "error": 1}
    assert body["rows"][0] == {
        "row": 2,
        "status": "new",
        "number": "10042",
        "name": "Bergbahnen Muster AG",
        "detail": "9470 Buchs SG",
        "problem": None,
    }
    problem = body["rows"][1]["problem"]
    assert (problem["field"], problem["code"], problem["value"]) == ("postal_code", "required", "")
    assert not body["committed"]
    assert user_client.get("/api/customers").json()["total"] == 0

    imported = user_client.post(
        "/api/imports/customers", files=upload(), data={"duplicates": "update"}
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["committed"]
    assert user_client.get("/api/customers").json()["total"] == 1
    again = user_client.post(
        "/api/imports/customers", files=upload(), data={"duplicates": "update"}
    ).json()
    assert again["counts"] == {"new": 0, "updated": 1, "skipped": 0, "error": 1}


def test_the_mapping_can_be_chosen(user_client: TestClient) -> None:
    set_up_company(user_client)
    mapping = {"company_name": 1, "city": 3}
    body = user_client.post(
        "/api/imports/customers/preview",
        files=upload(),
        data={"mapping": json.dumps(mapping)},
    ).json()
    assert body["mapping"] == mapping
    for invalid in ("[1, 2]", '{"city": "drei"}', "nicht json"):
        refused = user_client.post(
            "/api/imports/customers/preview", files=upload(), data={"mapping": invalid}
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "invalid_mapping"
    incomplete = user_client.post(
        "/api/imports/customers/preview", files=upload(), data={"mapping": '{"city": 3}'}
    ).json()
    # The test run shows the columns to map instead of failing.
    assert (incomplete["missing"], incomplete["rows"]) == (
        [["number", "company_name", "last_name"]],
        [],
    )
    refused = user_client.post(
        "/api/imports/customers", files=upload(), data={"mapping": '{"city": 3}'}
    )
    assert refused.json()["error"]["code"] == "mapping_incomplete"


def test_unreadable_and_large_files_are_refused(user_client: TestClient) -> None:
    set_up_company(user_client)
    empty = user_client.post("/api/imports/articles/preview", files=upload(b""))
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "empty_file"
    large = user_client.post(
        "/api/imports/articles/preview", files=upload(b"a;b\n" * (5 * 1024 * 1024 // 4 + 1))
    )
    assert large.json()["error"]["code"] == "file_too_large"


def test_articles(user_client: TestClient) -> None:
    set_up_company(user_client)
    content = b"Bezeichnung;Einheit;Preis\nBeratung;Std.;120,00\n"
    body = user_client.post("/api/imports/articles", files=upload(content)).json()
    assert body["rows"][0]["detail"] == "CHF 120.00"
    assert {"key": "name", "required": True} in body["fields"]


def test_import_needs_a_company(user_client: TestClient) -> None:
    refused = user_client.post("/api/imports/customers/preview", files=upload())
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "company_not_set_up"


def test_templates(user_client: TestClient) -> None:
    created = user_client.post(
        "/api/imports/customers/templates",
        json={"name": "Altes Programm", "columns": {"number": "KdNr", "postal_city": "PLZ_Ort"}},
    )
    assert created.status_code == 201, created.text
    template = created.json()
    assert template["target"] == "customers"
    listed = user_client.get("/api/imports/customers/templates").json()
    assert [t["name"] for t in listed] == ["Altes Programm"]
    assert user_client.get("/api/imports/articles/templates").json() == []
    duplicate = user_client.post(
        "/api/imports/customers/templates",
        json={"name": "altes programm", "columns": {"city": "Ort"}},
    )
    assert duplicate.status_code == 409
    too_many = {f"x{index}": "Spalte" for index in range(51)}
    oversized = user_client.post(
        "/api/imports/customers/templates", json={"name": "Gross", "columns": too_many}
    )
    assert oversized.status_code == 422
    deleted = user_client.delete(f"/api/imports/templates/{template['id']}")
    assert deleted.status_code == 204
    assert user_client.delete(f"/api/imports/templates/{template['id']}").status_code == 404
