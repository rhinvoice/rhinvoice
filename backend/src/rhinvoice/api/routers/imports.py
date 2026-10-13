from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from rhinvoice.api.dependencies import NOT_IN_DEMO, ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.importing.fields import FIELDS, ImportTarget
from rhinvoice.application.importing.files import ImportFile
from rhinvoice.application.importing.handlers import (
    MAX_TEMPLATE_NAME,
    ImportRequest,
    ImportRun,
    SaveTemplate,
)
from rhinvoice.application.importing.ports import ImportTemplate
from rhinvoice.application.importing.results import (
    DuplicateStrategy,
    RowOutcome,
    RowStatus,
)
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.infrastructure.importing.archive import MAX_UPLOAD_BYTES, read_files
from rhinvoice.infrastructure.importing.reader import MAX_FILE_BYTES

# A public demo takes no files from strangers: whatever it stored, every visitor could open.
router = APIRouter(
    prefix="/api/imports",
    tags=["imports"],
    responses=ERROR_RESPONSES,
    dependencies=[NOT_IN_DEMO],
)

SAMPLE_ROWS = 3
_MAPPING = TypeAdapter(dict[str, int])

FileUpload = Annotated[
    UploadFile, File(description="CSV (UTF-8 or Windows-1252), XLSX or XLS, at most 5 MB")
]
FilesUpload = Annotated[
    list[UploadFile],
    File(
        description=(
            "Invoices: their PDF files, one by one or as ZIP files; the invoice number "
            "in the file name tells the invoice. At most 200 MB together."
        )
    ),
]
DuplicatesForm = Annotated[DuplicateStrategy, Form()]
MappingForm = Annotated[
    str | None,
    Form(
        description=(
            'JSON object field -> column index (0-based), e.g. {"number": 0, "city": 3}; '
            "empty: suggested from the column names"
        )
    ),
]


class ImportFieldResponse(ApiModel):
    key: str
    required: bool


class RowProblemResponse(ApiModel):
    field: str
    code: str
    """required, invalid, or a specific rule such as invalid_amount or unknown_unit."""
    message: str
    value: str
    """The cell's text, if the file has one for the field."""


class ImportRowResponse(ApiModel):
    row: int
    """Row number in the file; the column names are row 1."""
    status: RowStatus
    number: str
    name: str
    detail: str
    problem: RowProblemResponse | None
    file: str | None
    """Invoices: the PDF that became the invoice."""
    attachments: int
    """Invoices: further files of the number, kept with the invoice."""
    new_customer: bool
    """Invoices: the customer was unknown and has been created, archived."""

    @classmethod
    def of(cls, outcome: RowOutcome) -> Self:
        problem = outcome.problem
        return cls(
            row=outcome.row,
            status=outcome.status,
            number=outcome.number,
            name=outcome.name,
            detail=outcome.detail,
            problem=None
            if problem is None
            else RowProblemResponse(
                field=problem.field,
                code=problem.code,
                message=problem.message,
                value=problem.value,
            ),
            file=outcome.file,
            attachments=outcome.attachments,
            new_customer=outcome.new_customer,
        )


class ImportCounts(ApiModel):
    new: int
    updated: int
    skipped: int
    error: int


class ImportRunResponse(ApiModel):
    target: ImportTarget
    file_type: str
    encoding: str | None
    delimiter: str | None
    headers: list[str]
    sample: list[list[str]]
    """The first rows below the column names, for choosing the mapping."""
    fields: list[ImportFieldResponse]
    mapping: dict[str, int]
    """Field key -> column index (0-based) that was used."""
    counts: ImportCounts
    rows: list[ImportRowResponse]
    committed: bool
    missing: list[list[str]]
    """Needed columns that are not mapped, each as alternatives; the test run then has no rows."""
    unused_files: list[str]
    """Invoices: uploaded files that belong to no invoice of the file."""
    next_number: str | None
    """Invoices: the number of the next invoice written here (behind the imported ones)."""

    @classmethod
    def of(cls, run: ImportRun) -> Self:
        table = run.table
        return cls(
            target=run.target,
            file_type=table.file_type,
            encoding=table.encoding,
            delimiter=table.delimiter,
            headers=list(table.headers),
            sample=[list(row) for row in table.rows[:SAMPLE_ROWS]],
            fields=[
                ImportFieldResponse(key=field.key, required=field.required)
                for field in FIELDS[run.target]
            ],
            mapping=run.mapping,
            counts=ImportCounts(
                new=run.count(RowStatus.NEW),
                updated=run.count(RowStatus.UPDATED),
                skipped=run.count(RowStatus.SKIPPED),
                error=run.count(RowStatus.ERROR),
            ),
            rows=[ImportRowResponse.of(outcome) for outcome in run.outcomes],
            committed=run.committed,
            missing=[list(group) for group in run.missing],
            unused_files=list(run.unused_files),
            next_number=run.next_number,
        )


