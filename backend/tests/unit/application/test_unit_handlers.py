"""The company's own units (ADR 0046)."""

from dataclasses import replace
from uuid import UUID

import pytest

from rhinvoice.application.catalog.units import (
    MAX_UNITS,
    Removal,
    SaveUnit,
    UnitHandlers,
    UnitOffer,
    UnitView,
    chosen_unit,
    default_unit,
    relabel_units,
)
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.recurring.handlers import to_template
from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.catalog.unit_presets import PRESETS, START, UnitGroup, preset_of
from rhinvoice.domain.company.company import Company
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.recurring.plan import Interval, PlanAction, RecurringPlan
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from tests.helpers import raises_exactly
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

HOURS = factories.unit_id("HUR")
PIECES = factories.unit_id("C62")


@pytest.fixture
def handlers(store: Store) -> UnitHandlers:
    return UnitHandlers(uow=lambda: InMemoryUnitOfWork(store))


def command(**overrides: str) -> SaveUnit:
    values = {"label": "dz", "code": "DTN"}
    values.update(overrides)
    return SaveUnit(**values)


def labels(store: Store) -> list[str]:
    return [unit.label for unit in store.units if not unit.hidden]


def test_the_units_of_the_company(handlers: UnitHandlers, store: Store) -> None:
    views = handlers.units()
    assert [view.unit for view in views] == list(factories.units().values())
    assert not any(view.in_use for view in views)
    store.articles[new_id()] = factories.article(unit_id=HOURS)
    assert [view.in_use for view in handlers.units()][:3] == [False, True, False]


def test_create_an_own_unit(handlers: UnitHandlers, store: Store) -> None:
    created = handlers.create(
        command(
            label=" dz ",
            label_de="Dz.",
            label_en="dt",
            label_fr="q",
            label_it="q ",
            description="100 kg",
        )
    )
    assert created == UnitView(store.units[-1], in_use=False)
    unit = created.unit
    assert isinstance(unit.id, UUID)
    assert (unit.code, unit.label, unit.description, unit.preset, unit.hidden) == (
        "DTN",
        "dz",
        "100 kg",
        None,
        False,
    )
    assert unit.translations == {
        Language.DE: "Dz.",
        Language.EN: "dt",
        Language.FR: "q",
        Language.IT: "q",
    }
    assert store.unit_locks == 1
    assert unit.id != handlers.create(command(label="Doppelzentner")).unit.id
    assert labels(store)[-2:] == ["dz", "Doppelzentner"]


def test_units_are_checked_on_save(handlers: UnitHandlers, store: Store) -> None:
    with raises_exactly(ValidationError, "'HAR' is not in the EN 16931 unit code list") as code:
        handlers.create(command(code="HAR"))
    assert code.value.code == "unit_code_unknown"
    # Labels are unique whatever the case, hidden units' too; several may share a code.
    with raises_exactly(ConflictError, "another unit has this label") as taken:
        handlers.create(command(label="STD."))
    assert (taken.value.code, taken.value.details) == (
        "unit_label_taken",
        {"label": "another unit has this label"},
    )
    store.units = [replace(unit, hidden=unit.id == HOURS) for unit in store.units]
    with raises_exactly(ConflictError, "another unit has this label"):
        handlers.create(command(label="std."))
    assert handlers.create(command(label="Stunde", code="HUR")).unit.code == "HUR"
    assert len(store.units) == len(START) + 1


def test_at_most_100_units(handlers: UnitHandlers, store: Store) -> None:
    assert MAX_UNITS == 100
    for number in range(MAX_UNITS - len(START)):
        handlers.create(command(label=f"Einheit {number}"))
    assert len(store.units) == MAX_UNITS
    with raises_exactly(ConflictError, "at most 100 units") as error:
        handlers.create(command(label="Noch eine"))
    assert error.value.code == "too_many_units"
    handlers.remove(store.units[-1].id)
    assert handlers.take_over(["DTN"], [])[-1].unit.preset == "DTN"
    assert len(store.units) == MAX_UNITS
    with raises_exactly(ConflictError, "at most 100 units"):
        handlers.take_over(["H18"], [])


