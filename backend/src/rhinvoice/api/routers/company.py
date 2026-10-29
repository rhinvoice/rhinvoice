from datetime import date
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, File, Response, UploadFile, status
from pydantic import Field

from rhinvoice.api.country_profiles import CountryProfileResponse
from rhinvoice.api.dependencies import NOT_IN_DEMO, ContainerDep, CurrentUser
from rhinvoice.api.schemas import (
    ERROR_RESPONSES,
    AddressFields,
    AddressSchema,
    ApiModel,
    text,
)
from rhinvoice.application.common import AddressInput
from rhinvoice.application.company.handlers import SaveBankAccount, SaveCompany
from rhinvoice.application.errors import DemoLockedError, NotFoundError
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.company import Company
from rhinvoice.domain.company.logo import MAX_LOGO_BYTES
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.email import EMAIL_PATTERN
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency

router = APIRouter(prefix="/api", tags=["company"], responses=ERROR_RESPONSES)


class CompanyAddressSchema(AddressFields):
    """The company must be located in a country with a profile."""

    country: Country

    def to_input(self) -> AddressInput:
        return self.to_input_with(self.country.value)


class CompanyRequest(ApiModel):
    name: str = text(70, required=True)
    address: CompanyAddressSchema
    default_currency: Currency
    default_language: Language = Language.DE
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    phone: str = text(100)
    website: str = text(100)
    vat_number: str | None = Field(default=None, max_length=40)
    tax_number: str = text(100)
    commercial_register: str = text(200)
    small_business: bool = False
    cash_rounding: bool = False
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    accent_hue: int = Field(default=250, ge=0, le=359)

    def to_command(self) -> SaveCompany:
        return SaveCompany(
            name=self.name,
            address=self.address.to_input(),
            default_currency=self.default_currency,
            default_language=self.default_language,
            email=self.email,
            phone=self.phone,
            website=self.website,
            vat_number=self.vat_number,
            tax_number=self.tax_number,
            commercial_register=self.commercial_register,
            small_business=self.small_business,
            cash_rounding=self.cash_rounding,
            payment_terms_days=self.payment_terms_days,
            accent_hue=self.accent_hue,
        )


class CompanyResponse(ApiModel):
    id: UUID
    name: str
    address: AddressSchema
    country: Country
    default_currency: Currency
    default_language: Language
    email: str | None
    phone: str
    website: str
    vat_number: str | None
    tax_number: str
    commercial_register: str
    small_business: bool
    cash_rounding: bool
    payment_terms_days: int
    accent_hue: int
    profile: CountryProfileResponse
    """The rules and words of the company's country."""

    @classmethod
    def of(cls, company: Company, today: date) -> Self:
        return cls(
            id=company.id,
            name=company.name,
            address=AddressSchema.of(company.address),
            country=company.country,
            default_currency=company.default_currency,
            default_language=company.default_language,
            email=None if company.email is None else str(company.email),
            phone=company.phone,
            website=company.website,
            vat_number=None if company.vat_number is None else str(company.vat_number),
            tax_number=company.tax_number,
            commercial_register=company.commercial_register,
            small_business=company.small_business,
            cash_rounding=company.cash_rounding,
            payment_terms_days=company.payment_terms_days,
            accent_hue=company.accent_hue,
            profile=CountryProfileResponse.of(profile_of(company.country), today),
        )


class LogoResponse(ApiModel):
    media_type: str
    size: int


class BankAccountRequest(ApiModel):
    currency: Currency
    bank_name: str = text(70, required=True)
    holder: str = text(70, required=True)
    iban: str = Field(max_length=42)
    qr_iban: str | None = Field(default=None, max_length=42)
    bic: str | None = Field(default=None, max_length=14)
    is_default: bool = False
    third_party: bool = False
    """The account belongs to someone else who collects the payment (ADR 0037)."""
    holder_address: AddressSchema | None = None
    """The third party's address; required for third parties, ignored otherwise."""

    def to_command(self) -> SaveBankAccount:
        return SaveBankAccount(
            currency=self.currency,
            bank_name=self.bank_name,
            holder=self.holder,
            iban=self.iban,
            qr_iban=self.qr_iban,
            bic=self.bic,
            is_default=self.is_default,
            third_party=self.third_party,
            holder_address=None if self.holder_address is None else self.holder_address.to_input(),
        )