ColumnName = Annotated[str, Field(max_length=200)]


class TemplateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=MAX_TEMPLATE_NAME)
    columns: dict[str, ColumnName] = Field(
        max_length=50, description="Field key -> column name in the file"
    )


class TemplateResponse(ApiModel):
    id: UUID
    target: ImportTarget
    name: str
    columns: dict[str, str]
    created_at: datetime

    @classmethod
    def of(cls, template: ImportTemplate) -> Self:
        return cls(
            id=template.id,
            target=template.target,
            name=template.name,
            columns=dict(template.columns),
            created_at=template.created_at,
        )


class ImportUpload:
    """The form of a test run or an import: the file, the choices and the PDF files."""

    def __init__(
        self,
        file: FileUpload,
        duplicates: DuplicatesForm = DuplicateStrategy.SKIP,
        mapping: MappingForm = None,
        files: FilesUpload = [],  # noqa: B006 - FastAPI copies defaults per request
    ) -> None:
        self.file = file
        self.duplicates = duplicates
        self.mapping = mapping
        self.files = files

    def request(self, target: ImportTarget, *, commit: bool) -> ImportRequest:
        parsed: dict[str, int] | None = None
        if self.mapping is not None and self.mapping.strip():
            try:
                parsed = _MAPPING.validate_json(self.mapping)
            except PydanticValidationError:
                raise ValidationError(
                    "mapping",
                    "the mapping is not a JSON object of column numbers",
                    code="invalid_mapping",
                ) from None
        # Synchronous on purpose (thread pool); one byte more lets the reader reject large files.
        content = self.file.file.read(MAX_FILE_BYTES + 1)
        return ImportRequest(
            target=target,
            content=content,
            duplicates=self.duplicates,
            mapping=parsed,
            commit=commit,
            files=_files(self.files) if target is ImportTarget.INVOICES else (),
        )


Upload = Annotated[ImportUpload, Depends()]


def _files(uploads: list[UploadFile]) -> tuple[ImportFile, ...]:
    budget = MAX_UPLOAD_BYTES
    read: list[tuple[str, bytes]] = []
    for upload in uploads:
        content = upload.file.read(budget + 1)
        budget -= len(content)
        if budget < 0:
            raise ValidationError(
                "files", "the files are larger than 200 MB together", code="file_too_large"
            )
        read.append((upload.filename or "", content))
    return read_files(read)


@router.post("/{target}/preview")
def preview_import(
    target: ImportTarget, upload: Upload, _user: CurrentUser, container: ContainerDep
) -> ImportRunResponse:
    """Test run: reports what the import would do and changes nothing."""
    return ImportRunResponse.of(container.imports.run(upload.request(target, commit=False)))


@router.post("/{target}")
def run_import(
    target: ImportTarget, upload: Upload, _user: CurrentUser, container: ContainerDep
) -> ImportRunResponse:
    """Import the rows without errors; rows with errors are reported and left out."""
    return ImportRunResponse.of(container.imports.run(upload.request(target, commit=True)))


@router.get("/{target}/templates")
def list_templates(
    target: ImportTarget, _user: CurrentUser, container: ContainerDep
) -> list[TemplateResponse]:
    return [TemplateResponse.of(t) for t in container.imports.templates(target)]


@router.post("/{target}/templates", status_code=status.HTTP_201_CREATED)
def save_template(
    target: ImportTarget, body: TemplateRequest, _user: CurrentUser, container: ContainerDep
) -> TemplateResponse:
    template = container.imports.save_template(
        SaveTemplate(target=target, name=body.name, columns=body.columns)
    )
    return TemplateResponse.of(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: UUID, _user: CurrentUser, container: ContainerDep) -> None:
    container.imports.delete_template(template_id)
