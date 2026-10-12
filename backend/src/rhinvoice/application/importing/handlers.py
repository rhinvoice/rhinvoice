"""Import customers and articles from CSV and Excel files.

The test run and the import are the same code: the test run leaves the
transaction without committing it, so what it reports is exactly what the
import does. Rows with errors are left out and reported; the others are
imported. Duplicates are found by number, or else by name (customers: and
postal code), and skipped, updated or created anew. The existing records are
read once at the start, so a file of 10'000 rows does not query per row.

Updating keeps what the file does not say: only mapped columns with a value
change the record, so an export with fewer columns never erases data. Street
and house number change together.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from rhinvoice.application.catalog.handlers import (
    SaveArticle,
    build_article,
    next_free_article_number,
)
from rhinvoice.application.common import AddressInput
from rhinvoice.application.customer.handlers import (
    SaveCustomer,
    build_customer,
    next_free_customer_number,
)
from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.importing.fields import (
    ImportTarget,
    field_keys,
    suggest_mapping,
)
from rhinvoice.application.importing.parsing import (
    parse_amount,
    parse_country,
    parse_currency,
    parse_date,
    parse_flag,
    parse_language,
    parse_supply,
    parse_tax_category,
    parse_unit,
    parse_whole_number,
    split_postal_city,
    split_street,
)
from rhinvoice.application.importing.ports import ImportTemplate
from rhinvoice.domain.catalog.unit import DEFAULT_UNIT_CODE
from rhinvoice.domain.country.profile import NumberStyle
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from rhinvoice.application.importing.ports import ImportTable, TableReader
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.catalog.article import Article
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.country.profile import CountryProfile
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.shared.address import Address
    from rhinvoice.domain.shared.clock import Clock

MAX_TEMPLATE_NAME = 60
FIRST_DATA_ROW = 2
"""Row numbers as in the spreadsheet: row 1 holds the column names."""


class DuplicateStrategy(StrEnum):
    SKIP = "skip"
    UPDATE = "update"
    CREATE = "create"
    """Create a second record; a number that is taken gets the next free one."""


class RowStatus(StrEnum):
    NEW = "new"
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RowProblem:
    field: str
    code: str
    """required, invalid, or a specific rule such as invalid_amount or unknown_unit."""
    message: str
    value: str = ""
    """The cell's text, if the file has one for the field."""


@dataclass(frozen=True, slots=True)
class RowOutcome:
    row: int
    """Row number in the file (the column names are row 1)."""
    status: RowStatus
    number: str
    """Number of the record (new ones: the number they get); empty for errors without one."""
    name: str
    detail: str
    """Postal code and city of a customer, the price of an article."""
    problem: RowProblem | None = None


@dataclass(frozen=True, slots=True)
class ImportRequest:
    target: ImportTarget
    content: bytes
    duplicates: DuplicateStrategy = DuplicateStrategy.SKIP
    mapping: Mapping[str, int] | None = None
    """Field key -> column index; None: suggested from the column names."""
    commit: bool = False
    """False: a test run that changes nothing."""


@dataclass(frozen=True, slots=True)
class ImportRun:
    target: ImportTarget
    table: ImportTable
    mapping: dict[str, int]
    outcomes: tuple[RowOutcome, ...]
    committed: bool
    missing: tuple[tuple[str, ...], ...] = ()
    """Columns no row can do without, each as alternatives ("company_name", "last_name");
    a test run with missing columns reports them instead of rows."""

    def count(self, status: RowStatus) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is status)


@dataclass(frozen=True, slots=True)
class SaveTemplate:
    target: ImportTarget
    name: str
    columns: Mapping[str, str]


REQUIRED_COLUMNS: dict[ImportTarget, tuple[tuple[str, ...], ...]] = {
    # Without a number or a name no row can be matched or created. Everything else may
    # be missing in a file that only updates (new rows without it are reported).
    ImportTarget.CUSTOMERS: (("number", "company_name", "last_name"),),
    ImportTarget.ARTICLES: (("number", "name"),),
}
_PLACEHOLDER_NUMBER = "0"
"""Validates a new record before its number is taken from the sequence."""


@dataclass(frozen=True, slots=True)
class ImportLimits:
    """Tighter limits than the reader's own, for the public demo."""

    max_bytes: int
    max_rows: int


DEMO_IMPORT_LIMITS = ImportLimits(max_bytes=200 * 1024, max_rows=200)
"""Enough to try the import, too little to fill a shared demo with junk."""


