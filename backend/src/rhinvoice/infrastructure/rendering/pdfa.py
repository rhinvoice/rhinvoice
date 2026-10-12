"""PDF/A-3b for archiving, with the e-invoice embedded (ZUGFeRD / Factur-X).

Chromium's PDF already embeds every font and is tagged; three things are
missing for PDF/A-3b (ISO 19005-3), checked with veraPDF: the file identifier,
an output intent with an sRGB profile and XMP metadata. They are added here
without touching the pages, so the PDF keeps the exact look and the tags of
the preview. (Gotenberg's own PDF/A conversion goes through LibreOffice, which
replaces the fonts.)

``srgb.icc`` is LittleCMS' built-in sRGB profile (IEC 61966-2-1), written with
Pillow (``ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()``);
the profile states "No copyright, use freely".

The e-invoice is attached as ``factur-x.xml`` with the relationship
"Alternative" and described in the XMP with the Factur-X extension schema
(Factur-X 1.0 / ZUGFeRD 2.x, chapter 6).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from typing import TYPE_CHECKING, cast
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    PdfObject,
    StreamObject,
    TextStringObject,
)

from rhinvoice.application.errors import UnavailableError

if TYPE_CHECKING:
    from datetime import datetime

E_INVOICE_FILE = "factur-x.xml"
FACTUR_X_NAMESPACE = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"
FACTUR_X_VERSION = "1.0"
CONFORMANCE_LEVEL = "EN 16931"
DOCUMENT_TYPE = "INVOICE"
"""Factur-X names credit notes "INVOICE" as well."""
CREATOR = "Rhinvoice"


def _producer() -> str:
    """Name the software with its version, e.g. "Rhinvoice 0.4.0" (helps with support)."""
    try:
        return f"{CREATOR} {version('rhinvoice')}"
    except PackageNotFoundError:  # pragma: no cover - only when run from a bare source tree
        return CREATOR


PRODUCER = _producer()
_PROFILE = files("rhinvoice.infrastructure.rendering").joinpath("srgb.icc").read_bytes()
_EXTENSION_PROPERTIES = (
    ("DocumentFileName", "The name of the embedded XML document"),
    ("DocumentType", "The type of the hybrid document in capital letters, e.g. INVOICE or ORDER"),
    ("Version", "The actual version of the standard applying to the embedded XML document"),
    ("ConformanceLevel", "The conformance level of the embedded XML document"),
)


@dataclass(frozen=True, slots=True)
class PdfInfo:
    """The document information, written to the info dictionary and the XMP alike."""

    title: str
    author: str
    subject: str
    created: datetime
    keywords: tuple[str, ...] = ()
    """For the search of the operating system, e.g. type, number, customer, "ZUGFeRD"."""


def _name(value: str) -> NameObject:
    return NameObject(f"/{value}")


def _stream(data: bytes, entries: dict[str, PdfObject]) -> StreamObject:
    stream = DecodedStreamObject()
    stream.set_data(data)
    for key, value in entries.items():
        stream[_name(key)] = value
    return stream


def _pdf_date(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("D:%Y%m%d%H%M%SZ")


def _keywords(info: PdfInfo) -> str:
    return ", ".join(keyword for keyword in info.keywords if keyword)


def _xmp(info: PdfInfo, *, e_invoice: bool) -> bytes:
    stamp = info.created.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    title, author, subject = escape(info.title), escape(info.author), escape(info.subject)
    keywords = f"<pdf:Keywords>{escape(_keywords(info))}</pdf:Keywords>" if _keywords(info) else ""
    description = (
        f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">{subject}</rdf:li></rdf:Alt>'
        "</dc:description>"
        if subject
        else ""
    )
    parts = [
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>',
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">',
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">',
        (
            '<rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">'
            "<pdfaid:part>3</pdfaid:part><pdfaid:conformance>B</pdfaid:conformance>"
            "</rdf:Description>"
        ),
        (
            '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:format>application/pdf</dc:format>"
            f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}</rdf:li></rdf:Alt></dc:title>'
            f"<dc:creator><rdf:Seq><rdf:li>{author}</rdf:li></rdf:Seq></dc:creator>"
            f"{description}</rdf:Description>"
        ),
        (
            '<rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">'
            f"<pdf:Producer>{PRODUCER}</pdf:Producer>{keywords}</rdf:Description>"
        ),
        (
            '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
            f"<xmp:CreatorTool>{CREATOR}</xmp:CreatorTool>"
            f"<xmp:CreateDate>{stamp}</xmp:CreateDate><xmp:ModifyDate>{stamp}</xmp:ModifyDate>"
            "</rdf:Description>"
        ),
    ]
    if e_invoice:
        properties = "".join(
            '<rdf:li rdf:parseType="Resource">'
            f"<pdfaProperty:name>{name}</pdfaProperty:name>"
            "<pdfaProperty:valueType>Text</pdfaProperty:valueType>"
            "<pdfaProperty:category>external</pdfaProperty:category>"
            f"<pdfaProperty:description>{description}</pdfaProperty:description></rdf:li>"
            for name, description in _EXTENSION_PROPERTIES
        )
        parts += [
            (
                '<rdf:Description rdf:about=""'
                ' xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/"'
                ' xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#"'
                ' xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">'
                '<pdfaExtension:schemas><rdf:Bag><rdf:li rdf:parseType="Resource">'
                "<pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>"
                f"<pdfaSchema:namespaceURI>{FACTUR_X_NAMESPACE}</pdfaSchema:namespaceURI>"
                "<pdfaSchema:prefix>fx</pdfaSchema:prefix>"
                f"<pdfaSchema:property><rdf:Seq>{properties}</rdf:Seq></pdfaSchema:property>"
                "</rdf:li></rdf:Bag></pdfaExtension:schemas></rdf:Description>"
            ),
            (
                f'<rdf:Description rdf:about="" xmlns:fx="{FACTUR_X_NAMESPACE}">'
                f"<fx:DocumentType>{DOCUMENT_TYPE}</fx:DocumentType>"
                f"<fx:DocumentFileName>{E_INVOICE_FILE}</fx:DocumentFileName>"
                f"<fx:Version>{FACTUR_X_VERSION}</fx:Version>"
                f"<fx:ConformanceLevel>{CONFORMANCE_LEVEL}</fx:ConformanceLevel>"
                "</rdf:Description>"
            ),
        ]
    parts += ["</rdf:RDF>", "</x:xmpmeta>", '<?xpacket end="w"?>']
    return "\n".join(parts).encode()


def _attach(writer: PdfWriter, xml: bytes, created: datetime) -> None:
    attachment = writer.add_attachment(E_INVOICE_FILE, xml)
    attachment.subtype = _name("text/xml")
    attachment.size = NumberObject(len(xml))
    attachment.modification_date = created
    attachment.description = TextStringObject("Factur-X / ZUGFeRD invoice")
    attachment.associated_file_relationship = _name("Alternative")
    specification = attachment.pdf_object
    specification[_name("UF")] = TextStringObject(E_INVOICE_FILE)
    writer.root_object[_name("AF")] = ArrayObject([specification.indirect_reference])


def to_pdfa(pdf: bytes, info: PdfInfo, e_invoice: bytes | None = None) -> bytes:
    """Make a PDF/A-3b of a Chromium PDF; embed the e-invoice when there is one."""
    try:
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    except PyPdfError as error:
        msg = "the PDF service (Gotenberg) returned an unreadable PDF"
        raise UnavailableError(msg) from error
    # PDF/A needs a file identifier (ISO 19005-3, 6.1.3).
    writer.generate_file_identifiers()
    profile = _stream(_PROFILE, {"N": NumberObject(3)}).flate_encode()
    intent = DictionaryObject(
        {
            _name("Type"): _name("OutputIntent"),
            _name("S"): _name("GTS_PDFA1"),
            _name("OutputConditionIdentifier"): TextStringObject("sRGB IEC61966-2.1"),
            _name("Info"): TextStringObject("sRGB IEC61966-2.1"),
            # Streams must be indirect objects; pypdf has no public way to add one.
            _name("DestOutputProfile"): writer._add_object(profile),  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        }
    )
    root = writer.root_object
    root[_name("OutputIntents")] = ArrayObject([intent])
    if e_invoice is not None:
        _attach(writer, e_invoice, info.created)
    writer.xmp_metadata = _xmp(info, e_invoice=e_invoice is not None)
    metadata = cast("StreamObject", root[_name("Metadata")].get_object())
    metadata[_name("Type")] = _name("Metadata")
    metadata[_name("Subtype")] = _name("XML")
    stamp = _pdf_date(info.created)
    # The same values as the XMP (ISO 19005-3, 6.6.2.3); an empty subject is left out of both.
    document_info = {
        "/Title": info.title,
        "/Author": info.author,
        "/Creator": CREATOR,
        "/Producer": PRODUCER,
        "/CreationDate": stamp,
        "/ModDate": stamp,
    }
    if info.subject:
        document_info["/Subject"] = info.subject
    if _keywords(info):
        document_info["/Keywords"] = _keywords(info)
    writer.add_metadata(document_info)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
