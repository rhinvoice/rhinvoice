from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import (
    DECIMAL_PATTERN,
    ERROR_RESPONSES,
    UNIT_CODES,
    ApiModel,
    SearchParams,
    price_text,
    text,
)
from rhinvoice.application.catalog.handlers import SaveArticle
from rhinvoice.application.catalog.ports import ArticleQuery, ArticleSort
from rhinvoice.domain.catalog.article import Article
from rhinvoice.domain.catalog.unit import DEFAULT_UNIT_CODE
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply

router = APIRouter(prefix="/api/articles", tags=["articles"], responses=ERROR_RESPONSES)

PriceField = Annotated[str, Field(pattern=DECIMAL_PATTERN)]


class ArticleRequest(ApiModel):
    number: str = Field(default="", max_length=30, description="Empty: next number of the sequence")
    name: str = text(120, required=True)
    description: str = text(4000)
    group: str = text(50)
    unit: str = Field(default=DEFAULT_UNIT_CODE, json_schema_extra={"enum": UNIT_CODES})
    tax_category: TaxCategory = TaxCategory.STANDARD
    supply: Supply = Supply.SERVICE
    """Goods cross borders under their own VAT rules (export, intra-Community supply)."""
    prices: dict[Currency, PriceField] = Field(default_factory=dict[Currency, PriceField])
    """Net unit price per currency as a decimal string, e.g. {"CHF": "150.00"}."""

    def to_command(self) -> SaveArticle:
        return SaveArticle(
            name=self.name,
            number=self.number,
            unit=self.unit,
            tax_category=self.tax_category,
            supply=self.supply,
            prices=dict(self.prices),
            description=self.description,
            group=self.group,
        )


class ArticleResponse(ApiModel):
    id: UUID
    number: str
    name: str
    description: str
    group: str
    unit: str = Field(json_schema_extra={"enum": UNIT_CODES})
    unit_label_de: str
    unit_label_en: str
    unit_label_fr: str
    unit_label_it: str
    tax_category: TaxCategory
    supply: Supply
    prices: dict[Currency, str]
    archived: bool
    created_at: datetime

    @classmethod
    def of(cls, article: Article) -> Self:
        return cls(
            id=article.id,
            number=article.number,
            name=article.name,
            description=article.description,
            group=article.group,
            unit=article.unit.code,
            unit_label_de=article.unit.label_de,
            unit_label_en=article.unit.label_en,
            unit_label_fr=article.unit.label(Language.FR),
            unit_label_it=article.unit.label(Language.IT),
            tax_category=article.tax_category,
            supply=article.supply,
            prices={currency: price_text(price) for currency, price in article.prices.items()},
            archived=article.archived,
            created_at=article.created_at,
        )


class ArticlePage(ApiModel):
    items: list[ArticleResponse]
    total: int


class ArticleSearch(SearchParams):
    sort: ArticleSort = ArticleSort.NUMBER


@router.get("")
def search_articles(
    params: Annotated[ArticleSearch, Query()],
    _user: CurrentUser,
    container: ContainerDep,
) -> ArticlePage:
    page = container.articles.search(
        ArticleQuery(
            search=params.q,
            include_archived=params.include_archived,
            sort=params.sort,
            direction=params.direction,
            page=params.page_request(),
        ),
    )
    return ArticlePage(items=[ArticleResponse.of(a) for a in page.items], total=page.total)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_article(
    body: ArticleRequest, _user: CurrentUser, container: ContainerDep
) -> ArticleResponse:
    return ArticleResponse.of(container.articles.create(body.to_command()))


@router.get("/{article_id}")
def get_article(article_id: UUID, _user: CurrentUser, container: ContainerDep) -> ArticleResponse:
    return ArticleResponse.of(container.articles.get(article_id))


@router.put("/{article_id}")
def update_article(
    article_id: UUID,
    body: ArticleRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> ArticleResponse:
    return ArticleResponse.of(container.articles.update(article_id, body.to_command()))


@router.post("/{article_id}/archive")
def archive_article(
    article_id: UUID, _user: CurrentUser, container: ContainerDep
) -> ArticleResponse:
    return ArticleResponse.of(container.articles.archive(article_id))


@router.post("/{article_id}/restore")
def restore_article(
    article_id: UUID, _user: CurrentUser, container: ContainerDep
) -> ArticleResponse:
    return ArticleResponse.of(container.articles.restore(article_id))