@dataclass(frozen=True, slots=True)
class ImportHandlers:
    uow: UnitOfWorkFactory
    clock: Clock
    reader: TableReader
    limits: ImportLimits | None = None

    def run(self, request: ImportRequest) -> ImportRun:
        limits = self.limits
        if limits is not None and len(request.content) > limits.max_bytes:
            raise ValidationError(
                "file",
                f"files in the demo may have at most {limits.max_bytes // 1024} KB",
                code="demo_import_too_large",
            )
        table = self.reader.read(request.content)
        if limits is not None and len(table.rows) > limits.max_rows:
            raise ValidationError(
                "file",
                f"imports in the demo may have at most {limits.max_rows} rows",
                code="demo_import_too_many_rows",
            )
        if request.mapping is None:
            mapping = suggest_mapping(table.headers, request.target)
        else:
            mapping = _checked_mapping(request.mapping, request.target, len(table.headers))
        missing = missing_columns(mapping, request.target)
        if missing:
            if request.commit:
                names = ", ".join(" or ".join(group) for group in missing)
                raise ValidationError(
                    "mapping", f"missing columns: {names}", code="mapping_incomplete"
                )
            # The test run shows the columns, so they can be mapped by hand.
            return ImportRun(request.target, table, mapping, (), committed=False, missing=missing)
        with self.uow() as uow:
            company = uow.company.get()
            if company is None:
                raise ConflictError(
                    "set up the company before importing", code="company_not_set_up"
                )
            importer: _Rows = (
                _CustomerRows.load(uow, self.clock, company, request.duplicates)
                if request.target is ImportTarget.CUSTOMERS
                else _ArticleRows.load(uow, self.clock, company, request.duplicates)
            )
            outcomes = tuple(
                importer.row(index + FIRST_DATA_ROW, _cells(mapping, row))
                for index, row in enumerate(table.rows)
            )
            if request.commit:
                uow.commit()
        return ImportRun(request.target, table, mapping, outcomes, committed=request.commit)

    def templates(self, target: ImportTarget) -> list[ImportTemplate]:
        with self.uow() as uow:
            return uow.import_templates.list(target)

    def save_template(self, command: SaveTemplate) -> ImportTemplate:
        name = clean_text(command.name, "name", max_length=MAX_TEMPLATE_NAME, required=True)
        unknown = set(command.columns) - field_keys(command.target)
        if unknown:
            raise ValidationError(
                "columns", f"unknown fields: {', '.join(sorted(unknown))}", code="unknown_field"
            )
        columns = {key: column.strip() for key, column in command.columns.items() if column.strip()}
        if not columns:
            raise ValidationError("columns", "the template maps no column", code="empty_template")
        template = ImportTemplate(
            id=new_id(),
            target=command.target,
            name=name,
            columns=columns,
            created_at=self.clock.now(),
        )
        with self.uow() as uow:
            if uow.import_templates.name_exists(command.target, name):
                message = f"a template named {name} exists already"
                raise ConflictError(message, details={"name": message})
            uow.import_templates.add(template)
            uow.commit()
        return template

    def delete_template(self, template_id: UUID) -> None:
        with self.uow() as uow:
            if uow.import_templates.get(template_id) is None:
                raise NotFoundError("import template not found")
            uow.import_templates.delete(template_id)
            uow.commit()


def missing_columns(
    mapping: Mapping[str, int], target: ImportTarget
) -> tuple[tuple[str, ...], ...]:
    """List the needed columns that are not mapped, each with its alternatives."""
    return tuple(
        group for group in REQUIRED_COLUMNS[target] if all(key not in mapping for key in group)
    )


def _checked_mapping(
    mapping: Mapping[str, int], target: ImportTarget, width: int
) -> dict[str, int]:
    unknown = set(mapping) - field_keys(target)
    if unknown:
        raise ValidationError(
            "mapping", f"unknown fields: {', '.join(sorted(unknown))}", code="unknown_field"
        )
    if any(not 0 <= index < width for index in mapping.values()):
        raise ValidationError("mapping", "a column does not exist", code="unknown_column")
    if len(set(mapping.values())) != len(mapping):
        raise ValidationError(
            "mapping", "a column is mapped to two fields", code="column_used_twice"
        )
    return dict(mapping)


