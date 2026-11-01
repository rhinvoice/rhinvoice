"""The export of the issued invoices of a period for the bookkeeping (ADR 0038)."""

from collections.abc import Iterator
from datetime import date
from typing import IO, Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.routers.documents import file_disposition
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.document.export import (
    ZIP_MEDIA_TYPE,
    ExportFormat,
    ExportRequest,
)
from rhinvoice.application.errors import DemoLockedError
from rhinvoice.domain.document.export import ExportPeriod
from rhinvoice.domain.shared.language import Language

router = APIRouter(prefix="/api", tags=["exports"], responses=ERROR_RESPONSES)

CHUNK_BYTES = 64 * 1024
_BINARY = {"schema": {"type": "string", "format": "binary"}}
EXPORT_FILE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The list (Excel, CSV or PDF), or with ``pdfs`` a ZIP of the list and PDFs",
        "content": {
            **{export_format.media_type: _BINARY for export_format in ExportFormat},
            ZIP_MEDIA_TYPE: _BINARY,
        },
    },
    503: {
        "description": "A PDF is asked for, but no PDF service is configured or reachable",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}},
        },
    },
}


class ExportParams(ApiModel):
    start: date
    """First day of the period (issue dates)."""
    end: date
    """Last day of the period, at most ten years after the first."""
    format: ExportFormat = ExportFormat.XLSX
    pdfs: bool = False
    """Add the PDF of every document: the list and the PDFs come as one ZIP."""
    language: Language | None = None
    """Of the column headers; by default the company's language."""


def _chunks(content: IO[bytes]) -> Iterator[bytes]:
    try:
        while chunk := content.read(CHUNK_BYTES):
            yield chunk
    finally:
        content.close()


@router.get("/exports/invoices", response_class=StreamingResponse, responses=EXPORT_FILE)
def export_invoices(
    params: Annotated[ExportParams, Query()],
    _user: CurrentUser,
    container: ContainerDep,
) -> StreamingResponse:
    """Download the issued invoices and cancellations of a period for the bookkeeping."""
    if params.pdfs and container.settings.demo:
        # Many PDFs at once: too much load for a demo everyone shares.
        raise DemoLockedError("this is not possible in the public demo")
    exported = container.exports.export(
        ExportRequest(
            period=ExportPeriod(params.start, params.end),
            format=params.format,
            with_pdfs=params.pdfs,
            language=params.language,
        )
    )
    return StreamingResponse(
        _chunks(exported.content),
        media_type=exported.media_type,
        headers={
            "Content-Disposition": file_disposition(exported.name, download=True),
            "Cache-Control": "no-store",
        },
    )
