"""Repositories for company, bank accounts, customers, articles and sequences."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ColumnElement,
    and_,
    delete,
    func,
    insert,
    select,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from rhinvoice.application.catalog.ports import ArticleQuery, ArticleSort
from rhinvoice.application.common import Page, SortDirection
from rhinvoice.application.customer.ports import CustomerQuery, CustomerSort
from rhinvoice.domain.catalog.article import Article
from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.company import Company
from rhinvoice.domain.company.logo import Logo
from rhinvoice.domain.company.print_layout import (
    FooterAccounts,
    LogoPosition,
    LogoSize,
    PrintFont,
    PrintLayout,
    PrintTemplate,
)
from rhinvoice.domain.customer.customer import Customer, CustomerKind
from rhinvoice.domain.numbering.sequence import NumberSequence, SequenceKind
from rhinvoice.domain.shared.address import Address
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.iban import Bic, Iban
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.vat_number import VatNumber
from rhinvoice.infrastructure.db.search import NATURAL_COLLATION, text_match
from rhinvoice.infrastructure.db.tables import (
    article_prices,
    articles,
    bank_accounts,
    company_logo,
    customers,
    number_sequences,
    print_layout,
)
from rhinvoice.infrastructure.db.tables import (
    company as company_table,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from uuid import UUID

    from sqlalchemy import Connection, RowMapping, Select

    from rhinvoice.application.common import PageRequest

# --- Mapping helpers ---------------------------------------------------------------


def _address_from_row(row: RowMapping, prefix: str = "") -> Address:
    return Address(
        street=row[f"{prefix}street"],
        house_number=row[f"{prefix}house_number"],
        supplement=row[f"{prefix}supplement"],
        postal_code=row[f"{prefix}postal_code"],
        city=row[f"{prefix}city"],
        country=CountryCode(row[f"{prefix}country"]),
    )


def _address_values(address: Address | None, prefix: str = "") -> dict[str, Any]:
    fields = ("street", "house_number", "supplement", "postal_code", "city", "country")
    if address is None:
        return dict.fromkeys((f"{prefix}{name}" for name in fields), None)
    return {
        f"{prefix}street": address.street,
        f"{prefix}house_number": address.house_number,
        f"{prefix}supplement": address.supplement,
        f"{prefix}postal_code": address.postal_code,
        f"{prefix}city": address.city,
        f"{prefix}country": address.country.value,
    }


def _optional(value: str | None, factory: Any) -> Any:  # noqa: ANN401 - generic value object factory
    return None if value is None else factory(value)


# --- Company ---------------------------------------------------------------------------


class SqlCompanyRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self) -> Company | None:
        row = self._connection.execute(select(company_table)).mappings().first()
        if row is None:
            return None
        return Company(
            id=row["id"],
            name=row["name"],
            address=_address_from_row(row),
            default_currency=Currency(row["default_currency"]),
            default_language=Language(row["default_language"]),
            email=_optional(row["email"], EmailAddress),
            phone=row["phone"],
            website=row["website"],
            vat_number=_optional(row["vat_number"], VatNumber),
            tax_number=row["tax_number"],
            commercial_register=row["commercial_register"],
            small_business=row["small_business"],
            cash_rounding=row["cash_rounding"],
            payment_terms_days=row["payment_terms_days"],
            accent_hue=row["accent_hue"],
        )

    def save(self, company: Company) -> None:
        values = {
            "id": company.id,
            "name": company.name,
            **_address_values(company.address),
            "default_currency": company.default_currency.value,
            "default_language": company.default_language.value,
            "email": None if company.email is None else company.email.value,
            "phone": company.phone,
            "website": company.website,
            "vat_number": None if company.vat_number is None else company.vat_number.value,
            "tax_number": company.tax_number,
            "commercial_register": company.commercial_register,
            "small_business": company.small_business,
            "cash_rounding": company.cash_rounding,
            "payment_terms_days": company.payment_terms_days,
            "accent_hue": company.accent_hue,
        }
        statement = pg_insert(company_table).values(values)
        self._connection.execute(
            statement.on_conflict_do_update(index_elements=["id"], set_=values),
        )

    def get_logo(self) -> Logo | None:
        row = self._connection.execute(select(company_logo)).mappings().first()
        return None if row is None else Logo(content=row["content"], media_type=row["media_type"])

    def save_logo(self, logo: Logo) -> None:
        values = {"content": logo.content, "media_type": logo.media_type}
        statement = pg_insert(company_logo).values(singleton=True, **values)
        self._connection.execute(
            statement.on_conflict_do_update(index_elements=["singleton"], set_=values),
        )

    def delete_logo(self) -> None:
        self._connection.execute(delete(company_logo))

    def print_layout(self) -> PrintLayout:
        row = self._connection.execute(select(print_layout)).mappings().first()
        if row is None:
            return PrintLayout()
        return PrintLayout(
            template=PrintTemplate(row["template"]),
            logo_position=LogoPosition(row["logo_position"]),
            logo_size=LogoSize(row["logo_size"]),
            font=PrintFont(row["font"]),
            sender_line=row["sender_line"],
            contact=row["contact"],
            position_numbers=row["position_numbers"],
            footer_accounts=FooterAccounts(row["footer_accounts"]),
            e_invoice=row["e_invoice"],
        )

    def save_print_layout(self, layout: PrintLayout) -> None:
        values = {
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
        statement = pg_insert(print_layout).values(values)
        self._connection.execute(
            statement.on_conflict_do_update(index_elements=[print_layout.c.singleton], set_=values)
        )


# --- Bank accounts -------------------------------------------------------------------------


def _bank_account_from_row(row: RowMapping) -> BankAccount:
    return BankAccount(
        id=row["id"],
        currency=Currency(row["currency"]),
        bank_name=row["bank_name"],
        holder=row["holder"],
        iban=Iban(row["iban"]),
        qr_iban=_optional(row["qr_iban"], Iban),
        bic=_optional(row["bic"], Bic),
        is_default=row["is_default"],
    )


def _bank_account_values(account: BankAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "currency": account.currency.value,
        "bank_name": account.bank_name,
        "holder": account.holder,
        "iban": account.iban.value,
        "qr_iban": None if account.qr_iban is None else account.qr_iban.value,
        "bic": None if account.bic is None else account.bic.value,
        "is_default": account.is_default,
    }


class SqlBankAccountRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list(self) -> list[BankAccount]:
        statement = select(bank_accounts).order_by(
            bank_accounts.c.currency,
            bank_accounts.c.is_default.desc(),
            bank_accounts.c.bank_name,
        )
        rows = self._connection.execute(statement).mappings()
        return [_bank_account_from_row(row) for row in rows]

    def get(self, account_id: UUID) -> BankAccount | None:
        statement = select(bank_accounts).where(bank_accounts.c.id == account_id)
        row = self._connection.execute(statement).mappings().first()
        return None if row is None else _bank_account_from_row(row)

    def add(self, account: BankAccount) -> None:
        self._connection.execute(insert(bank_accounts).values(_bank_account_values(account)))

    def update(self, account: BankAccount) -> None:
        self._connection.execute(
            update(bank_accounts)
            .where(bank_accounts.c.id == account.id)
            .values(_bank_account_values(account)),
        )

    def delete(self, account_id: UUID) -> None:
        self._connection.execute(delete(bank_accounts).where(bank_accounts.c.id == account_id))


# --- Customers ---------------------------------------------------------------------------------


def _customer_from_row(row: RowMapping) -> Customer:
    has_delivery = row["delivery_postal_code"] is not None
    return Customer(
        id=row["id"],
        number=row["number"],
        kind=CustomerKind(row["kind"]),
        address=_address_from_row(row),
        created_at=row["created_at"],
        company_name=row["company_name"],
        salutation=row["salutation"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        contact_person=row["contact_person"],
        email=_optional(row["email"], EmailAddress),
        phone=row["phone"],
        vat_number=_optional(row["vat_number"], VatNumber),
        group=row["customer_group"],
        default_currency=_optional(row["default_currency"], Currency),
        default_language=_optional(row["default_language"], Language),
        tax_exempt=row["tax_exempt"],
        default_discount=Decimal(row["default_discount"]),
        payment_terms_days=row["payment_terms_days"],
        delivery_address=_address_from_row(row, "delivery_") if has_delivery else None,
        note=row["note"],
        archived=row["archived"],
    )


def _customer_values(customer: Customer) -> dict[str, Any]:
    return {
        "id": customer.id,
        "number": customer.number,
        "kind": customer.kind.value,
        "company_name": customer.company_name,
        "salutation": customer.salutation,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "contact_person": customer.contact_person,
        **_address_values(customer.address),
        **_address_values(customer.delivery_address, "delivery_"),
        "email": None if customer.email is None else customer.email.value,
        "phone": customer.phone,
        "vat_number": None if customer.vat_number is None else customer.vat_number.value,
        "customer_group": customer.group,
        "default_currency": None
        if customer.default_currency is None
        else customer.default_currency.value,
        "default_language": None
        if customer.default_language is None
        else customer.default_language.value,
        "tax_exempt": customer.tax_exempt,
        "default_discount": customer.default_discount,
        "payment_terms_days": customer.payment_terms_days,
        "note": customer.note,
        "archived": customer.archived,
        "created_at": customer.created_at,
    }


_CUSTOMER_NAME = func.coalesce(
    func.nullif(customers.c.company_name, ""),
    func.trim(customers.c.last_name + " " + customers.c.first_name),
)

_CUSTOMER_SORT: Mapping[CustomerSort, ColumnElement[Any]] = {
    CustomerSort.NUMBER: customers.c.number.collate(NATURAL_COLLATION),
    CustomerSort.NAME: _CUSTOMER_NAME.collate(NATURAL_COLLATION),
    CustomerSort.CITY: customers.c.city.collate(NATURAL_COLLATION),
    CustomerSort.CREATED_AT: customers.c.created_at,
}


@dataclass(frozen=True, slots=True)
class _Ordering:
    column: ColumnElement[Any]
    direction: SortDirection
    tiebreak: ColumnElement[Any]
    """Unique column that makes the order (and therefore paging) deterministic."""


def _paged[T](
    connection: Connection,
    statement: Select[Any],
    ordering: _Ordering,
    page: PageRequest,
    mapper: Callable[[RowMapping], T],
) -> Page[T]:
    total = connection.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    column = ordering.column
    order = column.desc() if ordering.direction is SortDirection.DESC else column.asc()
    rows = connection.execute(
        statement.order_by(order, ordering.tiebreak).limit(page.limit).offset(page.offset),
    ).mappings()
    return Page(items=[mapper(row) for row in rows], total=total)


class SqlCustomerRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, customer_id: UUID) -> Customer | None:
        row = (
            self._connection.execute(
                select(customers).where(customers.c.id == customer_id),
            )
            .mappings()
            .first()
        )
        return None if row is None else _customer_from_row(row)

    def number_exists(self, number: str, *, exclude_id: UUID | None = None) -> bool:
        condition = customers.c.number == number
        if exclude_id is not None:
            condition = and_(condition, customers.c.id != exclude_id)
        return self._connection.execute(select(func.count()).where(condition)).scalar_one() > 0

    def all(self) -> list[Customer]:
        rows = self._connection.execute(select(customers)).mappings()
        return [_customer_from_row(row) for row in rows]

    def add(self, customer: Customer) -> None:
        self._connection.execute(insert(customers).values(_customer_values(customer)))

    def update(self, customer: Customer) -> None:
        self._connection.execute(
            update(customers)
            .where(customers.c.id == customer.id)
            .values(_customer_values(customer)),
        )

    def search(self, query: CustomerQuery) -> Page[Customer]:
        conditions: list[ColumnElement[bool]] = [true()]
        if not query.include_archived:
            conditions.append(customers.c.archived.is_(False))
        if query.search.strip():
            conditions.append(
                text_match(
                    query.search,
                    [
                        customers.c.number,
                        customers.c.company_name,
                        customers.c.first_name,
                        customers.c.last_name,
                        customers.c.contact_person,
                        customers.c.email,
                        customers.c.city,
                        customers.c.customer_group,
                    ],
                ),
            )
        statement = select(customers).where(and_(*conditions))
        return _paged(
            self._connection,
            statement,
            _Ordering(_CUSTOMER_SORT[query.sort], query.direction, customers.c.id),
            query.page,
            _customer_from_row,
        )


# --- Articles ----------------------------------------------------------------------------------


_ARTICLE_SORT: Mapping[ArticleSort, ColumnElement[Any]] = {
    ArticleSort.NUMBER: articles.c.number.collate(NATURAL_COLLATION),
    ArticleSort.NAME: articles.c.name.collate(NATURAL_COLLATION),
    ArticleSort.GROUP: articles.c.article_group.collate(NATURAL_COLLATION),
    ArticleSort.CREATED_AT: articles.c.created_at,
}


class SqlArticleRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def _prices(self, article_ids: list[UUID]) -> dict[UUID, dict[Currency, Decimal]]:
        prices: dict[UUID, dict[Currency, Decimal]] = {article_id: {} for article_id in article_ids}
        if article_ids:
            rows = self._connection.execute(
                select(article_prices).where(article_prices.c.article_id.in_(article_ids)),
            ).mappings()
            for row in rows:
                prices[row["article_id"]][Currency(row["currency"])] = Decimal(row["price"])
        return prices

    def _from_row(self, row: RowMapping, prices: Mapping[Currency, Decimal]) -> Article:
        return Article(
            id=row["id"],
            number=row["number"],
            name=row["name"],
            unit=Unit(row["unit"]),
            tax_category=TaxCategory(row["tax_category"]),
            prices=prices,
            created_at=row["created_at"],
            description=row["description"],
            group=row["article_group"],
            archived=row["archived"],
            supply=Supply(row["supply"]),
        )

    def get(self, article_id: UUID) -> Article | None:
        row = (
            self._connection.execute(
                select(articles).where(articles.c.id == article_id),
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return self._from_row(row, self._prices([article_id])[article_id])

    def number_exists(self, number: str, *, exclude_id: UUID | None = None) -> bool:
        condition = articles.c.number == number
        if exclude_id is not None:
            condition = and_(condition, articles.c.id != exclude_id)
        return self._connection.execute(select(func.count()).where(condition)).scalar_one() > 0

    def all(self) -> list[Article]:
        rows = self._connection.execute(select(articles)).mappings().all()
        prices = self._prices([row["id"] for row in rows])
        return [self._from_row(row, prices[row["id"]]) for row in rows]

    def _values(self, article: Article) -> dict[str, Any]:
        return {
            "id": article.id,
            "number": article.number,
            "name": article.name,
            "description": article.description,
            "article_group": article.group,
            "unit": article.unit.code,
            "tax_category": article.tax_category.value,
            "supply": article.supply.value,
            "archived": article.archived,
            "created_at": article.created_at,
        }

    def _replace_prices(self, article: Article) -> None:
        self._connection.execute(
            delete(article_prices).where(article_prices.c.article_id == article.id),
        )
        if article.prices:
            self._connection.execute(
                insert(article_prices),
                [
                    {"article_id": article.id, "currency": currency.value, "price": price}
                    for currency, price in article.prices.items()
                ],
            )

    def add(self, article: Article) -> None:
        self._connection.execute(insert(articles).values(self._values(article)))
        self._replace_prices(article)

    def update(self, article: Article) -> None:
        self._connection.execute(
            update(articles).where(articles.c.id == article.id).values(self._values(article)),
        )
        self._replace_prices(article)

    def search(self, query: ArticleQuery) -> Page[Article]:
        conditions: list[ColumnElement[bool]] = [true()]
        if not query.include_archived:
            conditions.append(articles.c.archived.is_(False))
        if query.search.strip():
            conditions.append(
                text_match(
                    query.search,
                    [
                        articles.c.number,
                        articles.c.name,
                        articles.c.description,
                        articles.c.article_group,
                    ],
                ),
            )
        statement = select(articles).where(and_(*conditions))
        page = _paged(
            self._connection,
            statement,
            _Ordering(_ARTICLE_SORT[query.sort], query.direction, articles.c.id),
            query.page,
            lambda row: row,
        )
        prices = self._prices([row["id"] for row in page.items])
        return Page(
            items=[self._from_row(row, prices[row["id"]]) for row in page.items],
            total=page.total,
        )


# --- Number sequences ----------------------------------------------------------------------------


def _sequence_from_row(row: RowMapping) -> NumberSequence:
    return NumberSequence(
        kind=SequenceKind(row["kind"]),
        pattern=row["pattern"],
        start_value=row["start_value"],
        yearly_reset=row["yearly_reset"],
        next_value=row["next_value"],
        last_year=row["last_year"],
    )


def _sequence_values(sequence: NumberSequence) -> dict[str, Any]:
    return {
        "kind": sequence.kind.value,
        "pattern": sequence.pattern,
        "start_value": sequence.start_value,
        "yearly_reset": sequence.yearly_reset,
        "next_value": sequence.next_value,
        "last_year": sequence.last_year,
    }


class SqlNumberSequenceRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def lock(self, kind: SequenceKind) -> NumberSequence:
        default = NumberSequence.default(kind)
        # Create the row first so that there is always something to lock; concurrent
        # first allocations then wait for each other instead of both using number 1.
        self._connection.execute(
            pg_insert(number_sequences)
            .values(_sequence_values(default))
            .on_conflict_do_nothing(index_elements=["kind"]),
        )
        statement = (
            select(number_sequences).where(number_sequences.c.kind == kind.value).with_for_update()
        )
        return _sequence_from_row(self._connection.execute(statement).mappings().one())

    def save(self, sequence: NumberSequence) -> None:
        values = _sequence_values(sequence)
        statement = pg_insert(number_sequences).values(values)
        self._connection.execute(
            statement.on_conflict_do_update(index_elements=["kind"], set_=values),
        )

    def list(self) -> list[NumberSequence]:
        rows = self._connection.execute(select(number_sequences)).mappings()
        return [_sequence_from_row(row) for row in rows]