def _cells(mapping: Mapping[str, int], row: tuple[str, ...]) -> dict[str, str]:
    """Collect the non-empty values of the mapped columns by field key."""
    values = {key: row[index].strip() for key, index in mapping.items()}
    return {key: value for key, value in values.items() if value}


# Domain fields that the import fills from another column.
_SOURCE_COLUMNS = {
    "postal_code": "postal_city",
    "city": "postal_city",
    "house_number": "street",
}


def _error(row: int, error: ValidationError, cells: Mapping[str, str]) -> RowOutcome:
    name = cells.get("company_name") or cells.get("last_name") or cells.get("name", "")
    value = cells.get(error.field) or cells.get(_SOURCE_COLUMNS.get(error.field, ""), "")
    code = error.code
    if code == ValidationError.code:
        # The domain's general code: say whether the value is missing or wrong.
        code = "invalid" if value else "required"
    return RowOutcome(
        row=row,
        status=RowStatus.ERROR,
        number=cells.get("number", ""),
        name=name,
        detail="",
        problem=RowProblem(field=error.field, code=code, message=error.message, value=value),
    )


class _Rows(Protocol):
    def row(self, row: int, cells: Mapping[str, str]) -> RowOutcome: ...


def _customer_key(name: str, postal_code: str) -> tuple[str, str]:
    return name.casefold(), postal_code


