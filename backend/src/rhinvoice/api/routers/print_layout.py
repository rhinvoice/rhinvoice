from typing import Self

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.routers.documents import HTML_PAGE
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.domain.company.print_layout import (
    FooterAccounts,
    LogoPosition,
    LogoSize,
    PrintFont,
    PrintLayout,
    PrintTemplate,
)

router = APIRouter(prefix="/api/print-layout", tags=["print-layout"], responses=ERROR_RESPONSES)


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
        )


@router.get("")
def get_print_layout(_user: CurrentUser, container: ContainerDep) -> PrintLayoutSchema:
    return PrintLayoutSchema.of(container.company.print_layout())


@router.put("")
def save_print_layout(
    body: PrintLayoutSchema, _user: CurrentUser, container: ContainerDep
) -> PrintLayoutSchema:
    """Save the layout for documents rendered from now on; issued ones keep their PDF."""
    return PrintLayoutSchema.of(container.company.save_print_layout(body.to_domain()))


@router.post("/preview", response_class=HTMLResponse, responses=HTML_PAGE)
def preview_print_layout(
    body: PrintLayoutSchema, _user: CurrentUser, container: ContainerDep
) -> HTMLResponse:
    """Render the latest invoice (or a sample one) with this layout, without saving it.

    409 company_not_set_up before the company is set up.
    """
    return HTMLResponse(container.printing.layout_preview_html(body.to_domain()))
