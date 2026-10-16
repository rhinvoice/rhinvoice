from fastapi.testclient import TestClient

from tests.unit.domain.factories import CH_IBAN, CH_QR_IBAN

ADDRESS = {
    "street": "Bahnhofstrasse",
    "house_number": "1",
    "postal_code": "8001",
    "city": "Zürich",
    "country": "CH",
}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_endpoints_require_login(client: TestClient) -> None:
    for path in (
        "/api/company",
        "/api/customers",
        "/api/articles",
        "/api/bank-accounts",
        "/api/number-sequences",
    ):
        assert client.get(path).status_code == 401, path


def test_company_lifecycle(user_client: TestClient) -> None:
    missing = user_client.get("/api/company")
    assert missing.status_code == 404
    assert missing.json()["error"]["message"] == "the company has not been set up yet"
    body = {
        "name": "Muster GmbH",
        "address": ADDRESS,
        "default_currency": "CHF",
        "email": "info@muster.example",
        "vat_number": "CHE-123.456.788 MWST",
    }
    saved = user_client.put("/api/company", json=body)
    assert saved.status_code == 200, saved.text
    company = saved.json()
    assert company["country"] == "CH"
    assert company["vat_number"] == "CHE-123.456.788 MWST"
    # The 5-centime rounding is a choice, off unless switched on.
    assert company["cash_rounding"] is False
    assert user_client.get("/api/company").json() == company


def test_unknown_country_codes_are_rejected(user_client: TestClient) -> None:
    body = {"kind": "company", "company_name": "X", "address": {**ADDRESS, "country": "XX"}}
    response = user_client.post("/api/customers", json=body)
    assert response.status_code == 422
    assert "address.country" in response.json()["error"]["details"]


def test_company_must_be_in_a_supported_country(user_client: TestClient) -> None:
    body = {"name": "X", "address": {**ADDRESS, "country": "FR"}, "default_currency": "EUR"}
    response = user_client.put("/api/company", json=body)
    assert response.status_code == 422
    assert "address.country" in response.json()["error"]["details"]


def test_invalid_vat_number_is_a_domain_validation_error(user_client: TestClient) -> None:
    body = {
        "name": "X",
        "address": ADDRESS,
        "default_currency": "CHF",
        "vat_number": "CHE-123.456.789",
    }
    response = user_client.put("/api/company", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {
        "vat_number": "the check digit of the Swiss UID is wrong"
    }


def test_logo_upload(user_client: TestClient) -> None:
    assert user_client.get("/api/company/logo").status_code == 404
    uploaded = user_client.put("/api/company/logo", files={"file": ("logo.png", PNG, "image/png")})
    assert uploaded.status_code == 200
    assert uploaded.json() == {"media_type": "image/png", "size": len(PNG)}
    logo = user_client.get("/api/company/logo")
    assert logo.content == PNG
    assert logo.headers["content-type"] == "image/png"
    rejected = user_client.put(
        "/api/company/logo", files={"file": ("x.svg", b"<svg/>", "image/svg+xml")}
    )
    assert rejected.status_code == 422
    assert user_client.delete("/api/company/logo").status_code == 204
    assert user_client.get("/api/company/logo").status_code == 404


def test_logo_size_limit(user_client: TestClient) -> None:
    huge = PNG + b"\x00" * (1024 * 1024)
    response = user_client.put("/api/company/logo", files={"file": ("big.png", huge, "image/png")})
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"logo": "the logo must be at most 1 MB"}


