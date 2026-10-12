"""Use cases for articles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.numbering.handlers import allocate_number
from rhinvoice.domain.catalog.article import Article
from rhinvoice.domain.catalog.unit import DEFAULT_UNIT_CODE, Unit
from rhinvoice.domain.numbering.sequence import SequenceKind
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, parse_decimal
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date, datetime
    from uuid import UUID

    from rhinvoice.application.catalog.ports import ArticleQuery
    from rhinvoice.application.common import Page
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock

MAX_NUMBER_ATTEMPTS = 100


@dataclass(frozen=True, slots=True)
class SaveArticle:
    name: str
    number: str = ""
    """Empty: take the next number of the article sequence."""
    unit: str = DEFAULT_UNIT_CODE
    tax_category: TaxCategory = TaxCategory.STANDARD
    prices: dict[Currency, str] = field(default_factory=dict[Currency, str])
    description: str = ""
    group: str = ""
    supply: Supply = Supply.SERVICE


@dataclass(frozen=True, slots=True)
class ArticleHandlers:
    uow: UnitOfWorkFactory
    clock: Clock

    def search(self, query: ArticleQuery) -> Page[Article]:
        with self.uow() as uow:
            return uow.articles.search(query)

    def get(self, article_id: UUID) -> Article:
        with self.uow() as uow:
            return self._require(uow, article_id)

    def create(self, command: SaveArticle) -> Article:
        with self.uow() as uow:
            number = command.number.strip() or next_free_article_number(uow, self.clock.today())
            article = build_article(new_id(), number, command, now=self.clock.now(), existing=None)
            self._ensure_unique(uow, article.number, exclude_id=None)
            uow.articles.add(article)
            uow.commit()
        return article

    def update(self, article_id: UUID, command: SaveArticle) -> Article:
        with self.uow() as uow:
            existing = self._require(uow, article_id)
            number = command.number.strip() or existing.number
            article = build_article(
                article_id, number, command, now=self.clock.now(), existing=existing
            )
            self._ensure_unique(uow, article.number, exclude_id=article_id)
            uow.articles.update(article)
            uow.commit()
        return article

    def archive(self, article_id: UUID) -> Article:
        return self._change(article_id, Article.archive)

    def restore(self, article_id: UUID) -> Article:
        return self._change(article_id, Article.restore)

    def _change(self, article_id: UUID, change: Callable[[Article], Article]) -> Article:
        with self.uow() as uow:
            article = change(self._require(uow, article_id))
            uow.articles.update(article)
            uow.commit()
        return article

    @staticmethod
    def _ensure_unique(uow: UnitOfWork, number: str, *, exclude_id: UUID | None) -> None:
        if uow.articles.number_exists(number, exclude_id=exclude_id):
            message = f"article number {number} is already taken"
            raise ConflictError(message, details={"number": message})

    @staticmethod
    def _require(uow: UnitOfWork, article_id: UUID) -> Article:
        article = uow.articles.get(article_id)
        if article is None:
            raise NotFoundError("article not found")
        return article


def build_article(
    article_id: UUID,
    number: str,
    command: SaveArticle,
    *,
    now: datetime,
    existing: Article | None,
) -> Article:
    """Build the article of a create or update command; raise ValidationError if invalid."""
    prices = {
        currency: parse_decimal(price, f"prices.{currency}")
        for currency, price in command.prices.items()
        if price.strip()
    }
    return Article(
        id=article_id,
        number=number,
        name=command.name,
        unit=Unit(command.unit),
        tax_category=command.tax_category,
        prices=prices,
        created_at=now if existing is None else existing.created_at,
        description=command.description,
        group=command.group,
        archived=False if existing is None else existing.archived,
        supply=command.supply,
    )


def next_free_article_number(uow: UnitOfWork, today: date) -> str:
    """Take the next number of the sequence, skipping numbers assigned manually."""
    for _ in range(MAX_NUMBER_ATTEMPTS):
        number = allocate_number(uow, SequenceKind.ARTICLE, today)
        if not uow.articles.number_exists(number):
            return number
    raise ConflictError("no free article number found, please check the number sequence")