@dataclass(slots=True)
class _CustomerRows:
    uow: UnitOfWork
    clock: Clock
    company: Company
    duplicates: DuplicateStrategy
    by_number: dict[str, Customer]
    by_name: dict[tuple[str, str], Customer]

    @property
    def profile(self) -> CountryProfile:
        return profile_of(self.company.country)

    @classmethod
    def load(
        cls, uow: UnitOfWork, clock: Clock, company: Company, duplicates: DuplicateStrategy
    ) -> _CustomerRows:
        rows = cls(uow, clock, company, duplicates, {}, {})
        # Oldest first: of several equal names the oldest customer is the duplicate.
        for customer in sorted(uow.customers.all(), key=lambda c: (c.created_at, c.number)):
            rows.remember(customer)
        return rows

    def remember(self, customer: Customer) -> None:
        self.by_number[customer.number] = customer
        key = _customer_key(customer.display_name, customer.address.postal_code)
        self.by_name.setdefault(key, customer)

    def row(self, row: int, cells: Mapping[str, str]) -> RowOutcome:
        try:
            return self._import(row, cells)
        except ValidationError as error:
            return _error(row, error, cells)

    def _import(self, row: int, cells: Mapping[str, str]) -> RowOutcome:
        postal_code, city, prefix_country = self._place(cells)
        company_name = cells.get("company_name", "")
        name = company_name or " ".join(
            part for part in (cells.get("first_name"), cells.get("last_name")) if part
        )
        number = cells.get("number", "")
        existing = (
            self.by_number.get(number)
            if number
            else self.by_name.get(_customer_key(name, postal_code))
            if name
            else None
        )
        if existing is not None and self.duplicates is DuplicateStrategy.SKIP:
            return RowOutcome(
                row, RowStatus.SKIPPED, existing.number, existing.display_name, _place(existing)
            )
        updating = existing if self.duplicates is DuplicateStrategy.UPDATE else None
        base = (
            SaveCustomer(
                kind=CustomerKind.COMPANY if company_name else CustomerKind.PERSON,
                address=AddressInput(postal_code="", city="", country=self.company.country.value),
            )
            if updating is None
            else _customer_command(updating)
        )
        command = self._changed(base, cells, postal_code, city, prefix_country)
        now = self.clock.now()
        if updating is not None:
            customer = build_customer(
                updating.id, updating.number, command, now=now, existing=updating
            )
            self.uow.customers.update(customer)
            status = RowStatus.UPDATED
        else:
            # Validate first: a row with errors must not use up a number.
            probe = build_customer(new_id(), _PLACEHOLDER_NUMBER, command, now=now, existing=None)
            if not number or number in self.by_number:
                number = next_free_customer_number(self.uow, self.clock.today())
            customer = replace(probe, number=number)
            self.uow.customers.add(customer)
            status = RowStatus.NEW
        self.remember(customer)
        return RowOutcome(row, status, customer.number, customer.display_name, _place(customer))

    @staticmethod
    def _place(cells: Mapping[str, str]) -> tuple[str, str, str]:
        """Postal code, city and the country of a postal code prefix ("CH-9470")."""
        postal_code, city, country = cells.get("postal_code", ""), cells.get("city", ""), ""
        if "postal_city" in cells:
            postal, place, country = split_postal_city(cells["postal_city"])
            postal_code, city = postal_code or postal, city or place
        return postal_code, city, country

    def _changed(
        self,
        base: SaveCustomer,
        cells: Mapping[str, str],
        postal_code: str,
        city: str,
        prefix_country: str,
    ) -> SaveCustomer:
        """Apply the row's values to the command; fields without a value stay as they are."""
        current = base.address

        def text(key: str, value: str) -> str:
            return cells.get(key, value)

        def optional(key: str, value: str | None) -> str | None:
            return cells.get(key, value)

        kind = base.kind
        if "company_name" in cells:
            kind = CustomerKind.COMPANY
        elif "last_name" in cells and not base.company_name:
            kind = CustomerKind.PERSON
        street, house_number = current.street, current.house_number
        if "street" in cells:
            # Street and house number change together: a new street drops the old number.
            street, house_number = cells["street"], cells.get("house_number", "")
            if not house_number:
                street, house_number = split_street(street)
        country = parse_country(cells.get("country", ""), prefix_country or current.country)
        postal_code = postal_code or current.postal_code
        if country == "DE" and len(postal_code) == len("1067") and postal_code.isdigit():
            # Spreadsheets drop the leading zero of East German postal codes (01067).
            postal_code = f"0{postal_code}"
        dot_thousands = self.profile.number_style is NumberStyle.DOT_COMMA
        return replace(
            base,
            kind=kind,
            company_name=text("company_name", base.company_name),
            salutation=text("salutation", base.salutation),
            first_name=text("first_name", base.first_name),
            last_name=text("last_name", base.last_name),
            contact_person=text("contact_person", base.contact_person),
            email=optional("email", base.email),
            phone=text("phone", base.phone),
            vat_number=optional("vat_number", base.vat_number),
            group=text("group", base.group),
            note=text("note", base.note),
            address=AddressInput(
                postal_code=postal_code,
                city=city or current.city,
                country=country,
                street=street,
                house_number=house_number,
                supplement=cells.get("supplement", current.supplement),
            ),
            default_currency=(
                parse_currency(cells["default_currency"])
                if "default_currency" in cells
                else base.default_currency
            ),
            default_language=(
                parse_language(cells["default_language"])
                if "default_language" in cells
                else base.default_language
            ),
            default_discount=(
                parse_amount(
                    cells["default_discount"].rstrip("% "),
                    "default_discount",
                    dot_thousands=dot_thousands,
                )
                if "default_discount" in cells
                else base.default_discount
            ),
            payment_terms_days=(
                parse_whole_number(cells["payment_terms_days"], "payment_terms_days")
                if "payment_terms_days" in cells
                else base.payment_terms_days
            ),
            tax_exempt=(
                parse_flag(cells["tax_exempt"], "tax_exempt")
                if "tax_exempt" in cells
                else base.tax_exempt
            ),
            customer_since=(
                parse_date(cells["customer_since"], "customer_since")
                if "customer_since" in cells
                else base.customer_since
            ),
        )


def _place(customer: Customer) -> str:
    return f"{customer.address.postal_code} {customer.address.city}".strip()


def _customer_command(customer: Customer) -> SaveCustomer:
    """Build the command that would save the customer unchanged."""
    address = customer.address
    delivery = customer.delivery_address
    return SaveCustomer(
        kind=customer.kind,
        address=_address_input(address),
        number=customer.number,
        company_name=customer.company_name,
        salutation=customer.salutation,
        first_name=customer.first_name,
        last_name=customer.last_name,
        contact_person=customer.contact_person,
        email=None if customer.email is None else str(customer.email),
        phone=customer.phone,
        vat_number=None if customer.vat_number is None else str(customer.vat_number),
        group=customer.group,
        default_currency=customer.default_currency,
        default_language=customer.default_language,
        tax_exempt=customer.tax_exempt,
        default_discount=str(customer.default_discount),
        payment_terms_days=customer.payment_terms_days,
        delivery_address=None if delivery is None else _address_input(delivery),
        note=customer.note,
    )


def _address_input(address: Address) -> AddressInput:
    return AddressInput(
        postal_code=address.postal_code,
        city=address.city,
        country=address.country.value,
        street=address.street,
        house_number=address.house_number,
        supplement=address.supplement,
    )