def test_change_a_unit(handlers: UnitHandlers, store: Store) -> None:
    store.articles[new_id()] = factories.article(unit_id=HOURS)
    changed = handlers.update(
        HOURS, command(label="Stunde", code="HUR", label_en="hour", description="60 min")
    )
    assert changed == UnitView(store.units[1], in_use=True)
    assert (changed.unit.label, changed.unit.label_en, changed.unit.label_fr) == (
        "Stunde",
        "hour",
        "",
    )
    assert (changed.unit.description, changed.unit.preset, changed.unit.id) == (
        "60 min",
        "HUR",
        HOURS,
    )
    assert store.unit_locks == 1
    assert not handlers.update(PIECES, command(label="Stück", code="C62")).in_use
    # The code may change too; issued lines keep theirs.
    pair = handlers.update(
        PIECES, command(label="Stück", code="PR", label_de="Paar", label_it="paio")
    )
    assert (pair.unit.code, pair.unit.label_de, pair.unit.label_it) == ("PR", "Paar", "paio")
    assert store.units[0] == pair.unit
    # Its own label is no conflict; another unit's is.
    handlers.update(HOURS, command(label="stunde", code="HUR"))
    with raises_exactly(ConflictError, "another unit has this label"):
        handlers.update(HOURS, command(label="STÜCK", code="HUR"))
    with raises_exactly(NotFoundError, "unit not found"):
        handlers.update(new_id(), command())


def test_remove_deletes_or_hides(handlers: UnitHandlers, store: Store) -> None:
    assert handlers.remove(PIECES) is Removal.DELETED
    assert PIECES not in {unit.id for unit in store.units}
    store.articles[new_id()] = factories.article(unit_id=HOURS)
    assert handlers.remove(HOURS) is Removal.HIDDEN
    hours = next(unit for unit in store.units if unit.id == HOURS)
    assert hours.hidden
    assert store.unit_locks == 2
    # A hidden unit nothing uses any more goes on removing.
    store.articles = {}
    assert handlers.remove(HOURS) is Removal.DELETED
    with raises_exactly(NotFoundError, "unit not found"):
        handlers.remove(HOURS)


def test_a_unit_used_meanwhile_is_hidden(handlers: UnitHandlers, store: Store) -> None:
    """A line saved while the unit is removed: the database refuses the delete, it is hidden."""
    store.units_referenced_meanwhile.add(HOURS)
    assert handlers.remove(HOURS) is Removal.HIDDEN
    assert next(unit for unit in store.units if unit.id == HOURS).hidden is True
    assert handlers.remove(PIECES) is Removal.DELETED


def test_units_used_by_lines_and_plans_are_hidden(
    handlers: UnitHandlers, store: Store, clock: FixedClock
) -> None:
    store.company = factories.company()
    customer = factories.customer()
    store.customers[customer.id] = customer
    hours = LineInput(kind=LineKind.ITEM, description="Beratung", unit_id=HOURS)
    documents = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    documents.create(DocumentType.INVOICE, DraftInput(customer_id=customer.id, lines=(hours,)))
    pieces = replace(hours, unit_id=PIECES)
    store.plans[new_id()] = RecurringPlan.new(
        new_id(),
        name="Hosting",
        customer_id=customer.id,
        interval=Interval.MONTHLY,
        start_date=clock.today(),
        action=PlanAction.DRAFT,
        template=to_template(
            DraftInput(customer_id=customer.id, currency=Currency.CHF, lines=(pieces,)),
            list(factories.tax_rates().values()),
            list(factories.units().values()),
        ),
        today=clock.today(),
        now=clock.now(),
    )
    assert handlers.remove(HOURS) is Removal.HIDDEN
    assert handlers.remove(PIECES) is Removal.HIDDEN


def test_the_last_unit_offered_stays(handlers: UnitHandlers, store: Store) -> None:
    store.articles[new_id()] = factories.article(unit_id=PIECES)
    store.units = [replace(unit, hidden=unit.id != HOURS) for unit in store.units]
    with raises_exactly(
        ConflictError, "the last unit offered for lines cannot be removed"
    ) as error:
        handlers.remove(HOURS)
    assert error.value.code == "unit_last_visible"
    # Hidden ones are no unit offered, but may go themselves.
    assert handlers.remove(PIECES) is Removal.HIDDEN
    assert handlers.remove(factories.unit_id("MIN")) is Removal.DELETED


