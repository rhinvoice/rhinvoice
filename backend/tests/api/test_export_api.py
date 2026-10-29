"""The export of the issued invoices of a period over the API."""

import csv
import io
import zipfile
from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from rhinvoice.api.container import Container
from rhinvoice.infrastructure.export.writer import FileExportWriter
from tests.api.conftest import CLIENT_HEADERS, EMAIL, PASSWORD, AppFactory
from tests.api.test_documents_api import LINES, FakePdf, create, post

PATH = "/api/exports/invoices"
JANUARY = {"start": "2026-01-01", "end": "2026-01-31"}


class FakePrinter:
    def print_pdf(self, page: str) -> bytes:
        return b"%PDF-1.7 " + str(len(page)).encode()


def issued(client: TestClient, customer_id: str) -> dict[str, object]:
    draft = create(client, customer_id, lines=[LINES[0]])
    return post(client, f"/api/documents/{draft['id']}/issue")


def test_the_export_requires_login(client: TestClient) -> None:
    assert client.get(PATH, params=JANUARY).status_code == 401


def test_the_company_must_be_set_up(user_client: TestClient) -> None:
    response = user_client.get(PATH, params=JANUARY)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "company_not_set_up"


def test_csv_and_excel_of_a_month(user_client: TestClient, customer_id: str) -> None:
    invoice = issued(user_client, customer_id)
    response = user_client.get(PATH, params={**JANUARY, "format": "csv", "language": "en"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        "attachment; filename=\"Invoices 2026-01.csv\"; filename*=UTF-8''Invoices%202026-01.csv"
    )
    assert response.headers["cache-control"] == "no-store"
    header, first, *_ = csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";")
    assert header[0] == "Number"
    assert first[0] == invoice["number"]
    assert first[2] == "2026-01-15"

    excel = user_client.get(PATH, params=JANUARY)
    assert excel.status_code == 200
    assert excel.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "Rechnungen%202026-01.xlsx" in excel.headers["content-disposition"]
    workbook = load_workbook(io.BytesIO(excel.content))
    assert workbook.sheetnames == ["Rechnungen", "Summen"]
    assert workbook["Rechnungen"]["A2"].value == invoice["number"]

    # Another month holds nothing.
    other = user_client.get(PATH, params={"start": "2026-02-01", "end": "2026-02-28"})
    assert load_workbook(io.BytesIO(other.content))["Rechnungen"].max_row == 1


def test_the_period_is_checked(user_client: TestClient, customer_id: str) -> None:
    assert customer_id
    reversed_period = user_client.get(PATH, params={"start": "2026-02-01", "end": "2026-01-31"})
    assert reversed_period.status_code == 422
    assert reversed_period.json()["error"]["code"] == "period_reversed"
    too_long = user_client.get(PATH, params={"start": "2016-01-01", "end": "2026-01-01"})
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "period_too_long"
    assert user_client.get(PATH, params={"start": "2026-01-01"}).status_code == 422
    unknown = user_client.get(PATH, params={**JANUARY, "format": "docx"})
    assert unknown.status_code == 422


def test_a_pdf_list_needs_the_pdf_service(
    user_client: TestClient, customer_id: str, app: FastAPI, container: Container
) -> None:
    issued(user_client, customer_id)
    unavailable = user_client.get(PATH, params={**JANUARY, "format": "pdf"})
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "unavailable"
    zipped = user_client.get(PATH, params={**JANUARY, "format": "csv", "pdfs": "true"})
    assert zipped.status_code == 503

    printing = replace(container.printing, pdf_renderer=FakePdf())
    app.state.container = replace(
        container,
        printing=printing,
        exports=replace(
            container.exports, printing=printing, writer=FileExportWriter(FakePrinter())
        ),
    )
    listed = user_client.get(PATH, params={**JANUARY, "format": "pdf"})
    assert listed.status_code == 200
    assert listed.headers["content-type"] == "application/pdf"
    assert listed.content.startswith(b"%PDF-1.7 ")


def test_with_pdfs_a_zip_holds_the_list_and_the_pdfs(
    user_client: TestClient, customer_id: str, app: FastAPI, container: Container
) -> None:
    invoice = issued(user_client, customer_id)
    printing = replace(container.printing, pdf_renderer=FakePdf())
    app.state.container = replace(container, exports=replace(container.exports, printing=printing))
    response = user_client.get(PATH, params={**JANUARY, "format": "csv", "pdfs": "true"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "Rechnungen%202026-01.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert names == ["Rechnungen 2026-01.csv", f"{invoice['number']}.pdf"]
        assert archive.read(names[1]) == f"%PDF-{invoice['number']} 1".encode()
        listed = archive.read(names[0]).decode("utf-8-sig")
    assert listed.splitlines()[0].endswith(";Datei")
    assert f";{invoice['number']}.pdf" in listed
    # The PDF was archived on the way: the document's own download returns the same.
    again = user_client.get(f"/api/documents/{invoice['id']}/pdf")
    assert again.content == f"%PDF-{invoice['number']} 1".encode()


def test_the_demo_exports_lists_but_no_pdfs(app_factory: AppFactory, customer_id: str) -> None:
    assert customer_id
    with TestClient(app_factory(demo=True), headers=CLIENT_HEADERS) as demo:
        login = demo.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert login.status_code == 200, login.text
        refused = demo.get(PATH, params={**JANUARY, "pdfs": "true"})
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "demo_locked"
        assert demo.get(PATH, params=JANUARY).status_code == 200
