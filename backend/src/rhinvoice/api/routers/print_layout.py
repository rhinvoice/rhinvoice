from typing import Any, Self
from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import HTMLResponse, Response
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.routers.documents import HTML_PAGE, file_disposition
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel, text
from rhinvoice.domain.company.print_layout import (
    MAX_FIELD_LABEL,
    MAX_INFO_ENTRIES,
    MAX_INFO_KEY,
    MAX_LAYOUT_NAME,
    FooterAccounts,
    InfoEntry,
    LogoPosition,
    LogoSize,
    NamedLayout,
    PrintFont,
    PrintLayout,
    PrintTemplate,
)

router = APIRouter(prefix="/api/print-layouts", tags=["print-layout"], responses=ERROR_RESPONSES)


class InfoEntrySchema(ApiModel):
    """One line of the facts next to the address."""

    key: str = Field(max_length=MAX_INFO_KEY)
    """A row (number, customer_number, date, due_date, service_date, reference), a reference
    field of the e-invoice (project, contract, purchase_order, sales_order, despatch_advice,
    tender, invoiced_object, buyer_accounting) or a custom field: "custom-" and 8 hex digits."""
    shown: bool = True
    """Rows only; number and date are always shown."""
    label: str = Field(default="", max_length=MAX_FIELD_LABEL)
    """Custom fields only: the printed name."""


class PrintLayoutSchema(ApiModel):
    template: PrintTemplate
    logo_position: LogoPosition
    logo_size: LogoSize
    font: PrintFont
    sender_line: bool
    """The small sender line above the address (window envelopes)."""
    contact: bool
    """Phone, e-mail and website in the head."""
    position_numbers: bool
    footer_accounts: FooterAccounts
    e_invoice: bool
    """Embed the e-invoice (ZUGFeRD, EN 16931) in the PDF of invoices."""
    info_block: list[InfoEntrySchema] = Field(max_length=MAX_INFO_ENTRIES)
    """The facts next to the address in order: every row once, plus the fields."""

    @classmethod
    def of(cls, layout: PrintLayout) -> Self:
        return cls(
            template=layout.template,
            logo_position=layout.logo_position,
            logo_size=layout.logo_size,
            font=layout.font,
            sender_line=layout.sender_line,
            contact=layout.contact,
            position_numbers=layout.position_numbers,
            footer_accounts=layout.footer_accounts,
            e_invoice=layout.e_invoice,
            info_block=[
                InfoEntrySchema(key=entry.key, shown=entry.shown, label=entry.label)
                for entry in layout.info_block
            ],
        )

    def to_domain(self) -> PrintLayout:
        return PrintLayout(
            template=self.template,
            logo_position=self.logo_position,
            logo_size=self.logo_size,
            font=self.font,
            sender_line=self.sender_line,
            contact=self.contact,
            position_numbers=self.position_numbers,
            footer_accounts=self.footer_accounts,
            e_invoice=self.e_invoice,
            info_block=tuple(
                InfoEntry(entry.key, entry.shown, entry.label) for entry in self.info_block
            ),
        )


class PrintLayoutResponse(ApiModel):
    """A named print layout (#48)."""

    id: UUID
    name: str
    is_default: bool
    layout: PrintLayoutSchema

    @classmethod
    def of(cls, named: NamedLayout) -> Self:
        return cls(
            id=named.id,
            name=named.name,
            is_default=named.is_default,
            layout=PrintLayoutSchema.of(named.layout),
        )


class CreatePrintLayoutRequest(ApiModel):
    name: str = text(MAX_LAYOUT_NAME, required=True)
    copy_of: UUID | None = None
    """The layout to start from; none: the default one."""


class SavePrintLayoutRequest(ApiModel):
    name: str = text(MAX_LAYOUT_NAME, required=True)
    layout: PrintLayoutSchema


@router.get("")
def list_print_layouts(_user: CurrentUser, container: ContainerDep) -> list[PrintLayoutResponse]:
    """Every print layout, the default first."""
    return [PrintLayoutResponse.of(named) for named in container.company.list_print_layouts()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_print_layout(
    body: CreatePrintLayoutRequest, _user: CurrentUser, container: ContainerDep
) -> PrintLayoutResponse:
    """Add a layout as a copy of another one.

    409 print_layout_name_taken, too_many_print_layouts.
    """
    return PrintLayoutResponse.of(container.company.create_print_layout(body.name, body.copy_of))


@router.put("/{layout_id}")
def save_print_layout(
    layout_id: UUID, body: SavePrintLayoutRequest, _user: CurrentUser, container: ContainerDep
) -> PrintLayoutResponse:
    """Save a layout for documents rendered from now on; issued ones keep theirs.

    409 print_layout_name_taken.
    """
    named = container.company.update_print_layout(layout_id, body.name, body.layout.to_domain())
    return PrintLayoutResponse.of(named)


@router.post("/{layout_id}/default")
def make_default_print_layout(
    layout_id: UUID, _user: CurrentUser, container: ContainerDep
) -> PrintLayoutResponse:
    """Make a layout the default for customers and documents without their own."""
    return PrintLayoutResponse.of(container.company.make_default_print_layout(layout_id))


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_print_layout(layout_id: UUID, _user: CurrentUser, container: ContainerDep) -> None:
    """Delete a layout; its customers and drafts take the default.

    409 default_print_layout: the default one stays.
    """
    container.company.delete_print_layout(layout_id)


@router.post("/preview", response_class=HTMLResponse, responses=HTML_PAGE)
def preview_print_layout(
    body: PrintLayoutSchema, _user: CurrentUser, container: ContainerDep
) -> HTMLResponse:
    """Render the latest invoice (or a sample one) with this layout, without saving it.

    409 company_not_set_up before the company is set up.
    """
    return HTMLResponse(container.printing.layout_preview_html(body.to_domain()))


SAMPLE_PDF: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The latest invoice with this layout, marked as a sample",
        "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
    },
    503: {
        "description": "No PDF service configured or reachable",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}},
        },
    },
}


@router.post("/sample", response_class=Response, responses=SAMPLE_PDF)
def sample_print_layout(
    body: PrintLayoutSchema, _user: CurrentUser, container: ContainerDep
) -> Response:
    """Render the latest invoice with this layout as a PDF marked as a sample.

    To send to a bookkeeper or a customer before switching. 409 company_not_set_up.
    """
    content = container.printing.layout_sample_pdf(body.to_domain())
    headers = {
        "Content-Disposition": file_disposition("sample.pdf", download=True),
        "Cache-Control": "no-store",
    }
    return Response(content=content, media_type="application/pdf", headers=headers)