@dataclass(slots=True)
class _ArticleRows:
    uow: UnitOfWork
    clock: Clock
    company: Company
    duplicates: DuplicateStrategy
    by_number: dict[str, Article]
    by_name: dict[str, Article]

    @property
    def profile(self) -> CountryProfile:
        return profile_of(self.company.country)

    @classmethod
    def load(
        cls, uow: UnitOfWork, clock: Clock, company: Company, duplicates: DuplicateStrategy
    ) -> _ArticleRows:
        rows = cls(uow, clock, company, duplicates, {}, {})
        for article in sorted(uow.articles.all(), key=lambda a: (a.created_at, a.number)):
            rows.remember(article)
        return rows

    def remember(self, article: Article) -> None:
        self.by_number[article.number] = article
        self.by_name.setdefault(article.name.casefold(), article)

    def row(self, row: int, cells: Mapping[str, str]) -> RowOutcome:
        try:
            return self._import(row, cells)
        except ValidationError as error:
            return _error(row, self._price_column(error, cells), cells)

    def _price_column(self, error: ValidationError, cells: Mapping[str, str]) -> ValidationError:
        """Name the column a price came from ("price" or "price_chf") instead of "prices.CHF"."""
        if not error.field.startswith("prices."):
            return error
        currency = error.field.removeprefix("prices.")
        own = f"price_{currency.lower()}"
        column = own if own in cells else "price"
        return ValidationError(column, error.message, code=error.code)

    def _import(self, row: int, cells: Mapping[str, str]) -> RowOutcome:
        number = cells.get("number", "")
        name = cells.get("name", "")
        existing = (
            self.by_number.get(number)
            if number
            else self.by_name.get(name.casefold())
            if name
            else None
        )
        if existing is not None and self.duplicates is DuplicateStrategy.SKIP:
            return RowOutcome(
                row, RowStatus.SKIPPED, existing.number, existing.name, _price(existing)
            )
        updating = existing if self.duplicates is DuplicateStrategy.UPDATE else None
        base = SaveArticle(name=name) if updating is None else _article_command(updating)
        command = self._changed(base, cells)
        now = self.clock.now()
        if updating is not None:
            article = build_article(
                updating.id, updating.number, command, now=now, existing=updating
            )
            self.uow.articles.update(article)
            status = RowStatus.UPDATED
        else:
            probe = build_article(new_id(), _PLACEHOLDER_NUMBER, command, now=now, existing=None)
            if not number or number in self.by_number:
                number = next_free_article_number(self.uow, self.clock.today())
            article = replace(probe, number=number)
            self.uow.articles.add(article)
            status = RowStatus.NEW
        self.remember(article)
        return RowOutcome(row, status, article.number, article.name, _price(article))

    def _changed(self, base: SaveArticle, cells: Mapping[str, str]) -> SaveArticle:
        """Apply the row's values to the command; fields without a value stay as they are."""
        dot_thousands = self.profile.number_style is NumberStyle.DOT_COMMA
        prices = dict(base.prices)
        if "price" in cells:
            prices[self.company.default_currency] = parse_amount(
                cells["price"], "price", dot_thousands=dot_thousands
            )
        for key, currency in (("price_chf", Currency.CHF), ("price_eur", Currency.EUR)):
            if key in cells:
                prices[currency] = parse_amount(cells[key], key, dot_thousands=dot_thousands)
        return replace(
            base,
            name=cells.get("name", base.name),
            description=cells.get("description", base.description),
            group=cells.get("group", base.group),
            unit=parse_unit(cells["unit"], DEFAULT_UNIT_CODE) if "unit" in cells else base.unit,
            tax_category=(
                parse_tax_category(cells["tax_category"], self.profile.rates)
                if "tax_category" in cells
                else base.tax_category
            ),
            supply=parse_supply(cells["supply"]) if "supply" in cells else base.supply,
            prices=prices,
        )


def _price(article: Article) -> str:
    return " · ".join(f"{currency} {price}" for currency, price in sorted(article.prices.items()))


def _article_command(article: Article) -> SaveArticle:
    """Build the command that would save the article unchanged."""
    return SaveArticle(
        name=article.name,
        number=article.number,
        unit=article.unit.code,
        tax_category=article.tax_category,
        prices={currency: str(price) for currency, price in article.prices.items()},
        description=article.description,
        group=article.group,
        supply=article.supply,
    )
