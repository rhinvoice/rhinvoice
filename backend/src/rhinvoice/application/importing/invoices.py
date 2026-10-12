"""Invoices of a program used before, taken over with their original PDF (ADR 0019).

Each row becomes an issued invoice with the number, dates and amounts of the
file; the PDF with that number in its name is the invoice, further files of the
number are kept as its attachments. Customers are found by number, else by
name; unknown ones are created and archived, so that old customers do not crowd
the lists. Numbers that exist already are skipped: an issued invoice is never
changed. Afterwards the invoice sequence continues behind the imported numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from rhinvoice.application.common import AddressInput
from rhinvoice.application.customer.handlers import (
    SaveCustomer,
    build_customer,
    next_free_customer_number,
)
from rhinvoice.application.document.handlers import build_index
from rhinvoice.application.importing.files import FileIndex
from rhinvoice.application.importing.parsing import (
    parse_amount,
    parse_country,
    parse_currency,
    parse_date,
    parse_document_number,
    split_postal_city,
    split_street,
)
from rhinvoice.application.importing.results import (
    PLACEHOLDER_NUMBER,
    RowOutcome,
    RowStatus,
    error_outcome,
)
from rhinvoice.application.numbering.handlers import number_in_use
from rhinvoice.domain.country.profile import NumberStyle
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.document.attachment import Attachment
from rhinvoice.domain.document.document import (
    Document,
    DocumentType,
    DraftContent,
    IssueSnapshot,
)
from rhinvoice.domain.document.lines import PriceMode
from rhinvoice.domain.numbering.sequence import SequenceKind
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Money
from rhinvoice.domain.tax.treatment import TaxTreatment

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from rhinvoice.application.importing.files import ImportFile
    from rhinvoice.application.uow import UnitOfWork
    from rhinvoice.domain.company.bank_account import BankAccount
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.shared.clock import Clock
    from rhinvoice.domain.shared.money import Currency

_NAME = re.compile(r"[^\w]+")
_COLUMNS = {"total": "total_amount", "net": "net_amount"}
_CUSTOMER_COLUMNS = {"company_name": "customer_name", "number": "customer_number"}
SAME_NAME = 0.6
"""Similarity of two names (difflib) from which they name the same customer."""
"""Fields of the domain that the file calls otherwise."""


def name_key(name: str) -> str:
    """Compare customer names regardless of case, spaces and punctuation."""
    return _NAME.sub("", name.casefold())


def _same_customer(name: str, known: str) -> bool:
    """Whether the file's name fits the customer of that number, also after a renaming.

    "Farben Kobold KG" is "FarbenKobold GmbH" after a change of legal form; "Muster AG"
    with the number of "Bäckerei Huber" is another customer.
    """
    ours, theirs = name_key(name), name_key(known)
    shorter, longer = sorted((ours, theirs), key=len)
    return shorter in longer or SequenceMatcher(None, ours, theirs).ratio() >= SAME_NAME


@dataclass(slots=True)
class InvoiceRows:
    uow: UnitOfWork
    clock: Clock
    company: Company
    accounts: list[BankAccount]
    files: FileIndex
    by_number: dict[str, Customer]
    by_name: dict[str, Customer]
    numbers: set[str]
    """Invoice numbers taken in this import."""
    store_files: bool
    """False in a test run: the files are matched and checked, not written."""

    @classmethod
    def load(
        cls,
        uow: UnitOfWork,
        clock: Clock,
        company: Company,
        files: tuple[ImportFile, ...],
        *,
        store_files: bool,
    ) -> InvoiceRows:
        rows = cls(
            uow,
            clock,
            company,
            uow.bank_accounts.list(),
            FileIndex(files),
            {},
            {},
            set(),
            store_files,
        )
        # Oldest first: of several equal names the oldest customer is the one meant.
        for customer in sorted(uow.customers.all(), key=lambda c: (c.created_at, c.number)):
            rows.remember(customer)
        return rows

    def remember(self, customer: Customer) -> None:
        self.by_number[customer.number] = customer
        self.by_name.setdefault(name_key(customer.display_name), customer)

    def row(self, row: int, cells: Mapping[str, str]) -> RowOutcome:
        try:
            return self._import(row, cells)
        except ValidationError as error:
            column = _COLUMNS.get(error.field, error.field)
            named = ValidationError(column, error.message, code=error.code)
            outcome = error_outcome(row, named, cells)
            return replace(outcome, number=parse_document_number(outcome.number))

    def _amount(self, cells: Mapping[str, str], key: str, currency: Currency) -> Money | None:
        if key not in cells:
            return None
        dot_thousands = profile_of(self.company.country).number_style is NumberStyle.DOT_COMMA
        return Money(Decimal(parse_amount(cells[key], key, dot_thousands=dot_thousands)), currency)

    def _import(self, row: int, cells: Mapping[str, str]) -> RowOutcome:
        number = parse_document_number(cells.get("number", ""))
        if not number:
            raise ValidationError("number", "number is required")
        if number in self.numbers or self.uow.documents.number_exists(DocumentType.INVOICE, number):
            # Issued invoices are never changed, also not by importing them again.
            return RowOutcome(row, RowStatus.SKIPPED, number, cells.get("customer_name", ""), "")
        issue_date = parse_date(cells.get("issue_date", ""), "issue_date")
        due_date = parse_date(cells["due_date"], "due_date") if "due_date" in cells else None
        customer, wanted_number = self._customer(cells, issue_date)
        new_customer = wanted_number is not None
        currency = (
            parse_currency(cells.get("currency", ""))
            or customer.default_currency
            or self.company.default_currency
        )
        total, net, open_amount = self._amounts(cells, currency)
        content = DraftContent(
            customer_id=customer.id,
            currency=currency,
            language=customer.default_language or self.company.default_language,
            price_mode=PriceMode.NET,
            lines=(),
            treatment=TaxTreatment.DOMESTIC,
            issue_date=issue_date,
            due_date=due_date,
            subject=cells.get("subject", ""),
        )
        match = self.files.find(number)
        now = self.clock.now()
        document = Document.imported(
            new_id(),
            number=number,
            content=content,
            snapshot=IssueSnapshot(
                company=self.company, customer=customer, bank_account=self._account(currency)
            ),
            net=net,
            total=total,
            open_amount=open_amount,
            now=now,
            source="" if match is None or match.invoice is None else match.invoice.path,
        )
        # Checked before anything is written: a row is saved whole or not at all.
        attachments = [
            (
                Attachment(
                    id=new_id(),
                    document_id=document.id,
                    file_name=file.path,
                    sha256=file.sha256,
                    size=len(file.content),
                    added_at=now,
                ),
                file.content,
            )
            for file in (() if match is None else match.attachments)
        ]
        if wanted_number is not None:
            # Only now, with the row valid, the customer takes a number.
            if not wanted_number or wanted_number in self.by_number:
                wanted_number = next_free_customer_number(self.uow, self.clock.today())
            customer = replace(customer, number=wanted_number)
            document = replace(
                document, snapshot=replace(document.issued_snapshot, customer=customer)
            )
            self.uow.customers.add(customer)
            self.remember(customer)
        self.uow.documents.add(document, build_index(document, document.frozen_totals, customer))
        self.numbers.add(number)
        original = None if match is None else match.invoice
        if match is not None:
            self.files.claim(match)
        self._store(document, original, attachments)
        return RowOutcome(
            row,
            RowStatus.NEW,
            number,
            customer.display_name,
            f"{currency} {total.amount}",
            file=None if original is None else original.path,
            attachments=len(attachments),
            new_customer=new_customer,
        )

    def _amounts(self, cells: Mapping[str, str], currency: Currency) -> tuple[Money, Money, Money]:
        """Total, net and open amount of a row."""
        total = self._amount(cells, "total_amount", currency)
        if total is None:
            raise ValidationError("total_amount", "total_amount is required")
        net = self._amount(cells, "net_amount", currency)
        if net is None:
            # Without a net amount the tax tells it; without both the total counts as net.
            tax = self._amount(cells, "tax_amount", currency)
            net = total if tax is None else total - tax
        # Without an open amount the invoice counts as paid: it is an old one.
        open_amount = self._amount(cells, "open_amount", currency) or Money.zero(currency)
        return total, net, open_amount

    def _store(
        self,
        document: Document,
        original: ImportFile | None,
        attachments: list[tuple[Attachment, bytes]],
    ) -> None:
        """Write the invoice's files; a test run only checks them."""
        if not self.store_files:
            return
        if original is not None:
            archived = document.archive_pdf(original.sha256)
            self.uow.documents.archive_pdf(archived, original.content)
        for attachment, content in attachments:
            self.uow.documents.add_attachment(attachment, content)

    def _account(self, currency: Currency) -> BankAccount | None:
        """Pick the default account of the currency, for reminders of open invoices."""
        return next(
            (
                account
                for account in self.accounts
                if account.currency is currency and account.is_default
            ),
            None,
        )

    def _customer(self, cells: Mapping[str, str], since: date) -> tuple[Customer, str | None]:
        """Find the customer by number, else by name; else build an archived one.

        A new customer comes with the number it asks for ("" for the next free one), a
        known one with None.
        """
        number = cells.get("customer_number", "")
        name = cells.get("customer_name", "")
        known = self.by_number.get(number) if number else None
        if known is not None and name and not _same_customer(name, known.display_name):
            # The old program's numbers may be Rhinvoice's numbers of other customers.
            known = None
            number = ""
        if known is None and name:
            known = self.by_name.get(name_key(name))
        if known is not None:
            return known, None
        if not name:
            raise ValidationError("customer_name", "customer_name is required")
        postal_code, city = cells.get("postal_code", ""), cells.get("city", "")
        prefix_country = ""
        if "postal_city" in cells:
            postal, place, prefix_country = split_postal_city(cells["postal_city"])
            postal_code, city = postal_code or postal, city or place
        street, house_number = split_street(cells.get("street", ""))
        command = SaveCustomer(
            kind=CustomerKind.COMPANY,
            company_name=name,
            address=AddressInput(
                postal_code=postal_code,
                city=city,
                country=parse_country(
                    cells.get("country", ""), prefix_country or self.company.country.value
                ),
                street=street,
                house_number=house_number,
            ),
            customer_since=since,
        )
        try:
            customer = build_customer(
                new_id(), PLACEHOLDER_NUMBER, command, now=self.clock.now(), existing=None
            )
        except ValidationError as error:
            # The customer's fields are the file's customer columns.
            column = _CUSTOMER_COLUMNS.get(error.field, error.field)
            raise ValidationError(column, error.message, code=error.code) from error
        return customer.archive(), number

    def continue_numbering(self) -> str:
        """Move the invoice sequence behind the imported numbers; return the next number."""
        today = self.clock.today()
        sequence = self.uow.sequences.lock(SequenceKind.INVOICE)
        while number_in_use(self.uow, SequenceKind.INVOICE, sequence.preview(today)):
            _, sequence = sequence.allocate(today)
        self.uow.sequences.save(sequence)
        return sequence.preview(today)
