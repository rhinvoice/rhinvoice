from uuid import UUID

import pytest

from rhinvoice.application.common import AddressInput
from rhinvoice.application.company.handlers import CompanyHandlers, SaveBankAccount, SaveCompany
from rhinvoice.application.errors import NotFoundError
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from tests.helpers import raises_exactly
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain.factories import CH_IBAN, CH_QR_IBAN

ADDRESS = AddressInput(
    street="Bahnhofstrasse", house_number="1", postal_code="8001", city="Zürich", country="CH"
)
SECOND_CH_IBAN = "CH5604835012345678009"
EUR_IBAN = "LI21088100002324013AA"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


@pytest.fixture
def handlers(store: Store) -> CompanyHandlers:
    return CompanyHandlers(uow=lambda: InMemoryUnitOfWork(store))


def company_command(**overrides: object) -> SaveCompany:
    values: dict[str, object] = {
        "name": "Muster GmbH",
        "address": ADDRESS,
        "default_currency": Currency.CHF,
    }
    values.update(overrides)
    return SaveCompany(**values)  # type: ignore[arg-type]  # test builder


def account_command(**overrides: object) -> SaveBankAccount:
    values: dict[str, object] = {
        "currency": Currency.CHF,
        "bank_name": "Musterbank",
        "holder": "Muster GmbH",
        "iban": CH_IBAN,
    }
    values.update(overrides)
    return SaveBankAccount(**values)  # type: ignore[arg-type]  # test builder


def test_company_is_created_once_and_then_updated(handlers: CompanyHandlers, store: Store) -> None:
    assert handlers.get() is None
    created = handlers.save(
        company_command(
            email=" Info@Muster.example ", vat_number="che-123.456.788 mwst", phone="044"
        ),
    )
    assert store.company == created
    assert isinstance(created.id, UUID)
    assert str(created.email) == "info@muster.example"
    assert str(created.vat_number) == "CHE-123.456.788 MWST"
    assert created.default_language is Language.DE
    updated = handlers.save(company_command(name="Muster AG", small_business=True, accent_hue=120))
    assert updated.id == created.id
    assert updated.name == "Muster AG"
    assert updated.email is None
    assert updated.small_business
    assert handlers.get() == updated


def test_all_company_fields_are_stored(handlers: CompanyHandlers) -> None:
    company = handlers.save(
        company_command(
            default_language=Language.EN,
            default_currency=Currency.EUR,
            website="https://muster.ch",
            tax_number="12/345/67890",
            commercial_register="Handelsregister Zürich",
            small_business=True,
            cash_rounding=False,
            payment_terms_days=14,
            accent_hue=12,
            phone="044 000 00 00",
        ),
    )
    assert company.address.street_line == "Bahnhofstrasse 1"
    assert company.default_language is Language.EN
    assert company.default_currency is Currency.EUR
    assert company.website == "https://muster.ch"
    assert company.tax_number == "12/345/67890"
    assert company.commercial_register == "Handelsregister Zürich"
    assert company.small_business is True
    assert company.cash_rounding is False
    assert company.payment_terms_days == 14
    assert company.accent_hue == 12
    assert company.phone == "044 000 00 00"


def test_company_validation_errors_are_raised(handlers: CompanyHandlers, store: Store) -> None:
    with pytest.raises(ValidationError):
        handlers.save(company_command(vat_number="CHE-123.456.789"))
    assert store.company is None


def test_logo_upload_and_removal(handlers: CompanyHandlers, store: Store) -> None:
    assert handlers.get_logo() is None
    logo = handlers.set_logo(PNG)
    assert logo.media_type == "image/png"
    assert store.logo == logo
    assert handlers.get_logo() == logo
    handlers.delete_logo()
    assert handlers.get_logo() is None
    with pytest.raises(ValidationError):
        handlers.set_logo(b"GIF89a")


def test_first_account_per_currency_becomes_default(handlers: CompanyHandlers) -> None:
    first = handlers.create_bank_account(
        account_command(iban=" ch93 0076 2011 6238 5295 7 ", bic="ubswchzh80a")
    )
    assert first.is_default
    assert first.iban.value == CH_IBAN
    assert str(first.bic) == "UBSWCHZH80A"
    second = handlers.create_bank_account(account_command(iban=SECOND_CH_IBAN))
    assert not second.is_default
    eur = handlers.create_bank_account(account_command(currency=Currency.EUR, iban=EUR_IBAN))
    assert eur.is_default
    assert [a.id for a in handlers.list_bank_accounts()] == [first.id, second.id, eur.id]


