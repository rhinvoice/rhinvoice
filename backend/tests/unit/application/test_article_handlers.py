from datetime import timedelta
from decimal import Decimal

import pytest

from rhinvoice.application.catalog.handlers import ArticleHandlers, SaveArticle
from rhinvoice.application.catalog.ports import ArticleQuery, ArticleSort
from rhinvoice.application.common import PageRequest, SortDirection
from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store


@pytest.fixture
def handlers(store: Store, clock: FixedClock) -> ArticleHandlers:
    return ArticleHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


def command(**overrides: object) -> SaveArticle:
    values: dict[str, object] = {"name": "Beratung", "unit": "HUR", "prices": {Currency.CHF: "150"}}
    values.update(overrides)
    return SaveArticle(**values)  # type: ignore[arg-type]  # test builder


def test_create_article(handlers: ArticleHandlers) -> None:
    article = handlers.create(
        command(
            prices={Currency.CHF: "150.50", Currency.EUR: " "},
            tax_category=TaxCategory.REDUCED,
            description="Stundenansatz",
            group="Dienstleistung",
        ),
    )
    assert article.number == "1"
    assert article.prices == {Currency.CHF: Decimal("150.50")}
    assert article.unit.code == "HUR"
    assert article.tax_category is TaxCategory.REDUCED
    assert article.created_at == NOW
    assert handlers.create(command()).number == "2"


def test_defaults(handlers: ArticleHandlers) -> None:
    article = handlers.create(SaveArticle(name="Kabel"))
    assert article.unit.code == "C62"
    assert article.tax_category is TaxCategory.STANDARD
    assert article.prices == {}


def test_invalid_input(handlers: ArticleHandlers, store: Store) -> None:
    with pytest.raises(ValidationError) as price:
        handlers.create(command(prices={Currency.CHF: "zehn"}))
    assert price.value.field == "prices.CHF"
    with pytest.raises(ValidationError):
        handlers.create(command(unit="XXX"))
    assert store.articles == {}


def test_numbers_are_unique_and_skip_manual_ones(handlers: ArticleHandlers) -> None:
    handlers.create(command(number="1"))
    assert handlers.create(command()).number == "2"
    with raises_exactly(ConflictError, "article number 2 is already taken") as error:
        handlers.create(command(number="2"))
    assert error.value.details == {"number": "article number 2 is already taken"}


def test_number_search_gives_up_eventually(handlers: ArticleHandlers) -> None:
    for number in range(1, 101):
        handlers.create(command(number=str(number)))
    with raises_exactly(
        ConflictError, "no free article number found, please check the number sequence"
    ):
        handlers.create(command())


def test_update_archive_restore(handlers: ArticleHandlers, clock: FixedClock) -> None:
    article = handlers.create(command())
    other = handlers.create(command())
    handlers.archive(article.id)
    clock.set(NOW + timedelta(days=2))
    updated = handlers.update(
        article.id, command(name="Beratung Senior", prices={Currency.CHF: "180"})
    )
    assert updated.name == "Beratung Senior"
    assert updated.number == article.number
    assert updated.created_at == NOW
    assert updated.archived is True
    assert handlers.restore(article.id).archived is False
    assert handlers.get(article.id).prices == {Currency.CHF: Decimal(180)}
    with raises_exactly(ConflictError, f"article number {other.number} is already taken"):
        handlers.update(article.id, command(number=other.number))
    assert handlers.update(article.id, command(number="A-1")).number == "A-1"


def test_unknown_articles(handlers: ArticleHandlers) -> None:
    with raises_exactly(NotFoundError, "article not found"):
        handlers.get(new_id())
    with raises_exactly(NotFoundError, "article not found"):
        handlers.update(new_id(), command())
    with raises_exactly(NotFoundError, "article not found"):
        handlers.restore(new_id())


def test_search(handlers: ArticleHandlers) -> None:
    beratung = handlers.create(command(name="Beratung", group="Dienstleistung"))
    kabel = handlers.create(
        command(name="Kabel", group="Material", description="Netzwerkkabel Cat6")
    )
    old = handlers.create(command(name="Altes Produkt"))
    handlers.archive(old.id)
    assert [a.id for a in handlers.search(ArticleQuery(search="NETZWERK")).items] == [kabel.id]
    by_group = handlers.search(ArticleQuery(sort=ArticleSort.GROUP, direction=SortDirection.DESC))
    assert [a.id for a in by_group.items] == [kabel.id, beratung.id]
    everything = handlers.search(
        ArticleQuery(include_archived=True, sort=ArticleSort.NAME, page=PageRequest(limit=2)),
    )
    assert everything.total == 3
    assert [a.id for a in everything.items] == [old.id, beratung.id]
