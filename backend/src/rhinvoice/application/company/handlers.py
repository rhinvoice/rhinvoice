"""Use cases for the company, its logo and bank accounts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from rhinvoice.application.common import AddressInput, optional_email, optional_vat_number
from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.tax.handlers import adopt_rates, reseed_rates, seed_rates
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.company import DEFAULT_ACCENT_HUE, Company
from rhinvoice.domain.company.logo import Logo
from rhinvoice.domain.company.print_layout import MAX_LAYOUTS, NamedLayout, default_layout
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.iban import Bic, Iban
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.company.print_layout import PrintLayout
    from rhinvoice.domain.shared.money import Currency


@dataclass(frozen=True, slots=True)
class SaveCompany:
    name: str
    address: AddressInput
    default_currency: Currency
    default_language: Language = Language.DE
    email: str | None = None
    phone: str = ""
    website: str = ""
    vat_number: str | None = None
    tax_number: str = ""
    commercial_register: str = ""
    small_business: bool = False
    cash_rounding: bool = False
    payment_terms_days: int = 30
    accent_hue: int = DEFAULT_ACCENT_HUE


@dataclass(frozen=True, slots=True)
class SaveBankAccount:
    currency: Currency
    bank_name: str
    holder: str
    iban: str
    qr_iban: str | None = None
    bic: str | None = None
    is_default: bool = False
    third_party: bool = False
    """The account belongs to someone else, e.g. a financial service provider."""
    holder_address: AddressInput | None = None
    """The third party's address; ignored for own accounts."""