def test_show_a_hidden_unit_at_the_end(handlers: UnitHandlers, store: Store) -> None:
    store.units = [replace(unit, hidden=unit.code in {"HUR", "MIN"}) for unit in store.units]
    shown = handlers.show(HOURS)
    assert shown == UnitView(replace(factories.units()[HOURS], hidden=False), in_use=False)
    assert labels(store)[-2:] == ["Leistung", "Std."]
    assert [unit.label for unit in store.units][-1] == "Min."
    assert store.unit_locks == 1
    # A unit offered stays where it is.
    assert handlers.show(PIECES).unit.hidden is False
    assert labels(store)[0] == "Stk."
    with raises_exactly(NotFoundError, "unit not found"):
        handlers.show(new_id())


def test_sort_the_units(handlers: UnitHandlers, store: Store) -> None:
    store.units = [replace(unit, hidden=unit.code == "MIN") for unit in store.units]
    offered = [unit.id for unit in store.units if not unit.hidden]
    order = [offered[1], offered[0], *offered[2:]]
    views = handlers.reorder(order)
    assert [view.unit.id for view in views] == [*order, factories.unit_id("MIN")]
    assert labels(store)[:2] == ["Std.", "Stk."]
    assert store.units[-1].hidden
    assert store.unit_locks == 1
    for wrong in (order[1:], [*order, order[0]], [*order[1:], factories.unit_id("MIN")]):
        with raises_exactly(ValidationError, "the order names every unit offered once") as error:
            handlers.reorder(wrong)
        assert (error.value.field, error.value.code) == ("unit_ids", "unit_order_incomplete")
    store.articles[new_id()] = factories.article(unit_id=HOURS)
    assert [view.in_use for view in handlers.reorder(order)][:2] == [True, False]


def test_the_catalogue_offers_what_the_company_lacks(handlers: UnitHandlers, store: Store) -> None:
    offers = handlers.presets()
    assert [offer.key for offer in offers] == [preset.key for preset in PRESETS[len(START) :]]
    assert offers[1] == UnitOffer(
        code="DTN",
        label="dz",
        group=UnitGroup.WEIGHT,
        names=preset_of("DTN").names,  # type: ignore[union-attr]  # in the catalogue
        key="DTN",
    )
    # Hidden units follow, those from the catalogue in its group; a label taken hides an entry.
    store.units = [replace(unit, hidden=unit.code == "HUR") for unit in store.units]
    own = Unit(id=new_id(), code="XPX", label="Palette", description="Euro", hidden=True)
    store.units.append(own)
    offers = handlers.presets()
    assert "XPX" not in [offer.key for offer in offers]
    assert offers[-2:] == [
        UnitOffer(
            code="HUR",
            label="Std.",
            group=UnitGroup.TIME,
            names=preset_of("HUR").names,  # type: ignore[union-attr]  # in the catalogue
            unit_id=HOURS,
        ),
        UnitOffer(code="XPX", label="Palette", group=None, description="Euro", unit_id=own.id),
    ]


