"""Invoices of a program used before over HTTP: list and PDFs in, files out."""

import io
import zipfile

from fastapi.testclient import TestClient
from starlette.requests import Request

from rhinvoice.api.middleware import (
    MAX_BODY_BYTES,
    MAX_FILE_BODY_BYTES,
    MAX_IMPORT_BODY_BYTES,
    MAX_INVOICE_IMPORT_BODY_BYTES,
    _body_limit,  # pyright: ignore[reportPrivateUsage]
)
from rhinvoice.api.routers import imports
from tests.api.test_imports_api import set_up_company

LIST = (
    b"Rechnungsnummer;Betreff;Rechnungsdatum;Kunde;PLZ;Ort;Netto;Betrag;Offen\n"
    b"1;Rechnung R20150001;14.02.2015;Beispiel AG;3011;Bern;100;108;0\n"
    b"2;Rechnung R20150002;20.02.2015;Beispiel AG;3011;Bern;50;54;54\n"
)
PDF = b"%PDF-1.4 R20150001"


def zipped() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("IN/2015/Rechnung R20150002.pdf", b"%PDF-1.4 R20150002")
        package.writestr("IN/2015/Notizen.txt", b"x")
    return buffer.getvalue()


def uploads() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("file", ("Rechnungen.csv", LIST, "text/csv")),
        ("files", ("2015/Rechnung R20150001.pdf", PDF, "application/pdf")),
        ("files", ("2015/Mahnung R20150001.pdf", b"%PDF-1.4 Mahnung", "application/pdf")),
        ("files", ("2015/.DS_Store", b"\x00", "application/octet-stream")),
        ("files", ("Archiv.zip", zipped(), "application/zip")),
    ]


def test_invoices_come_with_their_pdf_files(user_client: TestClient) -> None:
    set_up_company(user_client)
    preview = user_client.post("/api/imports/invoices/preview", files=uploads())
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["mapping"]["number"] == 1
    assert body["next_number"] == "R20260001"
    assert body["unused_files"] == []
    first, second = body["rows"]
    assert (first["number"], first["file"], first["attachments"], first["new_customer"]) == (
        "R20150001",
        "2015/Rechnung R20150001.pdf",
        1,
        True,
    )
    assert second["file"] == "IN/2015/Rechnung R20150002.pdf"
    assert user_client.get("/api/documents?type=invoice").json()["total"] == 0

    imported = user_client.post("/api/imports/invoices", files=uploads())
    assert imported.status_code == 200, imported.text
    listed = user_client.get("/api/documents?type=invoice").json()
    numbers = {item["number"]: item for item in listed["items"]}
    assert all(item["imported"] for item in listed["items"])
    document_id = numbers["R20150001"]["id"]

    detail = user_client.get(f"/api/documents/{document_id}").json()
    assert (detail["imported"], detail["has_pdf"], detail["lines"]) == (True, True, [])
    pdf = user_client.get(f"/api/documents/{document_id}/pdf")
    assert pdf.content == PDF
    assert user_client.get(f"/api/documents/{document_id}/html").status_code == 409

    [attachment] = user_client.get(f"/api/documents/{document_id}/attachments").json()
    assert (attachment["file_name"], attachment["size"]) == ("2015/Mahnung R20150001.pdf", 16)
    file = user_client.get(
        f"/api/documents/{document_id}/attachments/{attachment['id']}?download=true"
    )
    assert file.content == b"%PDF-1.4 Mahnung"
    assert file.headers["content-type"] == "application/pdf"
    assert file.headers["content-disposition"] == (
        "attachment; filename=\"Mahnung R20150001.pdf\"; filename*=UTF-8''Mahnung%20R20150001.pdf"
    )
    assert file.headers["etag"] == f'"{attachment["sha256"]}"'
    inline = user_client.get(f"/api/documents/{document_id}/attachments/{attachment['id']}")
    assert inline.headers["content-disposition"].startswith("inline; ")
    missing = user_client.get(
        f"/api/documents/{document_id}/attachments/00000000-0000-0000-0000-000000000000"
    )
    assert missing.status_code == 404


def test_a_pdf_is_added_to_an_imported_invoice(user_client: TestClient) -> None:
    set_up_company(user_client)
    plain = b"Nummer;Datum;Kunde;PLZ;Ort;Betrag\nR20150001;14.02.2015;Beispiel AG;3011;Bern;108\n"
    user_client.post("/api/imports/invoices", files=[("file", ("r.csv", plain, "text/csv"))])
    listed = user_client.get("/api/documents?type=invoice").json()["items"]
    document_id = next(item["id"] for item in listed if item["number"] == "R20150001")
    assert user_client.get(f"/api/documents/{document_id}").json()["has_pdf"] is False
    assert user_client.get(f"/api/documents/{document_id}/pdf").status_code == 409

    added = user_client.post(
        f"/api/documents/{document_id}/files",
        files={"file": ("C:\\Scans\\Scan_0042.pdf", PDF, "application/pdf")},
    )
    assert added.status_code == 200, added.text
    assert added.json()["has_pdf"] is True
    assert added.json()["events"][-1] == {
        "at": added.json()["events"][-1]["at"],
        "kind": "file_added",
        "detail": "Scan_0042.pdf",
    }
    assert user_client.get(f"/api/documents/{document_id}/pdf").content == PDF
    nameless = user_client.post(
        f"/api/documents/{document_id}/files",
        files={"file": ("Scans/", b"%PDF-1.4 other", "application/pdf")},
    )
    assert nameless.status_code == 200, nameless.text
    [attachment] = user_client.get(f"/api/documents/{document_id}/attachments").json()
    assert attachment["file_name"] == "document.pdf"
    refused = user_client.post(
        f"/api/documents/{document_id}/files",
        files={"file": ("x.png", b"\x89PNG", "image/png")},
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "not_a_pdf"


def test_too_many_upload_bytes_are_refused(user_client: TestClient, monkeypatch: object) -> None:

    set_up_company(user_client)
    setattr_ = monkeypatch.setattr  # type: ignore[attr-defined]
    setattr_(imports, "MAX_UPLOAD_BYTES", len(PDF))
    refused = user_client.post(
        "/api/imports/invoices/preview",
        files=[
            ("file", ("r.csv", LIST, "text/csv")),
            ("files", ("a/R20150001.pdf", PDF, "application/pdf")),
            ("files", ("a/R20150002.pdf", PDF, "application/pdf")),
        ],
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "file_too_large"


def request(path: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": path, "headers": []})


def test_imports_and_files_may_be_larger_than_other_requests() -> None:
    assert _body_limit(request("/api/customers")) == MAX_BODY_BYTES
    assert _body_limit(request("/api/imports/customers/preview")) == MAX_IMPORT_BODY_BYTES
    assert _body_limit(request("/api/imports/invoices/preview")) == MAX_INVOICE_IMPORT_BODY_BYTES
    assert _body_limit(request("/api/imports/invoices")) == MAX_INVOICE_IMPORT_BODY_BYTES
    assert _body_limit(request("/api/documents/1/files")) == MAX_FILE_BODY_BYTES
    assert _body_limit(request("/api/documents/1/pdf")) == MAX_BODY_BYTES
    # The public demo takes no uploads at all; it never reads large bodies.
    for path in ("/api/imports/invoices", "/api/imports/customers", "/api/documents/1/files"):
        assert _body_limit(request(path), demo=True) == MAX_BODY_BYTES
