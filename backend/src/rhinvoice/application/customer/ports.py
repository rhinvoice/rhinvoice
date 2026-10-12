from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from rhinvoice.application.common import PageRequest, SortDirection

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.application.common import Page
    from rhinvoice.domain.customer.customer import Customer


class CustomerSort(StrEnum):
    NUMBER = "number"
    NAME = "name"
    CITY = "city"
    CREATED_AT = "created_at"


@dataclass(frozen=True, slots=True)
class CustomerQuery:
    search: str = ""
    """Matches number, name, contact person, e-mail and city (case-insensitive)."""
    include_archived: bool = False
    sort: CustomerSort = CustomerSort.NUMBER
    direction: SortDirection = SortDirection.ASC
    page: PageRequest = field(default_factory=PageRequest)


class CustomerRepository(Protocol):
    def get(self, customer_id: UUID) -> Customer | None: ...
    def number_exists(self, number: str, *, exclude_id: UUID | None = None) -> bool: ...
    def all(self) -> list[Customer]:
        """Return every customer, archived ones too (for the import's duplicate check)."""
        ...

    def add(self, customer: Customer) -> None: ...
    def update(self, customer: Customer) -> None: ...
    def search(self, query: CustomerQuery) -> Page[Customer]: ...
