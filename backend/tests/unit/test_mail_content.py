"""What mails carry: placeholder values as printed, the PDF and the XRechnung."""

from dataclasses import replace

from rhinvoice.domain.text.template import Placeholder
from rhinvoice.infrastructure.einvoice.cii import CiiWriter
from rhinvoice.infrastructure.mail.content import PrintedMailContent
from tests.api.test_documents_api import FakePdf
from tests.einvoice_samples import issue, samples


def test_an_invoice_for_an_authority_carries_its_xrechnung() -> None:
    printing, document_id = issue(samples()["de-authority"])
    printing = replace(printing, pdf_renderer=FakePdf(), e_invoices=CiiWriter())
    content = PrintedMailContent(printing)
    view = printing.documents.get(document_id)
    number = view.document.issued_number
    values = content.document_values(view)
    assert values.file_name == f"Rechnung {number}.pdf"
    assert values.placeholders[Placeholder.NUMBER] == number
    assert values.placeholders[Placeholder.DUE_DATE] == "01.04.2026"
    assert values.placeholders[Placeholder.COMPANY] == "Beispiel Software GmbH"
    pdf, xml = content.document_files(document_id, xrechnung=True)
    assert (pdf.name, pdf.media_type) == (f"Rechnung {number}.pdf", "application/pdf")
    assert pdf.content.startswith(b"%PDF-")
    assert (xml.name, xml.media_type) == (f"XRechnung {number}.xml", "application/xml")
    assert xml.content.startswith(b"<?xml")
    # The same archived PDF again, without the XML.
    assert content.document_files(document_id, xrechnung=False) == (pdf,)