def test_choosing_a_new_default_unsets_the_old_one(handlers: CompanyHandlers, store: Store) -> None:
    first = handlers.create_bank_account(account_command())
    second = handlers.create_bank_account(account_command(iban=SECOND_CH_IBAN, is_default=True))
    assert second.is_default
    assert not store.bank_accounts[first.id].is_default
    updated = handlers.update_bank_account(
        first.id, account_command(is_default=True, qr_iban=CH_QR_IBAN)
    )
    assert updated.is_default
    assert updated.qr_iban is not None
    assert not store.bank_accounts[second.id].is_default


def test_new_default_among_several_accounts(handlers: CompanyHandlers, store: Store) -> None:
    first = handlers.create_bank_account(account_command())
    second = handlers.create_bank_account(account_command(iban=SECOND_CH_IBAN))
    third = handlers.create_bank_account(account_command(iban=CH_IBAN, is_default=True))
    assert [store.bank_accounts[a.id].is_default for a in (first, second, third)] == [
        False,
        False,
        True,
    ]


def test_changing_the_currency_of_the_default_promotes_a_successor(
    handlers: CompanyHandlers,
    store: Store,
) -> None:
    first = handlers.create_bank_account(account_command())
    second = handlers.create_bank_account(account_command(iban=SECOND_CH_IBAN))
    moved = handlers.update_bank_account(first.id, account_command(currency=Currency.EUR))
    assert moved.is_default
    assert store.bank_accounts[second.id].is_default
    handlers.update_bank_account(
        second.id, account_command(iban=SECOND_CH_IBAN, currency=Currency.EUR)
    )
    assert not store.bank_accounts[second.id].is_default


def test_moving_a_default_promotes_an_account_of_its_former_currency(
    handlers: CompanyHandlers,
    store: Store,
) -> None:
    chf = handlers.create_bank_account(account_command())
    eur = handlers.create_bank_account(account_command(currency=Currency.EUR, iban=EUR_IBAN))
    other_eur = handlers.create_bank_account(
        account_command(currency=Currency.EUR, iban=SECOND_CH_IBAN, bank_name="Zweitbank")
    )
    moved = handlers.update_bank_account(eur.id, account_command(iban=EUR_IBAN))
    assert not moved.is_default
    assert store.bank_accounts[chf.id].is_default
    assert store.bank_accounts[other_eur.id].is_default


def test_updating_the_default_keeps_the_other_accounts(
    handlers: CompanyHandlers,
    store: Store,
) -> None:
    first = handlers.create_bank_account(account_command())
    second = handlers.create_bank_account(account_command(iban=SECOND_CH_IBAN))
    updated = handlers.update_bank_account(first.id, account_command(bank_name="Neue Bank"))
    assert updated.is_default
    assert not store.bank_accounts[second.id].is_default


def test_updating_the_only_account_keeps_it_default(handlers: CompanyHandlers) -> None:
    account = handlers.create_bank_account(account_command())
    updated = handlers.update_bank_account(account.id, account_command(bank_name="Neue Bank"))
    assert updated.is_default
    assert updated.bank_name == "Neue Bank"


def test_deleting_the_default_promotes_another_account(
    handlers: CompanyHandlers, store: Store
) -> None:
    first = handlers.create_bank_account(account_command())
    second = handlers.create_bank_account(account_command(iban=SECOND_CH_IBAN))
    eur = handlers.create_bank_account(account_command(currency=Currency.EUR, iban=EUR_IBAN))
    handlers.delete_bank_account(first.id)
    assert store.bank_accounts[second.id].is_default
    assert store.bank_accounts[eur.id].is_default
    handlers.delete_bank_account(second.id)
    handlers.delete_bank_account(eur.id)
    assert store.bank_accounts == {}


def test_deleting_a_non_default_account_keeps_the_default(
    handlers: CompanyHandlers, store: Store
) -> None:
    first = handlers.create_bank_account(account_command())
    second = handlers.create_bank_account(account_command(iban=SECOND_CH_IBAN))
    handlers.delete_bank_account(second.id)
    assert store.bank_accounts[first.id].is_default


def test_unknown_accounts(handlers: CompanyHandlers) -> None:
    unknown: UUID = new_id()
    with raises_exactly(NotFoundError, "bank account not found"):
        handlers.update_bank_account(unknown, account_command())
    with raises_exactly(NotFoundError, "bank account not found"):
        handlers.delete_bank_account(unknown)


def test_account_without_optional_values(handlers: CompanyHandlers) -> None:
    account = handlers.create_bank_account(account_command(qr_iban="", bic=""))
    assert account.qr_iban is None
    assert account.bic is None