def test_bank_accounts(user_client: TestClient) -> None:
    created = user_client.post(
        "/api/bank-accounts",
        json={
            "currency": "CHF",
            "bank_name": "Musterbank",
            "holder": "Muster",
            "iban": CH_IBAN,
            "qr_iban": CH_QR_IBAN,
        },
    )
    assert created.status_code == 201, created.text
    account = created.json()
    assert account["is_default"] is True
    assert account["iban_formatted"] == "CH93 0076 2011 6238 5295 7"
    updated = user_client.put(
        f"/api/bank-accounts/{account['id']}",
        json={
            "currency": "CHF",
            "bank_name": "Neue Bank",
            "holder": "Muster",
            "iban": CH_IBAN,
            "bic": "UBSWCHZH80A",
        },
    )
    assert updated.json()["bank_name"] == "Neue Bank"
    assert updated.json()["qr_iban"] is None
    assert [a["id"] for a in user_client.get("/api/bank-accounts").json()] == [account["id"]]
    bad = user_client.post(
        "/api/bank-accounts",
        json={"currency": "CHF", "bank_name": "X", "holder": "X", "iban": "CH9300762011623852958"},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["details"] == {
        "iban": "IBAN check digits are wrong, please check for typos"
    }
    assert user_client.delete(f"/api/bank-accounts/{account['id']}").status_code == 204
    assert user_client.delete(f"/api/bank-accounts/{account['id']}").status_code == 404


def test_customers(user_client: TestClient) -> None:
    body = {
        "kind": "company",
        "company_name": "Müller AG",
        "contact_person": "Frau Muster",
        "address": ADDRESS,
        "delivery_address": {**ADDRESS, "country": "LI", "city": "Vaduz", "postal_code": "9490"},
        "default_discount": "2.5",
        "default_currency": "EUR",
    }
    created = user_client.post("/api/customers", json=body)
    assert created.status_code == 201, created.text
    customer = created.json()
    assert customer["number"] == "1001"
    assert customer["display_name"] == "Müller AG"
    assert customer["default_discount"] == "2.5"
    assert customer["delivery_address"]["city"] == "Vaduz"
    assert user_client.get(f"/api/customers/{customer['id']}").json() == customer

    person = user_client.post(
        "/api/customers",
        json={
            "kind": "person",
            "first_name": "Max",
            "last_name": "Muster",
            "address": ADDRESS,
            "email": "max@example.com",
        },
    ).json()
    assert person["display_name"] == "Max Muster"

    page = user_client.get("/api/customers", params={"q": "muller"}).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == customer["id"]
    by_name = user_client.get("/api/customers", params={"sort": "name", "direction": "desc"}).json()
    assert [c["id"] for c in by_name["items"]] == [person["id"], customer["id"]]

    archived = user_client.post(f"/api/customers/{customer['id']}/archive").json()
    assert archived["archived"] is True
    assert user_client.get("/api/customers").json()["total"] == 1
    assert user_client.get("/api/customers", params={"include_archived": True}).json()["total"] == 2
    assert user_client.post(f"/api/customers/{customer['id']}/restore").json()["archived"] is False

    renamed = user_client.put(
        f"/api/customers/{customer['id']}", json={**body, "company_name": "Müller & Co."}
    )
    assert renamed.json()["company_name"] == "Müller & Co."
    assert renamed.json()["number"] == "1001"

    duplicate = user_client.post("/api/customers", json={**body, "number": "1001"})
    assert duplicate.status_code == 409
    assert user_client.get("/api/customers/00000000-0000-0000-0000-000000000000").status_code == 404


def test_customer_validation(user_client: TestClient) -> None:
    response = user_client.post("/api/customers", json={"kind": "company", "address": ADDRESS})
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"company_name": "company_name is required"}
    bad_discount = user_client.post(
        "/api/customers",
        json={
            "kind": "company",
            "company_name": "X",
            "address": ADDRESS,
            "default_discount": "101",
        },
    )
    assert bad_discount.status_code == 422
    unknown_param = user_client.get("/api/customers", params={"limit": 0})
    assert unknown_param.status_code == 422


