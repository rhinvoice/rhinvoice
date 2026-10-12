"""JSON representations of frozen document data (snapshots, totals) and invoice templates.

Decimals are stored as strings to avoid any binary floating point rounding.
The format is versioned implicitly by the keys; new keys must be optional.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.company import Company
from rhinvoice.domain.company.print_layout import (
    FooterAccounts,
    LogoPosition,
    LogoSize,
    PrintFont,
    PrintLayout,
    PrintTemplate,
)
from rhinvoice.domain.customer.customer import Customer, CustomerKind
from rhinvoice.domain.document.calculation import LineAmount, TaxGroup, Totals
from rhinvoice.domain.document.document import IssueSnapshot
from rhinvoice.domain.document.lines import (
    Discount,
    DiscountKind,
    DocumentLine,
    LineKind,
    PriceMode,
)
from rhinvoice.domain.recurring.plan import InvoiceTemplate
from rhinvoice.domain.shared.address import Address
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.iban import Bic, Iban
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.vat_code import VatCode
from rhinvoice.domain.tax.vat_number import VatNumber

type Json = dict[str, Any]


def _opt(value: object | None) -> str | None:
    return None if value is None else str(value)


def address_to_json(address: Address) -> Json:
    return {
        "street": address.street,
        "house_number": address.house_number,
        "supplement": address.supplement,
        "postal_code": address.postal_code,
        "city": address.city,
        "country": address.country.value,
    }


def address_from_json(data: Json) -> Address:
    return Address(
        street=data["street"],
        house_number=data["house_number"],
        supplement=data["supplement"],
        postal_code=data["postal_code"],
        city=data["city"],
        country=CountryCode(data["country"]),
    )


def company_to_json(company: Company) -> Json:
    return {
        "id": str(company.id),
        "name": company.name,
        "address": address_to_json(company.address),
        "default_currency": company.default_currency.value,
        "default_language": company.default_language.value,
        "email": _opt(company.email),
        "phone": company.phone,
        "website": company.website,
        "vat_number": _opt(company.vat_number),
        "tax_number": company.tax_number,
        "commercial_register": company.commercial_register,
        "small_business": company.small_business,
        "cash_rounding": company.cash_rounding,
        "payment_terms_days": company.payment_terms_days,
        "accent_hue": company.accent_hue,
    }


def company_from_json(data: Json) -> Company:
    return Company(
        id=_uuid(data["id"]),
        name=data["name"],
        address=address_from_json(data["address"]),
        default_currency=Currency(data["default_currency"]),
        default_language=Language(data["default_language"]),
        email=None if data["email"] is None else EmailAddress(data["email"]),
        phone=data["phone"],
        website=data["website"],
        vat_number=None if data["vat_number"] is None else VatNumber(data["vat_number"]),
        tax_number=data["tax_number"],
        commercial_register=data["commercial_register"],
        small_business=data["small_business"],
        cash_rounding=data["cash_rounding"],
        payment_terms_days=data["payment_terms_days"],
        accent_hue=data["accent_hue"],
    )


def customer_to_json(customer: Customer) -> Json:
    return {
        "id": str(customer.id),
        "number": customer.number,
        "kind": customer.kind.value,
        "address": address_to_json(customer.address),
        "created_at": customer.created_at.isoformat(),
        "company_name": customer.company_name,
        "salutation": customer.salutation,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "contact_person": customer.contact_person,
        "email": _opt(customer.email),
        "phone": customer.phone,
        "vat_number": _opt(customer.vat_number),
        "group": customer.group,
        "default_currency": _opt(customer.default_currency),
        "default_language": _opt(customer.default_language),
        "tax_exempt": customer.tax_exempt,
        "default_discount": str(customer.default_discount),
        "payment_terms_days": customer.payment_terms_days,
        "delivery_address": (
            None
            if customer.delivery_address is None
            else address_to_json(customer.delivery_address)
        ),
        "note": customer.note,
        "archived": customer.archived,
    }


def customer_from_json(data: Json) -> Customer:
    delivery = data["delivery_address"]
    return Customer(
        id=_uuid(data["id"]),
        number=data["number"],
        kind=CustomerKind(data["kind"]),
        address=address_from_json(data["address"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        company_name=data["company_name"],
        salutation=data["salutation"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        contact_person=data["contact_person"],
        email=None if data["email"] is None else EmailAddress(data["email"]),
        phone=data["phone"],
        vat_number=None if data["vat_number"] is None else VatNumber(data["vat_number"]),
        group=data["group"],
        default_currency=None
        if data["default_currency"] is None
        else Currency(data["default_currency"]),
        default_language=None
        if data["default_language"] is None
        else Language(data["default_language"]),
        tax_exempt=data["tax_exempt"],
        default_discount=Decimal(data["default_discount"]),
        payment_terms_days=data["payment_terms_days"],
        delivery_address=None if delivery is None else address_from_json(delivery),
        note=data["note"],
        archived=data["archived"],
    )


def bank_account_to_json(account: BankAccount) -> Json:
    return {
        "id": str(account.id),
        "currency": account.currency.value,
        "bank_name": account.bank_name,
        "holder": account.holder,
        "iban": account.iban.value,
        "qr_iban": _opt(account.qr_iban),
        "bic": _opt(account.bic),
        "is_default": account.is_default,
    }


def bank_account_from_json(data: Json) -> BankAccount:
    return BankAccount(
        id=_uuid(data["id"]),
        currency=Currency(data["currency"]),
        bank_name=data["bank_name"],
        holder=data["holder"],
        iban=Iban(data["iban"]),
        qr_iban=None if data["qr_iban"] is None else Iban(data["qr_iban"]),
        bic=None if data["bic"] is None else Bic(data["bic"]),
        is_default=data["is_default"],
    )


def snapshot_to_json(snapshot: IssueSnapshot) -> Json:
    return {
        "company": company_to_json(snapshot.company),
        "customer": customer_to_json(snapshot.customer),
        "bank_account": (
            None if snapshot.bank_account is None else bank_account_to_json(snapshot.bank_account)
        ),
        "notice": snapshot.notice,
        "goods_notice": snapshot.goods_notice,
        "layout": None if snapshot.layout is None else layout_to_json(snapshot.layout),
        "accounts": (
            None
            if snapshot.accounts is None
            else [bank_account_to_json(account) for account in snapshot.accounts]
        ),
    }


def snapshot_from_json(data: Json) -> IssueSnapshot:
    account = data["bank_account"]
    # Documents issued before version 0.4 have no notice, before 0.5 no layout and accounts.
    layout = data.get("layout")
    accounts = data.get("accounts")
    return IssueSnapshot(
        company=company_from_json(data["company"]),
        customer=customer_from_json(data["customer"]),
        bank_account=None if account is None else bank_account_from_json(account),
        notice=data.get("notice"),
        goods_notice=data.get("goods_notice"),
        layout=None if layout is None else layout_from_json(layout),
        accounts=(
            None
            if accounts is None
            else tuple(bank_account_from_json(account) for account in accounts)
        ),
    )


def layout_to_json(layout: PrintLayout) -> Json:
    return {
        "template": layout.template.value,
        "logo_position": layout.logo_position.value,
        "logo_size": layout.logo_size.value,
        "font": layout.font.value,
        "sender_line": layout.sender_line,
        "contact": layout.contact,
        "position_numbers": layout.position_numbers,
        "footer_accounts": layout.footer_accounts.value,
        "e_invoice": layout.e_invoice,
    }


def layout_from_json(data: Json) -> PrintLayout:
    """Read a stored layout; choices added in later versions take their default."""
    default = PrintLayout()
    return PrintLayout(
        template=PrintTemplate(data.get("template", default.template)),
        logo_position=LogoPosition(data.get("logo_position", default.logo_position)),
        logo_size=LogoSize(data.get("logo_size", default.logo_size)),
        font=PrintFont(data.get("font", default.font)),
        sender_line=data.get("sender_line", default.sender_line),
        contact=data.get("contact", default.contact),
        position_numbers=data.get("position_numbers", default.position_numbers),
        footer_accounts=FooterAccounts(data.get("footer_accounts", default.footer_accounts)),
        e_invoice=data.get("e_invoice", default.e_invoice),
    )


def totals_to_json(totals: Totals) -> Json:
    def money(value: Money) -> str:
        return str(value.amount)

    return {
        "currency": totals.currency.value,
        "lines": [
            {
                "line_id": str(line.line_id),
                "amount": money(line.amount),
                "vat_code": line.vat_code.value,
                "tax_rate": str(line.tax_rate),
            }
            for line in totals.lines
        ],
        "groups": [
            {
                "vat_code": group.vat_code.value,
                "rate": str(group.rate),
                "amount": money(group.amount),
                "discount": money(group.discount),
                "net": money(group.net),
                "tax": money(group.tax),
            }
            for group in totals.groups
        ],
        "subtotal": money(totals.subtotal),
        "discount": money(totals.discount),
        "net": money(totals.net),
        "tax": money(totals.tax),
        "gross": money(totals.gross),
        "rounding": money(totals.rounding),
        "total": money(totals.total),
    }


def totals_from_json(data: Json) -> Totals:
    currency = Currency(data["currency"])

    def money(value: str) -> Money:
        return Money(Decimal(value), currency)

    return Totals(
        currency=currency,
        lines=tuple(
            LineAmount(
                line_id=_uuid(line["line_id"]),
                amount=money(line["amount"]),
                vat_code=VatCode(line["vat_code"]),
                tax_rate=Decimal(line["tax_rate"]),
            )
            for line in data["lines"]
        ),
        groups=tuple(
            TaxGroup(
                vat_code=VatCode(group["vat_code"]),
                rate=Decimal(group["rate"]),
                amount=money(group["amount"]),
                discount=money(group["discount"]),
                net=money(group["net"]),
                tax=money(group["tax"]),
            )
            for group in data["groups"]
        ),
        subtotal=money(data["subtotal"]),
        discount=money(data["discount"]),
        net=money(data["net"]),
        tax=money(data["tax"]),
        gross=money(data["gross"]),
        rounding=money(data["rounding"]),
        total=money(data["total"]),
    )


def _uuid(value: str) -> UUID:
    return UUID(value)


def template_to_json(template: InvoiceTemplate) -> Json:
    discount = template.discount
    return {
        "currency": template.currency.value,
        "price_mode": template.price_mode.value,
        "language": None if template.language is None else template.language.value,
        "discount": (
            None
            if discount is None
            else {"kind": discount.kind.value, "value": str(discount.value)}
        ),
        "subject": template.subject,
        "reference": template.reference,
        "intro_text": template.intro_text,
        "payment_text": template.payment_text,
        "closing_text": template.closing_text,
        "lines": [
            {
                "id": str(line.id),
                "kind": line.kind.value,
                "description": line.description,
                "details": line.details,
                "quantity": str(line.quantity),
                "unit": None if line.unit is None else line.unit.code,
                "unit_price": str(line.unit_price),
                "discount_percent": str(line.discount_percent),
                "tax_category": line.tax_category.value,
                "supply": line.supply.value,
                "article_id": _opt(line.article_id),
            }
            for line in template.lines
        ],
    }


def template_from_json(data: Json) -> InvoiceTemplate:
    discount = data["discount"]
    return InvoiceTemplate(
        currency=Currency(data["currency"]),
        price_mode=PriceMode(data["price_mode"]),
        language=None if data["language"] is None else Language(data["language"]),
        discount=(
            None
            if discount is None
            else Discount(DiscountKind(discount["kind"]), Decimal(discount["value"]))
        ),
        subject=data["subject"],
        reference=data["reference"],
        intro_text=data["intro_text"],
        payment_text=data["payment_text"],
        closing_text=data["closing_text"],
        lines=tuple(
            DocumentLine(
                id=_uuid(line["id"]),
                kind=LineKind(line["kind"]),
                description=line["description"],
                details=line["details"],
                quantity=Decimal(line["quantity"]),
                unit=None if line["unit"] is None else Unit(line["unit"]),
                unit_price=Decimal(line["unit_price"]),
                discount_percent=Decimal(line["discount_percent"]),
                tax_category=TaxCategory(line["tax_category"]),
                supply=Supply(line["supply"]),
                article_id=None if line["article_id"] is None else _uuid(line["article_id"]),
            )
            for line in data["lines"]
        ),
    )