@dataclass(frozen=True, slots=True)
class CompanyHandlers:
    uow: UnitOfWorkFactory

    # --- Company ---------------------------------------------------------------

    def get(self) -> Company | None:
        with self.uow() as uow:
            return uow.company.get()

    def save(self, command: SaveCompany) -> Company:
        with self.uow() as uow:
            existing = uow.company.get()
            company = Company(
                id=new_id() if existing is None else existing.id,
                name=command.name,
                address=command.address.to_domain(),
                default_currency=command.default_currency,
                default_language=command.default_language,
                email=optional_email(command.email),
                phone=command.phone,
                website=command.website,
                vat_number=optional_vat_number(command.vat_number),
                tax_number=command.tax_number,
                commercial_register=command.commercial_register,
                small_business=command.small_business,
                cash_rounding=command.cash_rounding,
                payment_terms_days=command.payment_terms_days,
                accent_hue=command.accent_hue,
            )
            uow.company.save(company)
            # A company starts with the rates of its country (ADR 0044).
            if existing is None:
                adopt_rates(uow, seed_rates(uow, company))
            elif existing.country is not company.country:
                reseed_rates(uow, company)
            uow.commit()
        return company

    def get_logo(self) -> Logo | None:
        with self.uow() as uow:
            return uow.company.get_logo()

    def set_logo(self, content: bytes) -> Logo:
        logo = Logo.from_upload(content)
        with self.uow() as uow:
            uow.company.save_logo(logo)
            uow.commit()
        return logo

    def delete_logo(self) -> None:
        with self.uow() as uow:
            uow.company.delete_logo()
            uow.commit()

    # --- Print layouts -----------------------------------------------------------

    def list_print_layouts(self) -> list[NamedLayout]:
        """Every layout, the default first (#48)."""
        with self.uow() as uow:
            return uow.print_layouts.list()

    def create_print_layout(self, name: str, copy_of: UUID | None = None) -> NamedLayout:
        """Add a layout as a copy of another one (the default when none is named)."""
        with self.uow() as uow:
            layouts = uow.print_layouts.list(for_update=True)
            if len(layouts) >= MAX_LAYOUTS:
                raise ConflictError(
                    f"at most {MAX_LAYOUTS} print layouts", code="too_many_print_layouts"
                )
            source = default_layout(layouts) if copy_of is None else _require(layouts, copy_of)
            named = NamedLayout(new_id(), name, source.layout)
            _check_name(layouts, named)
            uow.print_layouts.add(named)
            uow.commit()
        return named

    def update_print_layout(self, layout_id: UUID, name: str, layout: PrintLayout) -> NamedLayout:
        with self.uow() as uow:
            layouts = uow.print_layouts.list(for_update=True)
            previous = _require(layouts, layout_id)
            named = NamedLayout(layout_id, name, layout, is_default=previous.is_default)
            _check_name(layouts, named)
            uow.print_layouts.update(named)
            uow.commit()
        return named

    def make_default_print_layout(self, layout_id: UUID) -> NamedLayout:
        """Make a layout the default; documents without their own and their customer's take it."""
        with self.uow() as uow:
            layouts = uow.print_layouts.list(for_update=True)
            chosen = _require(layouts, layout_id)
            if not chosen.is_default:
                # The old default first: the database allows one at a time.
                for previous in layouts:
                    if previous.is_default:
                        uow.print_layouts.update(replace(previous, is_default=False))
                chosen = replace(chosen, is_default=True)
                uow.print_layouts.update(chosen)
                uow.commit()
        return chosen

    def delete_print_layout(self, layout_id: UUID) -> None:
        """Delete a layout; its customers and drafts take the default, issued documents keep it."""
        with self.uow() as uow:
            named = _require(uow.print_layouts.list(for_update=True), layout_id)
            if named.is_default:
                raise ConflictError(
                    "the default print layout cannot be deleted", code="default_print_layout"
                )
            uow.print_layouts.delete(layout_id)
            uow.commit()

    # --- Bank accounts -----------------------------------------------------------

    def list_bank_accounts(self) -> list[BankAccount]:
        with self.uow() as uow:
            return uow.bank_accounts.list()

    def create_bank_account(self, command: SaveBankAccount) -> BankAccount:
        with self.uow() as uow:
            account = self._with_default_rule(uow, self._build_account(new_id(), command))
            uow.bank_accounts.add(account)
            uow.commit()
        return account

    def update_bank_account(self, account_id: UUID, command: SaveBankAccount) -> BankAccount:
        with self.uow() as uow:
            previous = self._require_account(uow, account_id)
            account = self._with_default_rule(uow, self._build_account(account_id, command))
            uow.bank_accounts.update(account)
            if previous.is_default and previous.currency is not account.currency:
                self._promote_successor(uow, previous)
            uow.commit()
        return account

    def delete_bank_account(self, account_id: UUID) -> None:
        """Issued documents keep a snapshot of the account, so deleting is safe."""
        with self.uow() as uow:
            account = self._require_account(uow, account_id)
            uow.bank_accounts.delete(account_id)
            if account.is_default:
                self._promote_successor(uow, account)
            uow.commit()

    @staticmethod
    def _promote_successor(uow: UnitOfWork, former: BankAccount) -> None:
        """Another account of the former default's currency becomes the default."""
        successor = next(
            (
                other
                for other in uow.bank_accounts.list()
                if other.currency is former.currency and other.id != former.id
            ),
            None,
        )
        if successor is not None:
            uow.bank_accounts.update(successor.as_default(is_default=True))

    @staticmethod
    def _build_account(account_id: UUID, command: SaveBankAccount) -> BankAccount:
        return BankAccount(
            id=account_id,
            currency=command.currency,
            bank_name=command.bank_name,
            holder=command.holder,
            iban=Iban.parse(command.iban),
            qr_iban=None if not command.qr_iban else Iban.parse(command.qr_iban),
            bic=None if not command.bic else Bic.parse(command.bic),
            is_default=command.is_default,
            third_party=command.third_party,
            holder_address=(
                None
                if command.holder_address is None or not command.third_party
                else command.holder_address.to_domain()
            ),
        )

    @staticmethod
    def _with_default_rule(uow: UnitOfWork, account: BankAccount) -> BankAccount:
        """Exactly one default account per currency; the first one becomes default.

        Other defaults are cleared *before* the account is written, so that the
        unique index on (currency) WHERE is_default is never violated.
        """
        others = [
            other
            for other in uow.bank_accounts.list()
            if other.currency is account.currency and other.id != account.id
        ]
        if account.is_default:
            for other in others:
                if other.is_default:
                    uow.bank_accounts.update(other.as_default(is_default=False))
            return account
        if any(other.is_default for other in others):
            return account
        return replace(account, is_default=True)

    @staticmethod
    def _require_account(uow: UnitOfWork, account_id: UUID) -> BankAccount:
        account = uow.bank_accounts.get(account_id)
        if account is None:
            raise NotFoundError("bank account not found")
        return account


def _require(layouts: list[NamedLayout], layout_id: UUID) -> NamedLayout:
    for named in layouts:
        if named.id == layout_id:
            return named
    raise NotFoundError("print layout not found")


def _check_name(layouts: list[NamedLayout], named: NamedLayout) -> None:
    """Names tell layouts apart in every list: no two alike, whatever the case."""
    taken = {other.name.casefold() for other in layouts if other.id != named.id}
    if named.name.casefold() in taken:
        message = "another print layout has this name"
        raise ConflictError(message, details={"name": message}, code="print_layout_name_taken")


def check_print_layout(uow: UnitOfWork, layout_id: UUID | None) -> None:
    """Refuse a layout choice that names no layout (customers, documents, plans)."""
    if layout_id is not None and all(named.id != layout_id for named in uow.print_layouts.list()):
        raise ValidationError("print_layout_id", "unknown print layout")