def test_articles(user_client: TestClient) -> None:
    created = user_client.post(
        "/api/articles",
        json={
            "name": "Beratung",
            "unit": "HUR",
            "prices": {"CHF": "150.00", "EUR": "160"},
            "group": "Dienstleistung",
        },
    )
    assert created.status_code == 201, created.text
    article = created.json()
    assert article["number"] == "1"
    assert article["unit_label_de"] == "Std."
    assert article["prices"] == {"CHF": "150.00", "EUR": "160.00"}
    assert user_client.get(f"/api/articles/{article['id']}").json() == article
    assert article["tax_category"] == "standard"
    updated = user_client.put(
        f"/api/articles/{article['id']}", json={"name": "Beratung Senior", "prices": {"CHF": "180"}}
    )
    assert updated.json()["prices"] == {"CHF": "180.00"}
    precise = user_client.post(
        "/api/articles", json={"name": "Schraube", "prices": {"CHF": "0.1234"}}
    )
    assert precise.json()["prices"] == {"CHF": "0.1234"}
    assert user_client.get(f"/api/articles/{precise.json()['id']}").json()["prices"] == {
        "CHF": "0.1234"
    }
    assert updated.json()["unit"] == "C62"
    assert user_client.get("/api/articles", params={"q": "senior"}).json()["total"] == 1
    assert user_client.post(f"/api/articles/{article['id']}/archive").json()["archived"] is True
    assert user_client.get("/api/articles").json()["total"] == 1
    assert user_client.post(f"/api/articles/{article['id']}/restore").json()["archived"] is False
    assert user_client.get(f"/api/articles/{article['id']}").json()["name"] == "Beratung Senior"
    invalid = user_client.post("/api/articles", json={"name": "X", "prices": {"CHF": "1.00001"}})
    assert invalid.status_code == 422


def test_number_sequences(user_client: TestClient) -> None:
    sequences = {s["kind"]: s for s in user_client.get("/api/number-sequences").json()}
    assert sequences["invoice"]["next_number"] == "R20260001"
    assert sequences["invoice"]["next_value"] == 1
    config = {
        "pattern": "RE-{YY}-{NNNNN}",
        "start_value": 1,
        "yearly_reset": True,
        "next_value": 345,
    }
    preview = user_client.post("/api/number-sequences/invoice/preview", json=config)
    assert preview.json() == {"next_number": "RE-26-00345"}
    saved = user_client.put("/api/number-sequences/invoice", json=config)
    assert saved.json()["next_number"] == "RE-26-00345"
    assert saved.json()["next_value"] == 345
    invalid = user_client.put("/api/number-sequences/invoice", json={**config, "pattern": "{NNNN}"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]["pattern"].startswith("a yearly reset needs")


def test_reference_data(user_client: TestClient) -> None:
    units = user_client.get("/api/reference/units").json()
    hours = {"code": "HUR", "label_de": "Std.", "label_en": "h", "label_fr": "h", "label_it": "h"}
    assert hours in units
    countries = user_client.get("/api/reference/countries").json()
    assert "CH" in countries
    assert "LI" in countries
    assert countries == sorted(countries)


def test_country_profiles(user_client: TestClient) -> None:
    profiles = {p["country"]: p for p in user_client.get("/api/reference/country-profiles").json()}
    assert list(profiles) == ["CH", "LI", "DE", "AT"]
    swiss = profiles["CH"]
    assert swiss["vat_system"] == "swiss"
    assert swiss["vat_area"] == ["CH", "LI"]
    assert swiss["rates"] == {"standard": "8.1", "reduced": "2.6", "special": "3.8"}
    assert swiss["terms"]["de"]["tax_name"] == "MWST"
    assert swiss["terms"]["en"]["special_rate"] == "Accommodation rate"
    assert swiss["payment_codes"] == ["epc_to_eea", "swiss_qr_bill"]
    assert swiss["number_style"] == "apostrophe"
    assert (swiss["default_currency"], swiss["cash_rounding"], swiss["tax_number"]) == (
        "CHF",
        True,
        False,
    )
    german = profiles["DE"]
    assert german["rates"] == {"standard": "19", "reduced": "7", "special": None}
    assert german["terms"]["de"]["vat_number_label"] == "USt-IdNr."
    assert german["terms"]["de"]["special_rate"] is None
    assert (german["payment_codes"], german["tax_number"]) == (["epc"], True)
    assert profiles["AT"]["rates"]["special"] == "13"


def test_number_conflicts_point_to_the_number_field(user_client: TestClient) -> None:
    body = {"kind": "company", "company_name": "X", "address": ADDRESS, "number": "7"}
    assert user_client.post("/api/customers", json=body).status_code == 201
    conflict = user_client.post("/api/customers", json=body)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"] == {"number": "customer number 7 is already taken"}
    article = {"name": "A", "number": "7"}
    assert user_client.post("/api/articles", json=article).status_code == 201
    assert user_client.post("/api/articles", json=article).json()["error"]["details"] == {
        "number": "article number 7 is already taken",
    }
