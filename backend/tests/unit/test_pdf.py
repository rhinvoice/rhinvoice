"""The Gotenberg adapter, against a simulated Gotenberg (httpx.MockTransport)."""

import io
from collections.abc import Callable
from dataclasses import replace
from email.parser import BytesParser
from email.policy import HTTP
from uuid import UUID

import httpx
import pytest
from pypdf import PdfReader

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.document.printing import PrintHandlers, PrintModel
from rhinvoice.application.errors import UnavailableError
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.language import Language
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from rhinvoice.infrastructure.rendering.pdf import (
    GotenbergPdfRenderer,
    pdf_file_name,
    pdf_title,
)
from rhinvoice.infrastructure.rendering.pdfa import PRODUCER
from tests.helpers import blank_pdf, raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)
LINE = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="100")


def printing_for(store: Store) -> PrintHandlers:
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    clock = FixedClock(NOW)

    def uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    documents = DocumentHandlers(uow=uow, clock=clock)
    return PrintHandlers(
        uow=uow, clock=clock, documents=documents, renderer=JinjaDocumentRenderer()
    )


def draft(**overrides: object) -> DraftInput:
    values: dict[str, object] = {"customer_id": CUSTOMER, "lines": (LINE,), "subject": "Web"}
    values.update(overrides)
    return DraftInput(**values)  # type: ignore[arg-type]  # test builder


def model(store: Store, **overrides: object) -> PrintModel:
    printing = printing_for(store)
    return printing.model(printing.documents.preview(DocumentType.INVOICE, draft(**overrides)).view)


def form_fields(request: httpx.Request) -> dict[str, bytes]:
    """Split a multipart request into its parts by name."""
    content_type = request.headers["content-type"]
    message = BytesParser(policy=HTTP).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + request.content
    )
    fields: dict[str, bytes] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        payload = part.get_payload(decode=True)
        assert isinstance(name, str)
        assert isinstance(payload, bytes)
        fields[name] = payload
    return fields


def test_pdf_title(store: Store) -> None:
    assert pdf_title(model(store)) == "Rechnung (Entwurf)"
    printing = printing_for(store)
    created = printing.documents.create(DocumentType.QUOTE, draft()).document
    issued = printing.documents.issue(created.id)
    assert pdf_title(printing.model(issued)) == f"Angebot {issued.document.number}"


def test_the_page_is_sent_to_gotenberg(store: Store) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=blank_pdf(), headers={"content-type": "application/pdf"})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    html = JinjaDocumentRenderer()
    renderer = GotenbergPdfRenderer("http://gotenberg:3000/", html, client)
    printed = model(store, language=Language.EN)
    content = renderer.pdf(printed, b"<invoice/>")
    [request] = requests
    assert str(request.url) == "http://gotenberg:3000/forms/chromium/convert/html"
    assert request.method == "POST"
    fields = form_fields(request)
    assert fields["files"].decode() == html.html(printed)
    assert fields["paperWidth"] == b"8.27"
    assert fields["paperHeight"] == b"11.69"
    assert fields["generateTaggedPdf"] == b"true"
    assert fields["preferCssPageSize"] == b"true"
    assert "metadata" not in fields
    # Made a PDF/A afterwards, with the metadata and the e-invoice.
    reader = PdfReader(io.BytesIO(content))
    assert reader.metadata == {
        "/Title": "Invoice (Draft)",
        "/Author": "Muster GmbH",
        "/Subject": "Web",
        "/Creator": "Rhinvoice",
        "/Producer": PRODUCER,
        # For the search of the operating system; a draft has no number yet.
        "/Keywords": "Invoice, Beispiel AG, ZUGFeRD",
        "/CreationDate": "D:20260309090000Z",
        "/ModDate": "D:20260309090000Z",
    }
    assert reader.attachments == {"factur-x.xml": [b"<invoice/>"]}
    assert renderer.pdf(printed)  # without e-invoice


def fails(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, text="chromium crashed")


def answers_html(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<html>proxy login</html>")


def answers_no_pdf(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"<html>", headers={"content-type": "application/pdf"})


def refuses(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


@pytest.mark.parametrize(
    ("respond", "message"),
    [
        (fails, "the PDF service (Gotenberg) failed with status 500"),
        (refuses, "the PDF service (Gotenberg) is not reachable"),
        (answers_html, "the PDF service (Gotenberg) did not return a PDF"),
        (answers_no_pdf, "the PDF service (Gotenberg) did not return a PDF"),
    ],
)
def test_failures_of_gotenberg_are_reported(
    store: Store, respond: Callable[[httpx.Request], httpx.Response], message: str
) -> None:
    client = httpx.Client(transport=httpx.MockTransport(respond))
    renderer = GotenbergPdfRenderer("http://gotenberg:3000", JinjaDocumentRenderer(), client)
    with raises_exactly(UnavailableError, message):
        renderer.pdf(model(store))


@pytest.fixture
def store() -> Store:
    return Store()


def test_without_a_client_a_default_one_is_used(store: Store) -> None:
    # Port 9 (discard) refuses connections on any normal machine.
    renderer = GotenbergPdfRenderer("http://127.0.0.1:9", JinjaDocumentRenderer())
    with raises_exactly(UnavailableError, "the PDF service (Gotenberg) is not reachable"):
        renderer.pdf(model(store))


def test_pdf_file_names(store: Store) -> None:
    printing = printing_for(store)
    draft_document = printing.documents.create(DocumentType.INVOICE, draft()).document
    assert pdf_file_name(draft_document) == "Rechnung (Entwurf).pdf"
    english = printing.documents.create(DocumentType.QUOTE, draft(language=Language.EN)).document
    assert pdf_file_name(english) == "Quote (Draft).pdf"
    numbered = replace(draft_document, number='R/2026:01*?"<>|\\x')
    assert pdf_file_name(numbered) == "Rechnung R-2026-01-------x.pdf"
