from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.importing.fields import FIELDS, ImportTarget
from rhinvoice.application.importing.handlers import (
    MAX_TEMPLATE_NAME,
    DuplicateStrategy,
    ImportRequest,
    ImportRun,
    RowOutcome,
    RowStatus,
    SaveTemplate,
)
from rhinvoice.application.importing.ports import ImportTemplate
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.infrastructure.importing.reader import MAX_FILE_BYTES

router = APIRouter(prefix="/api/imports", tags=["imports"], responses=ERROR_RESPONSES)

SAMPLE_ROWS = 3
_MAPPING = TypeAdapter(dict[str, int])

FileUpload = Annotated[
    UploadFile, File(description="CSV (UTF-8 or Windows-1252), XLSX or XLS, at most 5 MB")
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


def _request(
    target: ImportTarget,
    file: UploadFile,
    duplicates: DuplicateStrategy,
    mapping: str | None,
    *,
    commit: bool,
) -> ImportRequest:
    parsed: dict[str, int] | None = None
    if mapping is not None and mapping.strip():
        try:
            parsed = _MAPPING.validate_json(mapping)
        except PydanticValidationError:
            raise ValidationError(
                "mapping",
                "the mapping is not a JSON object of column numbers",
                code="invalid_mapping",
            ) from None
    # Synchronous on purpose (thread pool); one byte more lets the reader reject large files.
    content = file.file.read(MAX_FILE_BYTES + 1)
    return ImportRequest(
        target=target, content=content, duplicates=duplicates, mapping=parsed, commit=commit
    )


@router.post("/{target}/preview")
def preview_import(
    target: ImportTarget,
    file: FileUpload,
    _user: CurrentUser,
    container: ContainerDep,
    duplicates: DuplicatesForm = DuplicateStrategy.SKIP,
    mapping: MappingForm = None,
) -> ImportRunResponse:
    """Test run: reports what the import would do and changes nothing."""
    request = _request(target, file, duplicates, mapping, commit=False)
    return ImportRunResponse.of(container.imports.run(request))


@router.post("/{target}")
def run_import(
    target: ImportTarget,
    file: FileUpload,
    _user: CurrentUser,
    container: ContainerDep,
    duplicates: DuplicatesForm = DuplicateStrategy.SKIP,
    mapping: MappingForm = None,
) -> ImportRunResponse:
    """Import the rows without errors; rows with errors are reported and left out."""
    request = _request(target, file, duplicates, mapping, commit=True)
    return ImportRunResponse.of(container.imports.run(request))


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
