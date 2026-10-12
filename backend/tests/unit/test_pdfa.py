"""PDF/A-3b and the embedded e-invoice (veraPDF checks real PDFs in `make einvoice`)."""

import io
from datetime import UTC, datetime, timedelta, timezone

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    PdfObject,
    StreamObject,
)

from rhinvoice.application.errors import UnavailableError
from rhinvoice.infrastructure.rendering.pdfa import PRODUCER, PdfInfo, to_pdfa
from tests.helpers import blank_pdf, raises_exactly

CREATED = datetime(2026, 3, 9, 10, 30, tzinfo=timezone(timedelta(hours=1)))
INFO = PdfInfo(title="Rechnung R1 <&>", author="Muster & Co.", subject="Web", created=CREATED)
XML = b'<?xml version="1.0"?><rsm:CrossIndustryInvoice/>'


def tagged_pdf() -> bytes:
    """Make a PDF with a structure tree, like Chromium's tagged output."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(blank_pdf())))
    tree = DictionaryObject({NameObject("/Type"): NameObject("/StructTreeRoot")})
    writer.root_object[NameObject("/StructTreeRoot")] = tree
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def resolved[T: PdfObject](value: object, kind: type[T]) -> T:
    """Follow a reference and check the object's type (pypdf objects are loosely typed)."""
    target = value.get_object() if isinstance(value, PdfObject) else value
    assert isinstance(target, kind)
    return target


def catalog(reader: PdfReader) -> DictionaryObject:
    return resolved(reader.trailer["/Root"], DictionaryObject)


def test_a_pdf_a_keeps_the_pages_and_tags() -> None:
    reader = PdfReader(io.BytesIO(to_pdfa(tagged_pdf(), INFO)))
    root = catalog(reader)
    assert len(reader.pages) == 1
    assert str(resolved(root["/StructTreeRoot"], DictionaryObject)["/Type"]) == "/StructTreeRoot"
    # A file identifier, twice the same when first written.
    first, second = resolved(reader.trailer["/ID"], ArrayObject)
    assert first == second
    assert first
    [intent] = resolved(root["/OutputIntents"], ArrayObject)
    intent = resolved(intent, DictionaryObject)
    assert (str(intent["/S"]), str(intent["/OutputConditionIdentifier"])) == (
        "/GTS_PDFA1",
        "sRGB IEC61966-2.1",
    )
    profile = resolved(intent["/DestOutputProfile"], StreamObject)
    assert resolved(profile["/N"], NumberObject) == 3
    assert profile.get_data()[36:40] == b"acsp"
    metadata = resolved(root["/Metadata"], StreamObject)
    assert (str(metadata["/Type"]), str(metadata["/Subtype"])) == ("/Metadata", "/XML")
    assert "/AF" not in root
    assert reader.attachments == {}


def test_the_info_and_the_xmp_agree() -> None:
    reader = PdfReader(io.BytesIO(to_pdfa(blank_pdf(), INFO)))
    assert reader.metadata == {
        "/Title": "Rechnung R1 <&>",
        "/Author": "Muster & Co.",
        "/Subject": "Web",
        "/Creator": "Rhinvoice",
        "/Producer": PRODUCER,
        # In UTC.
        "/CreationDate": "D:20260309093000Z",
        "/ModDate": "D:20260309093000Z",
    }
    xmp = reader.xmp_metadata
    assert xmp is not None
    assert xmp.dc_title == {"x-default": "Rechnung R1 <&>"}
    assert xmp.dc_creator == ["Muster & Co."]
    assert xmp.dc_description == {"x-default": "Web"}
    assert xmp.pdf_producer == PRODUCER
    assert PRODUCER.startswith("Rhinvoice ")
    assert xmp.xmp_creator_tool == "Rhinvoice"
    assert xmp.xmp_create_date == datetime(2026, 3, 9, 9, 30, tzinfo=UTC).replace(tzinfo=None)
    raw = xmp.stream.get_data().decode()
    assert "<pdfaid:part>3</pdfaid:part><pdfaid:conformance>B</pdfaid:conformance>" in raw
    assert raw.startswith('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>')
    assert raw.endswith('<?xpacket end="w"?>')
    assert "urn:factur-x" not in raw


def test_an_empty_subject_is_left_out() -> None:
    reader = PdfReader(io.BytesIO(to_pdfa(blank_pdf(), PdfInfo("T", "A", "", CREATED))))
    assert reader.metadata is not None
    assert "/Subject" not in reader.metadata
    assert reader.xmp_metadata is not None
    assert "dc:description" not in reader.xmp_metadata.stream.get_data().decode()


def test_the_e_invoice_is_embedded_as_factur_x() -> None:
    reader = PdfReader(io.BytesIO(to_pdfa(tagged_pdf(), INFO, XML)))
    assert reader.attachments == {"factur-x.xml": [XML]}
    [reference] = resolved(catalog(reader)["/AF"], ArrayObject)
    specification = resolved(reference, DictionaryObject)
    assert str(specification["/F"]) == str(specification["/UF"]) == "factur-x.xml"
    assert str(specification["/AFRelationship"]) == "/Alternative"
    assert str(specification["/Desc"]) == "Factur-X / ZUGFeRD invoice"
    files = resolved(specification["/EF"], DictionaryObject)
    embedded = resolved(files["/F"], StreamObject)
    assert str(embedded["/Type"]) == "/EmbeddedFile"
    assert str(embedded["/Subtype"]) == "/text/xml"
    params = resolved(embedded["/Params"], DictionaryObject)
    assert resolved(params["/Size"], NumberObject) == len(XML)
    assert str(params["/ModDate"]) == "D:20260309103000+01'00'"
    assert reader.xmp_metadata is not None
    raw = reader.xmp_metadata.stream.get_data().decode()
    for expected in (
        'xmlns:fx="urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#">',
        "<fx:DocumentType>INVOICE</fx:DocumentType>",
        "<fx:DocumentFileName>factur-x.xml</fx:DocumentFileName>",
        "<fx:Version>1.0</fx:Version>",
        "<fx:ConformanceLevel>EN 16931</fx:ConformanceLevel>",
        "<pdfaSchema:prefix>fx</pdfaSchema:prefix>",
        "<pdfaProperty:name>ConformanceLevel</pdfaProperty:name>",
    ):
        assert expected in raw


def test_an_unreadable_pdf_is_a_failure_of_the_pdf_service() -> None:
    with raises_exactly(UnavailableError, "the PDF service (Gotenberg) returned an unreadable PDF"):
        to_pdfa(b"%PDF-1.7 truncated", INFO)


def test_keywords_in_the_info_and_the_xmp() -> None:
    info = PdfInfo("T", "A", "", CREATED, ("Rechnung", "R1", "", "Müller & Söhne"))
    reader = PdfReader(io.BytesIO(to_pdfa(blank_pdf(), info)))
    assert reader.metadata is not None
    # Empty keywords (a draft's number) are left out.
    assert str(reader.metadata["/Keywords"]) == "Rechnung, R1, Müller & Söhne"
    assert reader.xmp_metadata is not None
    raw = reader.xmp_metadata.stream.get_data().decode()
    assert "<pdf:Keywords>Rechnung, R1, Müller &amp; Söhne</pdf:Keywords>" in raw
    without = PdfReader(io.BytesIO(to_pdfa(blank_pdf(), PdfInfo("T", "A", "", CREATED, ("",)))))
    assert without.metadata is not None
    assert "/Keywords" not in without.metadata
