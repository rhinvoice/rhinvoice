from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from rhinvoice.application.common import PageRequest, SortDirection

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from rhinvoice.application.common import Page
    from rhinvoice.domain.catalog.article import Article
    from rhinvoice.domain.tax.tax_rate import TaxRate


class ArticleSort(StrEnum):
    NUMBER = "number"
    NAME = "name"
    GROUP = "group"
    CREATED_AT = "created_at"


@dataclass(frozen=True, slots=True)
class ArticleQuery:
    search: str = ""
    """Matches number, name, description and group (case-insensitive)."""
    include_archived: bool = False
    sort: ArticleSort = ArticleSort.NUMBER
    direction: SortDirection = SortDirection.ASC
    page: PageRequest = field(default_factory=PageRequest)


class ArticleRepository(Protocol):
    def get(self, article_id: UUID) -> Article | None: ...
    def number_exists(self, number: str, *, exclude_id: UUID | None = None) -> bool: ...
    def all(self) -> list[Article]:
        """Return every article, archived ones too (for the import's duplicate check)."""
        ...

    def add(self, article: Article) -> None: ...
    def update(self, article: Article) -> None: ...
    def search(self, query: ArticleQuery) -> Page[Article]: ...
    def adopt_rates(self, rates: Mapping[str, TaxRate]) -> None:
        """Give the articles saved before the company had rates the rate of their category.

        ``rates`` names the rate of each former category as stored (standard, reduced,
        special, zero, exempt); pass-through items stay without (migration 0027).
        """
        ...
