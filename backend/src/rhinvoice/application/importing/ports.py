"""Files to import (CSV, Excel) as a table of texts, and saved column mappings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from uuid import UUID

    from rhinvoice.application.importing.fields import ImportTarget


@dataclass(frozen=True, slots=True)
class ImportTable:
    headers: tuple[str, ...]
    """Column names from the first row; empty ones become "Spalte 3" etc."""
    rows: tuple[tuple[str, ...], ...]
    """The rows below the headers, each as long as ``headers``; empty rows are left out."""
    file_type: str
    """csv, xlsx or xls."""
    encoding: str | None = None
    """Detected character set of a CSV file (UTF-8 or Windows-1252)."""
    delimiter: str | None = None
    """Detected separator of a CSV file."""


class TableReader(Protocol):
    def read(self, content: bytes) -> ImportTable:
        """Read a CSV or Excel file; raises ValidationError when it cannot."""
        ...


@dataclass(frozen=True, slots=True)
class ImportTemplate:
    """A saved column mapping, e.g. for the exports of a program used before."""

    id: UUID
    target: ImportTarget
    name: str
    columns: Mapping[str, str]
    """Field key -> column name in the file (compared like the suggestions)."""
    created_at: datetime


class ImportTemplateRepository(Protocol):
    def list(self, target: ImportTarget) -> list[ImportTemplate]: ...
    def get(self, template_id: UUID) -> ImportTemplate | None: ...
    def name_exists(self, target: ImportTarget, name: str) -> bool: ...
    def add(self, template: ImportTemplate) -> None: ...
    def delete(self, template_id: UUID) -> None: ...