def test_take_over_from_the_catalogue(handlers: UnitHandlers, store: Store) -> None:
    store.units = [replace(unit, hidden=unit.code in {"HUR", "MIN"}) for unit in store.units]
    views = handlers.take_over(["DTN", "H18", "DTN"], [HOURS, HOURS, PIECES])
    assert [view.unit.label for view in views if not view.unit.hidden][-4:] == [
        "Leistung",
        "Std.",
        "dz",
        "ha",
    ]
    added = store.units[-1]
    assert (added.code, added.preset, added.label_en) == ("H18", "H18", "")
    assert isinstance(added.id, UUID)
    assert added.id != store.units[-2].id
    assert all(not unit.hidden for unit in store.units if unit.code in {"HUR", "C62"})
    assert next(unit for unit in store.units if unit.id == HOURS).hidden is False
    assert store.unit_locks == 1
    assert [offer.key for offer in handlers.presets()].count("DTN") == 0
    store.articles[new_id()] = factories.article(unit_id=HOURS)
    flags = {view.unit.id: view.in_use for view in handlers.take_over([], [])}
    assert flags[HOURS] is True
    assert flags[PIECES] is False
    with raises_exactly(ConflictError, "a unit comes from this entry already") as taken:
        handlers.take_over(["DTN"], [])
    assert taken.value.code == "unit_preset_taken"
    with raises_exactly(NotFoundError, "the catalogue has no such unit") as unknown:
        handlers.take_over(["HAR"], [])
    assert unknown.value.code == "unit_preset_unknown"
    with raises_exactly(NotFoundError, "unit not found"):
        handlers.take_over([], [new_id()])
    # An own unit with an entry's label keeps it from being added.
    handlers.create(command(label="Karton", code="XBX"))
    with raises_exactly(ConflictError, "another unit has this label"):
        handlers.take_over(["XCT"], [])
    assert store.units[-1].label == "Karton"


def test_choose_a_unit() -> None:
    units = list(factories.units().values())
    hidden = [replace(unit, hidden=unit.id == HOURS) for unit in units]
    assert chosen_unit(units, None) is None
    assert chosen_unit(units, HOURS) == HOURS
    assert chosen_unit(hidden, HOURS, kept=(HOURS,)) == HOURS
    with raises_exactly(ValidationError, "the unit is hidden") as error:
        chosen_unit(hidden, HOURS, kept=(PIECES,))
    assert (error.value.field, error.value.code) == ("unit_id", "unit_hidden")
    with raises_exactly(ValidationError, "unknown unit") as unknown:
        chosen_unit(units, new_id())
    assert (unknown.value.field, unknown.value.code) == ("unit_id", "unit_unknown")
    assert default_unit(units).id == PIECES
    assert default_unit([replace(unit, hidden=unit.id == PIECES) for unit in units]).id == HOURS
    with raises_exactly(ValidationError, "a unit is required"):
        default_unit([replace(unit, hidden=True) for unit in units])


def test_the_catalogue_speaks_the_company_language(handlers: UnitHandlers, store: Store) -> None:
    store.company = factories.company(default_language=Language.FR)
    quintal = next(offer for offer in handlers.presets() if offer.key == "DTN")
    assert quintal.label == "q"
    # A label a unit has already keeps its entry out, in that language too.
    handlers.create(command(label="Q", code="QTL"))
    assert "DTN" not in [offer.key for offer in handlers.presets()]
    store.units = store.units[:-1]
    added = handlers.take_over(["DTN"], [])[-1].unit
    assert (added.label, added.label_de, added.label_en, added.label_it) == ("q", "dz", "dt", "")


def relabel(store: Store, company: Company) -> None:
    with InMemoryUnitOfWork(store) as uow:
        relabel_units(uow, company)
        uow.commit()


def test_a_new_company_words_its_units_in_its_language(store: Store) -> None:
    """ADR 0046: the start list is German until the company is saved for the first time."""
    renamed = replace(factories.units()[HOURS], label="Stunde")
    hidden = replace(factories.units()[PIECES], hidden=True)
    own = Unit(id=new_id(), code="MIN", label="min")
    store.units = [
        unit for unit in [*factories.units().values(), own] if unit.id not in {HOURS, PIECES}
    ]
    store.units = [hidden, renamed, *store.units]
    relabel(store, factories.company(default_language=Language.FR))
    words = {unit.code: unit for unit in store.units}
    # Untouched units speak French; German becomes their own label; hidden stays hidden.
    assert (words["C62"].label, words["C62"].label_de, words["C62"].hidden) == (
        "pce",
        "Stk.",
        True,
    )
    assert (words["DAY"].label, words["DAY"].label_de) == ("jour", "Tag")
    # A unit the user changed stays as it is; so does one whose new label a unit has.
    assert words["HUR"] == renamed
    assert next(unit for unit in store.units if unit.preset == "MIN").label == "Min."
    assert store.unit_locks == 1


def test_a_german_company_keeps_its_units(store: Store) -> None:
    relabel(store, factories.company())
    assert store.units == list(factories.units().values())
