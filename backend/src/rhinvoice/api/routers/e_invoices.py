"""E-invoices of issued invoices: what is embedded, what is missing, XRechnung."""

from typing import Self
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Response

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.document.einvoice import EInvoiceProblem, EInvoiceProfile
from rhinvoice.application.document.printing import EInvoiceStatus
from rhinvoice.infrastructure.rendering.pdf import file_name

router = APIRouter(prefix="/api", tags=["e-invoices"], responses=ERROR_RESPONSES)


class EInvoiceStatusResponse(ApiModel):
    enabled: bool
    """The print layout embeds e-invoices (ZUGFeRD) in the PDF."""
    embedded: bool | None
    """Whether the archived PDF holds the e-invoice; null while no PDF is archived."""
    zugferd_problems: list[EInvoiceProblem]
    """What keeps the invoice from being a ZUGFeRD e-invoice (EN 16931)."""
    xrechnung_problems: list[EInvoiceProblem]
    """What keeps the invoice from being an XRechnung."""

    @classmethod
    def of(cls, status: EInvoiceStatus) -> Self:
        problems = status.problems
        return cls(
            enabled=status.enabled,
            embedded=status.embedded,
            zugferd_problems=list(problems[EInvoiceProfile.EN16931]),
            xrechnung_problems=list(problems[EInvoiceProfile.XRECHNUNG]),
        )


XML_FILE: dict[int | str, dict[str, object]] = {
    200: {
        "description": "The invoice as XRechnung (CII XML)",
        "content": {"application/xml": {"schema": {"type": "string", "format": "binary"}}},
    },
}


@router.get("/documents/{document_id}/e-invoice")
def e_invoice_status(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> EInvoiceStatusResponse:
    """Tell whether the invoice's PDF is (or will be) a ZUGFeRD e-invoice and what is missing."""
    return EInvoiceStatusResponse.of(container.printing.e_invoice_status(document_id))


@router.get("/documents/{document_id}/xrechnung", response_class=Response, responses=XML_FILE)
def xrechnung(document_id: UUID, _user: CurrentUser, container: ContainerDep) -> Response:
    """Return the invoice as XRechnung file (for German authorities)."""
    document, content = container.printing.xrechnung(document_id)
    name = file_name(f"XRechnung {document.issued_number}", ".xml")
    fallback = name.encode("ascii", "replace").decode().replace("?", "_")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"
        ),
        "Cache-Control": "no-store",
    }
    return Response(content=content, media_type="application/xml", headers=headers)