class BankAccountResponse(ApiModel):
    id: UUID
    currency: Currency
    bank_name: str
    holder: str
    iban: str
    iban_formatted: str
    qr_iban: str | None
    bic: str | None
    is_default: bool
    third_party: bool
    holder_address: AddressSchema | None

    @classmethod
    def of(cls, account: BankAccount) -> Self:
        return cls(
            id=account.id,
            currency=account.currency,
            bank_name=account.bank_name,
            holder=account.holder,
            iban=account.iban.value,
            iban_formatted=account.iban.formatted(),
            qr_iban=None if account.qr_iban is None else account.qr_iban.value,
            bic=None if account.bic is None else account.bic.value,
            is_default=account.is_default,
            third_party=account.third_party,
            holder_address=(
                None if account.holder_address is None else AddressSchema.of(account.holder_address)
            ),
        )


@router.get("/company")
def get_company(_user: CurrentUser, container: ContainerDep) -> CompanyResponse:
    """Return the company of this installation; 404 until it has been set up."""
    company = container.company.get()
    if company is None:
        raise NotFoundError("the company has not been set up yet")
    return CompanyResponse.of(company, container.clock.today())


@router.put("/company")
def save_company(
    body: CompanyRequest, _user: CurrentUser, container: ContainerDep
) -> CompanyResponse:
    settings = container.settings
    if settings.demo and body.address.country != settings.demo_country:
        # The demo of a country stays one; the other countries have their own demos.
        raise DemoLockedError("the country of the demo company cannot be changed")
    return CompanyResponse.of(container.company.save(body.to_command()), container.clock.today())


@router.get(
    "/company/logo",
    response_class=Response,
    responses={
        status.HTTP_200_OK: {"content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}}}
    },
)
def get_logo(_user: CurrentUser, container: ContainerDep) -> Response:
    logo = container.company.get_logo()
    if logo is None:
        raise NotFoundError("no logo uploaded")
    return Response(
        content=logo.content,
        media_type=logo.media_type,
        headers={"Cache-Control": "no-cache"},
    )


@router.put("/company/logo", dependencies=[NOT_IN_DEMO])
def upload_logo(
    _user: CurrentUser,
    container: ContainerDep,
    file: Annotated[UploadFile, File(description="PNG, JPEG or WebP, at most 1 MB")],
) -> LogoResponse:
    # Synchronous on purpose: runs in the thread pool like the database access.
    # Reading one byte more than allowed lets the domain reject oversized files.
    content = file.file.read(MAX_LOGO_BYTES + 1)
    logo = container.company.set_logo(content)
    return LogoResponse(media_type=logo.media_type, size=len(logo.content))


@router.delete("/company/logo", status_code=status.HTTP_204_NO_CONTENT, dependencies=[NOT_IN_DEMO])
def delete_logo(_user: CurrentUser, container: ContainerDep) -> None:
    container.company.delete_logo()


@router.get("/bank-accounts")
def list_bank_accounts(_user: CurrentUser, container: ContainerDep) -> list[BankAccountResponse]:
    return [BankAccountResponse.of(a) for a in container.company.list_bank_accounts()]


@router.post("/bank-accounts", status_code=status.HTTP_201_CREATED)
def create_bank_account(
    body: BankAccountRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> BankAccountResponse:
    return BankAccountResponse.of(container.company.create_bank_account(body.to_command()))


@router.put("/bank-accounts/{account_id}")
def update_bank_account(
    account_id: UUID,
    body: BankAccountRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> BankAccountResponse:
    return BankAccountResponse.of(
        container.company.update_bank_account(account_id, body.to_command()),
    )


@router.delete("/bank-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_account(account_id: UUID, _user: CurrentUser, container: ContainerDep) -> None:
    container.company.delete_bank_account(account_id)
