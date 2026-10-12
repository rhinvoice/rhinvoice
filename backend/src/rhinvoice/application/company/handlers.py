"""Use cases for the company, its logo and bank accounts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from rhinvoice.application.common import AddressInput, optional_email, optional_vat_number
from rhinvoice.application.errors import NotFoundError
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.company import DEFAULT_ACCENT_HUE, Company
from rhinvoice.domain.company.logo import Logo
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

    # --- Print layout ------------------------------------------------------------

    def print_layout(self) -> PrintLayout:
        with self.uow() as uow:
            return uow.company.print_layout()

    def save_print_layout(self, layout: PrintLayout) -> PrintLayout:
        with self.uow() as uow:
            uow.company.save_print_layout(layout)
            uow.commit()
        return layout

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
