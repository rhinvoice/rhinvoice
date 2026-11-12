"""The company's own tax rates (ADR 0044)."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.tax.handlers import (
    MAX_TAX_RATES,
    PresetOffer,
    SaveTaxRate,
    TaxRateHandlers,
    TaxRateView,
)
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.presets import EXEMPT, REDUCED, STANDARD
from rhinvoice.domain.tax.tax_rate import RateCategory, RateValue, TaxRate
from tests.helpers import raises_exactly
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

GERMANY = factories.address(country=CountryCode("DE"))


@pytest.fixture
def handlers(store: Store) -> TaxRateHandlers:
    store.company = factories.company(address=GERMANY)
    return TaxRateHandlers(uow=lambda: InMemoryUnitOfWork(store))


def command(**overrides: object) -> SaveTaxRate:
    values: dict[str, object] = {
        "name": "Heilbehandlung",
        "category": RateCategory.EXEMPT,
        "values": ((date(2024, 1, 1), "0"),),
        "exemption_reason": "§ 4 Nr. 14 UStG",
    }
    values.update(overrides)
    return SaveTaxRate(**values)  # type: ignore[arg-type]  # test builder


def test_the_rates_of_the_company(handlers: TaxRateHandlers, store: Store) -> None:
    views = handlers.rates()
    assert [view.rate for view in views] == list(factories.tax_rates(Country.DE).values())
    assert not any(view.in_use for view in views)
    store.articles[new_id()] = factories.article(tax_rate_id=factories.rate_id(REDUCED))
    assert [view.in_use for view in handlers.rates()] == [False, True, False, False]


def test_create_an_own_rate(handlers: TaxRateHandlers, store: Store) -> None:
    created = handlers.create(
        command(values=((date(2026, 1, 1), "0.00"), (date(2024, 1, 1), "0")), notice=" Hinweis ")
    )
    assert created == TaxRateView(store.tax_rates[-1], in_use=False)
    rate = created.rate
    assert isinstance(rate.id, UUID)
    assert (rate.name, rate.category, rate.notice, rate.preset, rate.hidden) == (
        "Heilbehandlung",
        RateCategory.EXEMPT,
        "Hinweis",
        None,
        False,
    )
    # Oldest first, whatever the order sent.
    assert rate.values == (
        RateValue(date(2024, 1, 1), Decimal(0)),
        RateValue(date(2026, 1, 1), Decimal(0)),
    )
    assert store.tax_rate_locks == 1
    assert rate.id != handlers.create(command(name="Zweiter")).rate.id


def test_rates_are_checked_on_save(handlers: TaxRateHandlers, store: Store) -> None:
    with raises_exactly(ValidationError, "an exempt rate (E) needs the reason for the exemption"):
        handlers.create(command(exemption_reason=""))
    with raises_exactly(ValidationError, "'acht' is not a valid number") as number:
        handlers.create(command(values=((date(2024, 1, 1), "0"), (date(2025, 1, 1), "acht"))))
    assert number.value.field == "values.1.percent"
    with raises_exactly(ValidationError, "the percentage must be from 0 to below 100") as high:
        handlers.create(
            command(category=RateCategory.STANDARD, values=((date(2024, 1, 1), "100"),))
        )
    assert (high.value.field, high.value.code) == ("values.0.percent", "validation_error")
    with raises_exactly(ValidationError, "zero-rated (Z) and exempt (E) rates must be 0 %") as zero:
        handlers.create(command(values=((date(2024, 1, 1), "7"),)))
    assert zero.value.code == "rate_zero_needs_zero"
    with raises_exactly(ConflictError, "another tax rate has this name") as taken:
        handlers.create(command(name="NORMALSATZ"))
    assert (taken.value.code, taken.value.details) == (
        "tax_rate_name_taken",
        {"name": "another tax rate has this name"},
    )
    assert len(store.tax_rates) == 4


def test_at_most_forty_rates(handlers: TaxRateHandlers, store: Store) -> None:
    for number in range(MAX_TAX_RATES - 4):
        handlers.create(command(name=f"Satz {number}"))
    with raises_exactly(ConflictError, f"at most {MAX_TAX_RATES} tax rates") as error:
        handlers.create(command(name="Einer zu viel"))
    assert error.value.code == "too_many_tax_rates"
    assert len(store.tax_rates) == MAX_TAX_RATES


def test_update_a_rate(handlers: TaxRateHandlers, store: Store) -> None:
    standard = factories.rate_id(STANDARD)
    store.articles[new_id()] = factories.article(tax_rate_id=standard)
    updated = handlers.update(
        standard,
        command(
            name="Normal",
            category=RateCategory.STANDARD,
            values=((date(2027, 1, 1), "21"), (date(2007, 1, 1), "19")),
            exemption_reason="",
            notice="Neu",
        ),
    )
    assert updated.in_use
    assert updated.rate == replace(
        factories.tax_rates(Country.DE)[standard],
        name="Normal",
        values=(RateValue(date(2007, 1, 1), Decimal(19)), RateValue(date(2027, 1, 1), Decimal(21))),
        notice="Neu",
    )
    assert store.tax_rates[0] == updated.rate
    # The rate keeps its preset and its place.
    assert (updated.rate.preset, store.tax_rate_locks) == (STANDARD, 1)
    # Its own name may change case; another's is taken.
    assert (
        handlers.update(
            standard,
            command(
                name="NORMAL", category=RateCategory.STANDARD, values=((date(2007, 1, 1), "19"),)
            ),
        ).rate.name
        == "NORMAL"
    )
    with raises_exactly(ConflictError, "another tax rate has this name"):
        handlers.update(
            standard,
            command(
                name="reduzierter satz",
                category=RateCategory.STANDARD,
                values=((date(2007, 1, 1), "19"),),
            ),
        )


def test_the_texts_of_a_rate_change(handlers: TaxRateHandlers, store: Store) -> None:
    exempt = factories.rate_id(EXEMPT)
    changed = handlers.update(exempt, command(exemption_reason="§ 4 Nr. 21 UStG")).rate
    assert (changed.exemption_reason, changed.name, changed.notice) == (
        "§ 4 Nr. 21 UStG",
        "Heilbehandlung",
        "",
    )
    assert store.tax_rates[3] == changed


def test_the_category_of_a_rate_stays(handlers: TaxRateHandlers, store: Store) -> None:
    exempt = factories.rate_id(EXEMPT)
    with raises_exactly(
        ValidationError, "the category of a rate cannot change; add a new rate instead"
    ) as error:
        handlers.update(exempt, command(category=RateCategory.ZERO))
    assert (error.value.field, error.value.code) == ("category", "rate_category_fixed")
    assert store.tax_rates == list(factories.tax_rates(Country.DE).values())
    with raises_exactly(NotFoundError, "tax rate not found"):
        handlers.update(new_id(), command())


def test_hide_and_show_a_rate(handlers: TaxRateHandlers, store: Store) -> None:
    reduced = factories.rate_id(REDUCED)
    hidden = handlers.hide(reduced)
    assert (hidden.rate.hidden, hidden.in_use) == (True, False)
    assert store.tax_rates[1] == hidden.rate
    store.articles[new_id()] = factories.article(tax_rate_id=reduced)
    shown = handlers.show(reduced)
    assert (shown.rate.hidden, shown.in_use) == (False, True)
    assert store.tax_rates[1] == shown.rate
    assert store.tax_rate_locks == 2
    with raises_exactly(NotFoundError, "tax rate not found"):
        handlers.hide(new_id())


def test_delete_only_unused_rates(handlers: TaxRateHandlers, store: Store) -> None:
    reduced, exempt = factories.rate_id(REDUCED), factories.rate_id(EXEMPT)
    store.articles[new_id()] = factories.article(tax_rate_id=reduced)
    with raises_exactly(
        ConflictError, "documents, articles or recurring plans use the rate; hide it instead"
    ) as error:
        handlers.delete(reduced)
    assert error.value.code == "tax_rate_in_use"
    handlers.delete(exempt)
    assert exempt not in {rate.id for rate in store.tax_rates}
    assert store.tax_rate_locks == 2
    with raises_exactly(NotFoundError, "tax rate not found"):
        handlers.delete(exempt)


def test_presets_not_taken_yet(handlers: TaxRateHandlers, store: Store) -> None:
    offers = handlers.presets()
    assert [offer.key for offer in offers] == ["de_24_forestry", "de_24_beverages", "de_24_other"]
    forestry = profile_of(Country.DE).scheme_presets[0]
    assert offers[0] == PresetOffer(
        key="de_24_forestry",
        name="Forstwirtschaft § 24 (5,5 %)",
        category=RateCategory.STANDARD,
        values=forestry.values,
        notice="Besteuerung nach Durchschnittssätzen (§ 24 UStG)",
        exemption_reason="",
        sources=forestry.sources,
    )
    # In the company's language; a base preset deleted before is offered again.
    assert store.company is not None
    store.company = replace(store.company, default_language=Language.EN)
    handlers.delete(factories.rate_id(EXEMPT))
    english = handlers.presets()
    assert [offer.key for offer in english] == [
        EXEMPT,
        "de_24_forestry",
        "de_24_beverages",
        "de_24_other",
    ]
    assert (english[0].exemption_reason, english[0].notice) == ("Exempt supply", "")
    assert english[1].name == "Forestry § 24 (5.5 %)"


def test_take_over_a_preset(handlers: TaxRateHandlers, store: Store) -> None:
    taken = handlers.take_over_preset("de_24_other")
    assert isinstance(taken.rate.id, UUID)
    assert taken.in_use is False
    assert taken.rate == store.tax_rates[-1]
    assert (taken.rate.name, taken.rate.preset, taken.rate.notice) == (
        "Landwirtschaft § 24 (7,8 %)",
        "de_24_other",
        "Besteuerung nach Durchschnittssätzen (§ 24 UStG)",
    )
    assert store.tax_rate_locks == 1
    with raises_exactly(ConflictError, "a rate comes from this preset already") as again:
        handlers.take_over_preset("de_24_other")
    assert again.value.code == "preset_taken"
    with raises_exactly(NotFoundError, "the country has no such preset") as unknown:
        handlers.take_over_preset("ch_special")
    assert unknown.value.code == "unknown_preset"
    assert [offer.key for offer in handlers.presets()] == ["de_24_forestry", "de_24_beverages"]


def test_a_preset_needs_room_and_a_free_name(handlers: TaxRateHandlers, store: Store) -> None:
    own = TaxRate(
        id=new_id(),
        name="Forstwirtschaft § 24 (5,5 %)",
        category=RateCategory.STANDARD,
        values=(RateValue(date(2025, 1, 1), Decimal("5.5")),),
    )
    store.tax_rates = [*factories.tax_rates(Country.DE).values(), own]
    with raises_exactly(ConflictError, "another tax rate has this name"):
        handlers.take_over_preset("de_24_forestry")
    for number in range(MAX_TAX_RATES - 5):
        handlers.create(command(name=f"Satz {number}"))
    with raises_exactly(ConflictError, f"at most {MAX_TAX_RATES} tax rates"):
        handlers.take_over_preset("de_24_other")


def test_presets_need_the_company(store: Store) -> None:
    handlers = TaxRateHandlers(uow=lambda: InMemoryUnitOfWork(store))
    for action in (handlers.presets, lambda: handlers.take_over_preset("standard")):
        with raises_exactly(ConflictError, "set up the company first") as error:
            action()
        assert error.value.code == "company_not_set_up"
    assert handlers.apply_preset_updates() == []


def test_releases_add_new_percentages_to_unchanged_presets(
    handlers: TaxRateHandlers, store: Store
) -> None:
    """A release brings a new value of a preset; rates the user changed stay theirs."""
    current = factories.tax_rates(Country.DE)
    standard, reduced, exempt = (factories.rate_id(key) for key in (STANDARD, REDUCED, EXEMPT))
    behind = replace(current[standard], values=current[standard].values[:2])
    changed = replace(
        current[reduced],
        values=(*current[reduced].values[:2], RateValue(date(2021, 1, 1), Decimal(8))),
    )
    own = TaxRate(
        id=new_id(),
        name="Eigener Satz",
        category=RateCategory.STANDARD,
        values=(RateValue(date(2007, 1, 1), Decimal(19)),),
    )
    unknown = replace(own, id=new_id(), name="Alt", preset="de_old")
    store.tax_rates = [
        behind,
        changed,
        current[factories.rate_id("zero")],
        current[exempt],
        own,
        unknown,
    ]
    updated = handlers.apply_preset_updates()
    assert updated == [current[standard]]
    assert store.tax_rates == [
        current[standard],
        changed,
        current[factories.rate_id("zero")],
        current[exempt],
        own,
        unknown,
    ]
    assert store.tax_rate_locks == 1
    # Running it again changes nothing.
    assert handlers.apply_preset_updates() == []
    # A rate ahead of its preset (the user added the next value early) is left alone too.
    ahead = replace(
        current[standard],
        values=(*current[standard].values, RateValue(date(2030, 1, 1), Decimal(20))),
    )
    store.tax_rates[0] = ahead
    assert handlers.apply_preset_updates() == []
    assert store.tax_rates[0] == ahead
