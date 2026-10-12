from uuid import UUID

import pytest

from rhinvoice.application.errors import NotFoundError
from rhinvoice.application.text.handlers import SaveTextTemplate, TextHandlers, effective_notice
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.text.template import TextKind
from tests.helpers import raises_exactly
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

RC = TaxTreatment.REVERSE_CHARGE
SWISS_RC = (
    "Übergang der Steuerschuld auf den Leistungsempfänger "
    "(Steuerschuldnerschaft des Leistungsempfängers, Reverse Charge)."
)


@pytest.fixture
def handlers(store: Store) -> TextHandlers:
    store.company = factories.company()
    return TextHandlers(uow=lambda: InMemoryUnitOfWork(store))


def save(**overrides: object) -> SaveTextTemplate:
    values: dict[str, object] = {
        "kind": TextKind.PAYMENT,
        "document_type": DocumentType.INVOICE,
        "language": Language.DE,
        "name": "Fällig",
        "text": "Zahlbar bis {faellig}.",
    }
    values.update(overrides)
    return SaveTextTemplate(**values)  # type: ignore[arg-type]  # test builder


def test_templates_are_numbered_per_kind_type_and_language(
    handlers: TextHandlers, store: Store
) -> None:
    first = handlers.create_template(save(is_default=True))
    second = handlers.create_template(save(name="Prompt", text="Zahlbar prompt."))
    other_kind = handlers.create_template(save(kind=TextKind.INTRO, name="Hallo", text="Hallo"))
    english = handlers.create_template(save(language=Language.EN, name="Due", text="Due."))
    assert [first.position, second.position, other_kind.position, english.position] == [
        0,
        1,
        0,
        0,
    ]
    assert first.is_default
    assert store.text_templates[first.id] == first
    assert handlers.list_templates() == [other_kind, first, second, english]


def test_update_keeps_the_position_and_delete_removes(handlers: TextHandlers, store: Store) -> None:
    handlers.create_template(save())
    second = handlers.create_template(save(name="Prompt", text="Zahlbar prompt."))
    changed = handlers.update_template(second.id, save(name="Sofort", is_default=True))
    assert (changed.id, changed.name, changed.position, changed.is_default) == (
        second.id,
        "Sofort",
        1,
        True,
    )
    # Moved to another kind: placed after the templates there.
    handlers.create_template(save(kind=TextKind.CLOSING, name="Gruss", text="Gruss"))
    to_closing = handlers.update_template(second.id, save(kind=TextKind.CLOSING, name="Sofort"))
    assert to_closing.position == 1
    handlers.update_template(second.id, save(name="Sofort"))
    assert store.text_templates[second.id].position == 1
    handlers.delete_template(second.id)
    assert [template.name for template in handlers.list_templates()] == ["Fällig", "Gruss"]
    unknown = new_id()
    for action in (
        lambda: handlers.update_template(unknown, save()),
        lambda: handlers.delete_template(unknown),
        lambda: handlers.move_template(unknown, up=True),
    ):
        with raises_exactly(NotFoundError, "text template not found"):
            action()


def test_templates_are_validated(handlers: TextHandlers, store: Store) -> None:
    with pytest.raises(ValidationError) as error:
        handlers.create_template(save(text="Bis {datumm}"))
    assert error.value.code == "unknown_placeholder"
    assert store.text_templates == {}


def test_move_swaps_with_the_neighbour(handlers: TextHandlers) -> None:
    first = handlers.create_template(save(name="A", text="A"))
    second = handlers.create_template(save(name="B", text="B"))
    third = handlers.create_template(save(name="C", text="C"))
    handlers.create_template(save(kind=TextKind.CLOSING, name="Z", text="Z"))

    def names() -> list[str]:
        return [
            template.name
            for template in handlers.list_templates()
            if template.kind is TextKind.PAYMENT
        ]

    moved = handlers.move_template(third.id, up=True)
    assert [template.name for template in moved if template.kind is TextKind.PAYMENT] == [
        "A",
        "C",
        "B",
    ]
    handlers.move_template(first.id, up=False)
    assert names() == ["C", "A", "B"]
    # At the ends nothing moves.
    handlers.move_template(third.id, up=True)
    handlers.move_template(second.id, up=False)
    assert names() == ["C", "A", "B"]
    # The second one can move to the top.
    handlers.move_template(first.id, up=True)
    assert names() == ["A", "C", "B"]


def test_notices_list_defaults_and_own_wording(handlers: TextHandlers, store: Store) -> None:
    notices = handlers.list_notices()
    assert len(notices) == len(profile_of(Country.CH).notice_treatments) * len(Language)
    reverse = next(n for n in notices if (n.treatment, n.language) == (RC, Language.DE))
    assert (reverse.text, reverse.default_text, reverse.customized) == (SWISS_RC, SWISS_RC, False)
    english = next(n for n in notices if (n.treatment, n.language) == (RC, Language.EN))
    assert english.default_text == "Reverse charge: the recipient is liable for the VAT."
    # Saving the English suggestion keeps the built-in wording.
    saved = handlers.save_notice(RC, Language.EN, english.default_text)
    assert (saved.text, saved.customized) == (english.default_text, False)
    assert store.legal_notices == {}

    own = handlers.save_notice(RC, Language.DE, "  Reverse Charge: Steuerschuld beim Empfänger. ")
    assert (own.text, own.default_text, own.customized) == (
        "Reverse Charge: Steuerschuld beim Empfänger.",
        SWISS_RC,
        True,
    )
    assert store.legal_notices == {(RC, Language.DE): own.text}
    listed = next(
        n for n in handlers.list_notices() if (n.treatment, n.language) == (RC, Language.DE)
    )
    assert listed == own

    # The built-in wording or an empty text restores the default.
    for text in (SWISS_RC, " "):
        handlers.save_notice(RC, Language.DE, "Eigen")
        restored = handlers.save_notice(RC, Language.DE, text)
        assert (restored.text, restored.customized) == (SWISS_RC, False)
        assert store.legal_notices == {}


def test_notice_rules(handlers: TextHandlers, store: Store) -> None:
    with raises_exactly(ValidationError, "this tax treatment has no notice"):
        handlers.save_notice(TaxTreatment.DOMESTIC, Language.DE, "x")
    # Swiss companies export their goods: there is no intra-Community supply to word.
    with raises_exactly(ValidationError, "this tax treatment has no notice") as caught:
        handlers.save_notice(TaxTreatment.INTRA_COMMUNITY, Language.DE, "x")
    assert caught.value.field == "treatment"
    with raises_exactly(ValidationError, "text must be at most 500 characters long"):
        handlers.save_notice(RC, Language.DE, "x" * 501)
    store.company = None
    with raises_exactly(ValidationError, "please set up the company first") as missing:
        handlers.list_notices()
    assert missing.value.field == "company"
    with raises_exactly(ValidationError, "please set up the company first"):
        handlers.save_notice(RC, Language.DE, "x")


def test_effective_notice(store: Store) -> None:
    store.legal_notices[RC, Language.EN] = "Own"
    with InMemoryUnitOfWork(store) as uow:
        assert effective_notice(uow, TaxTreatment.DOMESTIC, Country.CH, Language.DE) == ""
        assert effective_notice(uow, RC, Country.CH, Language.DE) == SWISS_RC
        assert effective_notice(uow, RC, Country.DE, Language.EN) == "Own"


def test_ids_are_kept(handlers: TextHandlers) -> None:
    created = handlers.create_template(save())
    assert isinstance(created.id, UUID)
