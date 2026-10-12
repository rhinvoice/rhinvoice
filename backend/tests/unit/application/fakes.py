"""In-memory implementations of the application ports for fast unit tests."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Self
from uuid import UUID

from rhinvoice.application.backup.ports import BackupReason, BackupRun, RunStatus
from rhinvoice.application.catalog.ports import ArticleQuery, ArticleSort
from rhinvoice.application.common import Page, SortDirection
from rhinvoice.application.customer.ports import CustomerQuery, CustomerSort
from rhinvoice.application.document.ports import (
    CurrencyFigures,
    CurrencyTotals,
    CustomerRevenue,
    DocumentFacets,
    DocumentIndex,
    DocumentQuery,
    DocumentSort,
    DocumentSummary,
    MonthlyRevenue,
)
from rhinvoice.application.importing.ports import ImportTemplate
from rhinvoice.application.onboarding.ports import OnboardingMarks
from rhinvoice.domain.catalog.article import Article
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.print_layout import PrintLayout
from rhinvoice.domain.customer.customer import Customer
from rhinvoice.domain.document.attachment import Attachment
from rhinvoice.domain.document.document import (
    OPEN_INVOICE_STATUSES,
    DisplayStatus,
    DocumentStatus,
    DocumentType,
    EventKind,
)
from rhinvoice.domain.dunning.reminder import DEFAULT_LEVELS, DunningLevel, Reminder
from rhinvoice.domain.identity.session import Session
from rhinvoice.domain.identity.user import User
from rhinvoice.domain.mail.template import MailKind, MailTemplate
from rhinvoice.domain.numbering.sequence import NumberSequence, SequenceKind
from rhinvoice.domain.recurring.plan import PlanRun, RecurringPlan
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.text.template import TextKind, TextTemplate

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Sequence
    from datetime import datetime
    from types import TracebackType
    from zoneinfo import ZoneInfo

    from rhinvoice.application.importing.fields import ImportTarget
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.company.logo import Logo
    from rhinvoice.domain.document.document import Document
    from rhinvoice.domain.mail.server import MailServer
    from rhinvoice.domain.shared.email import EmailAddress


@dataclass
class StoredDocument:
    document: Document
    index: DocumentIndex


@dataclass(frozen=True, slots=True)
class BackupRequest:
    reason: BackupReason
    at: datetime
    handled: bool = False


@dataclass
class Store:
    """State shared by all units of work, i.e. the "database"."""

    users: dict[UUID, User] = field(default_factory=dict[UUID, User])
    sessions: dict[str, Session] = field(default_factory=dict[str, Session])
    company: Company | None = None
    logo: Logo | None = None
    bank_accounts: dict[UUID, BankAccount] = field(default_factory=dict[UUID, BankAccount])
    customers: dict[UUID, Customer] = field(default_factory=dict[UUID, Customer])
    articles: dict[UUID, Article] = field(default_factory=dict[UUID, Article])
    sequences: dict[SequenceKind, NumberSequence] = field(
        default_factory=dict[SequenceKind, NumberSequence],
    )
    documents: dict[UUID, StoredDocument] = field(default_factory=dict[UUID, StoredDocument])
    text_templates: dict[UUID, TextTemplate] = field(default_factory=dict[UUID, TextTemplate])
    pdfs: dict[UUID, bytes] = field(default_factory=dict[UUID, bytes])
    e_invoices: dict[UUID, bytes] = field(default_factory=dict[UUID, bytes])
    attachments: dict[UUID, tuple[Attachment, bytes]] = field(
        default_factory=dict[UUID, tuple[Attachment, bytes]]
    )
    legal_notices: dict[tuple[TaxTreatment, Language], str] = field(
        default_factory=dict[tuple[TaxTreatment, Language], str],
    )
    backup_requests: list[BackupRequest] = field(default_factory=list[BackupRequest])
    backup_runs: list[BackupRun] = field(default_factory=list[BackupRun])
    """In the order the backup container started them."""
    import_templates: dict[UUID, ImportTemplate] = field(default_factory=dict[UUID, ImportTemplate])
    numbering_checked_at: datetime | None = None
    onboarding_dismissed_at: datetime | None = None
    print_layout: PrintLayout | None = None
    dunning_levels: list[DunningLevel] = field(default_factory=list[DunningLevel])
    reminders: dict[UUID, Reminder] = field(default_factory=dict[UUID, Reminder])
    mail_server: MailServer | None = None
    plans: dict[UUID, RecurringPlan] = field(default_factory=dict[UUID, RecurringPlan])
    runs: list[PlanRun] = field(default_factory=list[PlanRun])
    mail_templates: dict[tuple[MailKind, Language], MailTemplate] = field(
        default_factory=dict[tuple[MailKind, Language], MailTemplate],
    )


class InMemoryUserRepository:
    def __init__(self, data: dict[UUID, User]) -> None:
        self.data = data
        self.locked = False
        self.locked_rows = 0

    def get(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        self.locked_rows += int(for_update)
        return self.data.get(user_id)

    def get_by_email(self, email: EmailAddress, *, for_update: bool = False) -> User | None:
        self.locked_rows += int(for_update)
        return next((u for u in self.data.values() if u.email == email), None)

    def add(self, user: User) -> None:
        self.data[user.id] = user

    def update(self, user: User) -> None:
        self.data[user.id] = user

    def count(self) -> int:
        return len(self.data)

    def lock(self) -> None:
        self.locked = True


class InMemorySessionRepository:
    def __init__(self, data: dict[str, Session]) -> None:
        self.data = data

    def get(self, token_hash: str) -> Session | None:
        return self.data.get(token_hash)

    def add(self, session: Session) -> None:
        self.data[session.token_hash] = session

    def update(self, session: Session) -> None:
        self.data[session.token_hash] = session

    def delete(self, token_hash: str) -> None:
        self.data.pop(token_hash, None)

    def delete_for_user(self, user_id: UUID, *, except_token_hash: str | None = None) -> None:
        for token_hash, session in list(self.data.items()):
            if session.user_id == user_id and token_hash != except_token_hash:
                del self.data[token_hash]


def _folded(text: str) -> str:
    """Lower case without accents, like unaccent + ILIKE in PostgreSQL."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _folded_de(text: str) -> str:
    """German umlaut spelling, like rhinvoice_fold_de in PostgreSQL."""
    for umlaut, spelled in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.casefold().replace(umlaut, spelled)
    return _folded(text)


def _matches(search: str, values: list[str]) -> bool:
    needle = _folded(search.strip())
    return any(needle in _folded(value) or needle in _folded_de(value) for value in values)


def _page[T](items: list[T], offset: int, limit: int) -> Page[T]:
    return Page(items=items[offset : offset + limit], total=len(items))


class InMemoryCompanyRepository:
    def __init__(
        self, company: Company | None, logo: Logo | None, layout: PrintLayout | None = None
    ) -> None:
        self.company = company
        self.logo = logo
        self.layout = layout

    def get(self) -> Company | None:
        return self.company

    def save(self, company: Company) -> None:
        self.company = company

    def get_logo(self) -> Logo | None:
        return self.logo

    def save_logo(self, logo: Logo) -> None:
        self.logo = logo

    def delete_logo(self) -> None:
        self.logo = None

    def print_layout(self) -> PrintLayout:
        return PrintLayout() if self.layout is None else self.layout

    def save_print_layout(self, layout: PrintLayout) -> None:
        self.layout = layout


class InMemoryBankAccountRepository:
    def __init__(self, data: dict[UUID, BankAccount]) -> None:
        self.data = data

    def list(self) -> list[BankAccount]:
        return sorted(
            self.data.values(),
            key=lambda account: (account.currency.value, not account.is_default, account.bank_name),
        )

    def get(self, account_id: UUID) -> BankAccount | None:
        return self.data.get(account_id)

    def add(self, account: BankAccount) -> None:
        self.data[account.id] = account

    def update(self, account: BankAccount) -> None:
        self.data[account.id] = account

    def delete(self, account_id: UUID) -> None:
        del self.data[account_id]


class InMemoryCustomerRepository:
    def __init__(self, data: dict[UUID, Customer]) -> None:
        self.data = data

    def get(self, customer_id: UUID) -> Customer | None:
        return self.data.get(customer_id)

    def number_exists(self, number: str, *, exclude_id: UUID | None = None) -> bool:
        return any(c.number == number and c.id != exclude_id for c in self.data.values())

    def all(self) -> list[Customer]:
        return list(self.data.values())

    def add(self, customer: Customer) -> None:
        self.data[customer.id] = customer

    def update(self, customer: Customer) -> None:
        self.data[customer.id] = customer

    def search(self, query: CustomerQuery) -> Page[Customer]:
        found = [
            customer
            for customer in self.data.values()
            if (query.include_archived or not customer.archived)
            and (
                not query.search.strip()
                or _matches(
                    query.search,
                    [
                        customer.number,
                        customer.display_name,
                        customer.contact_person,
                        str(customer.email or ""),
                        customer.address.city,
                        customer.group,
                    ],
                )
            )
        ]
        keys: dict[CustomerSort, Callable[[Customer], str]] = {
            CustomerSort.NUMBER: lambda c: c.number,
            CustomerSort.NAME: lambda c: c.display_name.lower(),
            CustomerSort.CITY: lambda c: c.address.city.lower(),
            CustomerSort.CREATED_AT: lambda c: c.created_at.isoformat(),
        }
        found.sort(key=keys[query.sort], reverse=query.direction is SortDirection.DESC)
        return _page(found, query.page.offset, query.page.limit)


class InMemoryArticleRepository:
    def __init__(self, data: dict[UUID, Article]) -> None:
        self.data = data

    def get(self, article_id: UUID) -> Article | None:
        return self.data.get(article_id)

    def number_exists(self, number: str, *, exclude_id: UUID | None = None) -> bool:
        return any(a.number == number and a.id != exclude_id for a in self.data.values())

    def all(self) -> list[Article]:
        return list(self.data.values())

    def add(self, article: Article) -> None:
        self.data[article.id] = article

    def update(self, article: Article) -> None:
        self.data[article.id] = article

    def search(self, query: ArticleQuery) -> Page[Article]:
        found = [
            article
            for article in self.data.values()
            if (query.include_archived or not article.archived)
            and (
                not query.search.strip()
                or _matches(
                    query.search, [article.number, article.name, article.description, article.group]
                )
            )
        ]
        keys: dict[ArticleSort, Callable[[Article], str]] = {
            ArticleSort.NUMBER: lambda a: a.number,
            ArticleSort.NAME: lambda a: a.name.lower(),
            ArticleSort.GROUP: lambda a: a.group.lower(),
            ArticleSort.CREATED_AT: lambda a: a.created_at.isoformat(),
        }
        found.sort(key=keys[query.sort], reverse=query.direction is SortDirection.DESC)
        return _page(found, query.page.offset, query.page.limit)


class InMemoryNumberSequenceRepository:
    def __init__(self, data: dict[SequenceKind, NumberSequence]) -> None:
        self.data = data
        self.locked: list[SequenceKind] = []

    def lock(self, kind: SequenceKind) -> NumberSequence:
        self.locked.append(kind)
        return self.data.setdefault(kind, NumberSequence.default(kind))

    def save(self, sequence: NumberSequence) -> None:
        self.data[sequence.kind] = sequence

    def list(self) -> list[NumberSequence]:
        return list(self.data.values())


def _document_date(document: Document, zone: ZoneInfo) -> date:
    local = document.created_at.astimezone(zone).date()
    return document.content.issue_date or local


def _selected(stored: StoredDocument, query: DocumentQuery, *, with_status: bool = True) -> bool:
    document = stored.document
    status = document.display_status(query.today)
    customer = query.customer_id
    return (
        document.type in query.types
        and (not with_status or not query.statuses or status in query.statuses)
        and (customer is None or document.content.customer_id == customer)
        and (query.origin is None or document.origin is query.origin)
        and (query.year is None or _document_date(document, query.zone).year == query.year)
        and all(_matches(word, [stored.index.search_text]) for word in query.search.split())
    )


class InMemoryDocumentRepository:
    def __init__(
        self,
        data: dict[UUID, StoredDocument],
        pdfs: dict[UUID, bytes],
        e_invoices: dict[UUID, bytes],
        attachments: dict[UUID, tuple[Attachment, bytes]],
    ) -> None:
        self.data = data
        self.pdfs = pdfs
        self.e_invoices = e_invoices
        self.saved_attachments = attachments
        self.locked: list[UUID] = []

    def get(self, document_id: UUID, *, for_update: bool = False) -> Document | None:
        if for_update:
            self.locked.append(document_id)
        stored = self.data.get(document_id)
        return None if stored is None else stored.document

    def add(self, document: Document, index: DocumentIndex) -> None:
        assert document.id not in self.data
        self.data[document.id] = StoredDocument(document, index)

    def update(self, document: Document, index: DocumentIndex) -> None:
        assert document.id in self.data
        self.data[document.id] = StoredDocument(document, index)

    def delete(self, document_id: UUID) -> None:
        del self.data[document_id]

    def number_exists(self, document_type: DocumentType, number: str) -> bool:
        return any(
            stored.document.type is document_type and stored.document.number == number
            for stored in self.data.values()
        )

    def latest_issue_date(self, document_type: DocumentType) -> date | None:
        dates = [
            stored.document.content.issue_date
            for stored in self.data.values()
            if stored.document.type is document_type and not stored.document.is_draft
        ]
        return max((day for day in dates if day is not None), default=None)

    def _summary(self, stored: StoredDocument, today: date) -> DocumentSummary:
        document = stored.document
        return DocumentSummary(
            id=document.id,
            type=document.type,
            status=document.status,
            display_status=document.display_status(today),
            number=document.number,
            customer_id=document.content.customer_id,
            customer_name=stored.index.customer_name,
            subject=document.content.subject,
            issue_date=document.content.issue_date,
            due_date=document.content.due_date,
            currency=document.content.currency,
            total=stored.index.total,
            open_amount=stored.index.open_amount,
            created_at=document.created_at,
            imported=document.is_imported,
        )

    def search(self, query: DocumentQuery) -> Page[DocumentSummary]:
        found = [
            self._summary(stored, query.today)
            for stored in self.data.values()
            if _selected(stored, query)
        ]
        descending = query.direction is SortDirection.DESC
        # Created first, then the sort key: equal keys keep the creation order.
        found.sort(key=lambda summary: summary.created_at, reverse=descending)
        if query.sort is DocumentSort.DUE_DATE:
            found.sort(key=lambda summary: summary.due_date or date.max, reverse=descending)
        return _page(found, query.page.offset, query.page.limit)

    def get_pdf(self, document_id: UUID) -> bytes | None:
        return self.pdfs.get(document_id)

    def get_e_invoice(self, document_id: UUID) -> bytes | None:
        return self.e_invoices.get(document_id)

    def archive_pdf(
        self, document: Document, content: bytes, e_invoice: bytes | None = None
    ) -> None:
        # Like the database triggers: once only, and the content must match the hash.
        assert document.id not in self.pdfs
        assert document.pdf_sha256 == hashlib.sha256(content).hexdigest()
        stored = self.data[document.id]
        self.data[document.id] = StoredDocument(document, stored.index)
        self.pdfs[document.id] = content
        if e_invoice is not None:
            self.e_invoices[document.id] = e_invoice

    def add_attachment(self, attachment: Attachment, content: bytes) -> None:
        # Like the database trigger: issued documents only, and the content must match.
        assert not self.data[attachment.document_id].document.is_draft
        assert attachment.sha256 == hashlib.sha256(content).hexdigest()
        assert attachment.id not in self.saved_attachments
        self.saved_attachments[attachment.id] = (attachment, content)

    def attachments(self, document_id: UUID) -> list[Attachment]:
        found = [
            attachment
            for attachment, _ in self.saved_attachments.values()
            if attachment.document_id == document_id
        ]
        return sorted(found, key=lambda attachment: (attachment.file_name, str(attachment.id)))

    def get_attachment(
        self, document_id: UUID, attachment_id: UUID
    ) -> tuple[Attachment, bytes] | None:
        stored = self.saved_attachments.get(attachment_id)
        return stored if stored is not None and stored[0].document_id == document_id else None

    def facets(self, query: DocumentQuery) -> DocumentFacets:
        totals: dict[Currency, CurrencyTotals] = {}
        counts: dict[DisplayStatus, int] = {}
        for stored in self.data.values():
            document = stored.document
            if document.type is not DocumentType.CANCELLATION and _selected(
                stored, query, with_status=False
            ):
                status = document.display_status(query.today)
                counts[status] = counts.get(status, 0) + 1
            counted = (
                document.status not in {DocumentStatus.DRAFT, DocumentStatus.CANCELLED}
                and document.type is not DocumentType.CANCELLATION
            )
            if not counted or not _selected(stored, query):
                continue
            currency = document.content.currency
            zero = Money.zero(currency)
            sums = totals.get(currency, CurrencyTotals(currency, 0, zero, zero))
            is_open = document.status in OPEN_INVOICE_STATUSES
            totals[currency] = CurrencyTotals(
                currency=currency,
                count=sums.count + 1,
                total=sums.total + stored.index.total,
                open=sums.open + (stored.index.open_amount if is_open else zero),
            )
        years = {
            _document_date(stored.document, query.zone).year
            for stored in self.data.values()
            if stored.document.type in query.types
        }
        return DocumentFacets(
            totals=[totals[currency] for currency in sorted(totals)],
            status_counts=counts,
            years=sorted(years, reverse=True),
        )

    def figures(self, today: date) -> list[CurrencyFigures]:
        by_currency: dict[Currency, CurrencyFigures] = {}
        for stored in self.data.values():
            document = stored.document
            if document.type is not DocumentType.INVOICE or document.is_draft:
                continue
            currency = document.content.currency
            zero = Money.zero(currency)
            figures = by_currency.get(currency, CurrencyFigures(currency, zero, zero, zero, 0, 0))
            is_open = document.status in OPEN_INVOICE_STATUSES
            overdue = is_open and document.display_status(today) is DisplayStatus.OVERDUE
            counts_paid = is_open or document.status is DocumentStatus.PAID
            open_amount = stored.index.open_amount
            by_currency[currency] = CurrencyFigures(
                currency=currency,
                open=figures.open + (open_amount if is_open else zero),
                overdue=figures.overdue + (open_amount if overdue else zero),
                paid=figures.paid + (stored.index.total - open_amount if counts_paid else zero),
                open_count=figures.open_count + is_open,
                overdue_count=figures.overdue_count + overdue,
            )
        return [by_currency[currency] for currency in sorted(by_currency)]

    def revenue_by_month(self, since: date) -> list[MonthlyRevenue]:
        totals: dict[tuple[date, Currency], Money] = {}
        for stored in self.data.values():
            document = stored.document
            issue_date = document.content.issue_date
            if (
                document.type is DocumentType.QUOTE
                or document.is_draft
                or issue_date is None
                or issue_date < since
            ):
                continue
            key = (issue_date.replace(day=1), document.content.currency)
            totals[key] = totals.get(key, Money.zero(key[1])) + stored.index.net
        return [
            MonthlyRevenue(month=month, currency=currency, net=totals[month, currency])
            for month, currency in sorted(totals)
        ]

    def revenue_by_customer(self, since: date) -> list[CustomerRevenue]:
        totals: dict[tuple[UUID, Currency], Money] = {}
        names: dict[tuple[UUID, Currency], tuple[tuple[date, datetime], str]] = {}
        for stored in self.data.values():
            document = stored.document
            issue_date = document.content.issue_date
            if (
                document.type is DocumentType.QUOTE
                or document.is_draft
                or issue_date is None
                or issue_date < since
            ):
                continue
            key = (document.content.customer_id, document.content.currency)
            totals[key] = totals.get(key, Money.zero(key[1])) + stored.index.net
            # The name on the latest document, like ORDER BY issue_date DESC, created_at DESC.
            latest = (issue_date, document.created_at)
            if key not in names or latest >= names[key][0]:
                names[key] = (latest, stored.index.customer_name)
        ranked = sorted(totals, key=lambda key: (-totals[key].amount, str(key[0])))
        return [
            CustomerRevenue(
                customer, names[customer, currency][1], currency, totals[customer, currency]
            )
            for customer, currency in ranked
        ]

    def revenue_between(self, start: date, end: date) -> dict[Currency, Money]:
        totals: dict[Currency, Money] = {}
        for stored in self.data.values():
            document = stored.document
            issue_date = document.content.issue_date
            if (
                document.type is DocumentType.QUOTE
                or document.is_draft
                or issue_date is None
                or not start <= issue_date <= end
            ):
                continue
            currency = document.content.currency
            totals[currency] = totals.get(currency, Money.zero(currency)) + stored.index.net
        return totals

    def days_to_pay(self, since: date) -> list[tuple[Currency, int]]:
        found: list[tuple[date, str, Currency, int]] = []
        for stored in self.data.values():
            document = stored.document
            issue_date = document.content.issue_date
            if (
                document.type is not DocumentType.INVOICE
                or document.status is not DocumentStatus.PAID
                or document.is_imported
                or issue_date is None
            ):
                continue
            last = max(payment.paid_on for payment in document.payments)
            if last >= since:
                found.append(
                    (last, str(document.id), document.content.currency, (last - issue_date).days)
                )
        return [(currency, days) for _, _, currency, days in sorted(found)]

    def recent_events(self, limit: int, today: date) -> list[tuple[DocumentSummary, str, datetime]]:
        # Newest recorded first among equal times, like ORDER BY at DESC, id DESC.
        events = [
            (self._summary(stored, today), event.kind.value, event.at)
            for stored in reversed(self.data.values())
            for event in reversed(stored.document.events)
            if event.kind is not EventKind.IMPORTED
        ]
        events.sort(key=lambda entry: entry[2], reverse=True)
        return events[:limit]


class InMemoryTextTemplateRepository:
    def __init__(self, data: dict[UUID, TextTemplate]) -> None:
        self.data = data

    def list(self) -> list[TextTemplate]:
        kinds = list(TextKind)
        return sorted(
            self.data.values(),
            key=lambda template: (
                template.document_type.value,
                template.language.value,
                kinds.index(template.kind),
                template.position,
                template.id,
            ),
        )

    def get(self, template_id: UUID) -> TextTemplate | None:
        return self.data.get(template_id)

    def add(self, template: TextTemplate) -> None:
        assert template.id not in self.data
        self.data[template.id] = template

    def update(self, template: TextTemplate) -> None:
        assert template.id in self.data
        self.data[template.id] = template

    def delete(self, template_id: UUID) -> None:
        del self.data[template_id]


class InMemoryLegalNoticeRepository:
    def __init__(self, data: dict[tuple[TaxTreatment, Language], str]) -> None:
        self.data = data

    def get(self, treatment: TaxTreatment, language: Language) -> str | None:
        return self.data.get((treatment, language))

    def all(self) -> dict[tuple[TaxTreatment, Language], str]:
        return dict(self.data)

    def save(self, treatment: TaxTreatment, language: Language, text: str) -> None:
        self.data[treatment, language] = text

    def delete(self, treatment: TaxTreatment, language: Language) -> None:
        self.data.pop((treatment, language), None)


class InMemoryBackupRepository:
    def __init__(self, requests: list[BackupRequest], runs: list[BackupRun]) -> None:
        self.requests = requests
        self.data = runs

    def request(self, reason: BackupReason, at: datetime) -> None:
        self.requests.append(BackupRequest(reason, at))

    def pending_since(self) -> datetime | None:
        return min((request.at for request in self.requests if not request.handled), default=None)

    def runs(self, limit: int) -> list[BackupRun]:
        return list(reversed(self.data))[:limit]

    def last_success(self) -> BackupRun | None:
        return next((run for run in reversed(self.data) if run.status is RunStatus.SUCCEEDED), None)


class InMemoryImportTemplateRepository:
    def __init__(self, data: dict[UUID, ImportTemplate]) -> None:
        self.data = data

    def list(self, target: ImportTarget) -> list[ImportTemplate]:
        found = [template for template in self.data.values() if template.target is target]
        return sorted(found, key=lambda template: template.name.lower())

    def get(self, template_id: UUID) -> ImportTemplate | None:
        return self.data.get(template_id)

    def name_exists(self, target: ImportTarget, name: str) -> bool:
        return any(
            t.target is target and t.name.lower() == name.lower() for t in self.data.values()
        )

    def add(self, template: ImportTemplate) -> None:
        self.data[template.id] = template

    def delete(self, template_id: UUID) -> None:
        del self.data[template_id]


class InMemoryOnboardingRepository:
    def __init__(
        self, numbering_checked_at: datetime | None, dismissed_at: datetime | None
    ) -> None:
        self.numbering_checked_at = numbering_checked_at
        self.dismissed_at = dismissed_at

    def marks(self) -> OnboardingMarks:
        return OnboardingMarks(
            numbering_checked=self.numbering_checked_at is not None,
            dismissed=self.dismissed_at is not None,
        )

    def check_numbering(self, at: datetime) -> None:
        self.numbering_checked_at = self.numbering_checked_at or at

    def dismiss(self, at: datetime) -> None:
        self.dismissed_at = self.dismissed_at or at

    def show(self) -> None:
        self.dismissed_at = None


class InMemoryDunningRepository:
    def __init__(self, levels: list[DunningLevel], data: dict[UUID, Reminder]) -> None:
        self.saved_levels = levels
        self.data = data

    def levels(self) -> list[DunningLevel]:
        return list(self.saved_levels) or list(DEFAULT_LEVELS)

    def save_levels(self, levels: Sequence[DunningLevel]) -> None:
        self.saved_levels = list(levels)

    def reminders(self, invoice_ids: Collection[UUID]) -> dict[UUID, list[Reminder]]:
        found: dict[UUID, list[Reminder]] = {}
        for reminder in sorted(self.data.values(), key=lambda reminder: reminder.level):
            if reminder.invoice_id in invoice_ids:
                found.setdefault(reminder.invoice_id, []).append(reminder)
        return found

    def get(self, reminder_id: UUID) -> Reminder | None:
        return self.data.get(reminder_id)

    def add(self, reminder: Reminder) -> None:
        self.data[reminder.id] = reminder


class InMemoryMailRepository:
    def __init__(
        self,
        server: MailServer | None,
        templates: dict[tuple[MailKind, Language], MailTemplate],
    ) -> None:
        self.saved_server = server
        self.data = templates

    def server(self) -> MailServer | None:
        return self.saved_server

    def save_server(self, server: MailServer) -> None:
        self.saved_server = server

    def templates(self) -> dict[tuple[MailKind, Language], MailTemplate]:
        return dict(self.data)

    def save_template(self, template: MailTemplate) -> None:
        self.data[template.kind, template.language] = template

    def delete_template(self, kind: MailKind, language: Language) -> None:
        self.data.pop((kind, language), None)


class InMemoryRecurringRepository:
    def __init__(self, plans: dict[UUID, RecurringPlan], runs: list[PlanRun]) -> None:
        self.data = plans
        self.saved_runs = runs
        self.locked: list[UUID] = []

    def all(self) -> list[RecurringPlan]:
        return sorted(self.data.values(), key=lambda plan: (plan.name, str(plan.id)))

    def get(self, plan_id: UUID, *, for_update: bool = False) -> RecurringPlan | None:
        if for_update:
            self.locked.append(plan_id)
        return self.data.get(plan_id)

    def add(self, plan: RecurringPlan) -> None:
        self.data[plan.id] = plan

    def update(self, plan: RecurringPlan) -> None:
        self.data[plan.id] = plan

    def delete(self, plan_id: UUID) -> None:
        del self.data[plan_id]
        self.saved_runs = [run for run in self.saved_runs if run.plan_id != plan_id]

    def due(self, today: date) -> list[UUID]:
        due = [plan for plan in self.data.values() if plan.is_due(today)]
        return [plan.id for plan in sorted(due, key=lambda plan: (plan.next_date, str(plan.id)))]

    def claim(self, run: PlanRun) -> bool:
        taken = any(
            (known.plan_id, known.period_start) == (run.plan_id, run.period_start)
            for known in self.saved_runs
        )
        if not taken:
            self.saved_runs.append(run)
        return not taken

    def finish(self, run: PlanRun) -> None:
        self.saved_runs = [
            run if (known.plan_id, known.period_start) == (run.plan_id, run.period_start) else known
            for known in self.saved_runs
        ]

    def runs(self, plan_ids: Collection[UUID], *, limit: int) -> dict[UUID, list[PlanRun]]:
        found: dict[UUID, list[PlanRun]] = {}
        for run in sorted(self.saved_runs, key=lambda run: run.period_start, reverse=True):
            if run.plan_id in plan_ids and len(found.get(run.plan_id, [])) < limit:
                found.setdefault(run.plan_id, []).append(run)
        return found


class InMemoryUnitOfWork:
    """Copies the store on enter and writes it back on commit only."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.commits = 0

    def __enter__(self) -> Self:
        self.users = InMemoryUserRepository(dict(self.store.users))
        self.sessions = InMemorySessionRepository(dict(self.store.sessions))
        self.company = InMemoryCompanyRepository(
            self.store.company, self.store.logo, self.store.print_layout
        )
        self.bank_accounts = InMemoryBankAccountRepository(dict(self.store.bank_accounts))
        self.customers = InMemoryCustomerRepository(dict(self.store.customers))
        self.articles = InMemoryArticleRepository(dict(self.store.articles))
        self.sequences = InMemoryNumberSequenceRepository(dict(self.store.sequences))
        self.documents = InMemoryDocumentRepository(
            dict(self.store.documents),
            dict(self.store.pdfs),
            dict(self.store.e_invoices),
            dict(self.store.attachments),
        )
        self.text_templates = InMemoryTextTemplateRepository(dict(self.store.text_templates))
        self.legal_notices = InMemoryLegalNoticeRepository(dict(self.store.legal_notices))
        self.backups = InMemoryBackupRepository(
            list(self.store.backup_requests), list(self.store.backup_runs)
        )
        self.import_templates = InMemoryImportTemplateRepository(dict(self.store.import_templates))
        self.onboarding = InMemoryOnboardingRepository(
            self.store.numbering_checked_at, self.store.onboarding_dismissed_at
        )
        self.dunning = InMemoryDunningRepository(
            list(self.store.dunning_levels), dict(self.store.reminders)
        )
        self.mail = InMemoryMailRepository(self.store.mail_server, dict(self.store.mail_templates))
        self.recurring = InMemoryRecurringRepository(dict(self.store.plans), list(self.store.runs))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        self.store.users = dict(self.users.data)
        self.store.sessions = dict(self.sessions.data)
        self.store.company = self.company.company
        self.store.logo = self.company.logo
        self.store.print_layout = self.company.layout
        self.store.bank_accounts = dict(self.bank_accounts.data)
        self.store.customers = dict(self.customers.data)
        self.store.articles = dict(self.articles.data)
        self.store.sequences = dict(self.sequences.data)
        self.store.documents = dict(self.documents.data)
        self.store.pdfs = dict(self.documents.pdfs)
        self.store.e_invoices = dict(self.documents.e_invoices)
        self.store.attachments = dict(self.documents.saved_attachments)
        self.store.text_templates = dict(self.text_templates.data)
        self.store.legal_notices = dict(self.legal_notices.data)
        self.store.backup_requests = list(self.backups.requests)
        self.store.backup_runs = list(self.backups.data)
        self.store.import_templates = dict(self.import_templates.data)
        self.store.numbering_checked_at = self.onboarding.numbering_checked_at
        self.store.onboarding_dismissed_at = self.onboarding.dismissed_at
        self.store.dunning_levels = list(self.dunning.saved_levels)
        self.store.reminders = dict(self.dunning.data)
        self.store.mail_server = self.mail.saved_server
        self.store.mail_templates = dict(self.mail.data)
        self.store.plans = dict(self.recurring.data)
        self.store.runs = list(self.recurring.saved_runs)
        self.commits += 1


class FakePasswordHasher:
    """Hashes are readable; hashes starting with 'old:' need a rehash."""

    def __init__(self) -> None:
        self.hashed: list[str] = []

    def hash(self, password: str) -> str:
        self.hashed.append(password)
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash in {f"hashed:{password}", f"old:{password}"}

    def needs_rehash(self, password_hash: str) -> bool:
        return password_hash.startswith("old:")


VALID_TOTP_CODE = "123456"
NEXT_TOTP_CODE = "654321"
TOTP_STEP = 100


class FakeTotpService:
    """Code "123456" belongs to step 100, "654321" to step 101."""

    def new_secret(self) -> str:
        return "SECRET"

    def matching_step(self, secret: str, code: str, at: datetime) -> int | None:
        assert secret
        assert at.tzinfo is not None
        return {VALID_TOTP_CODE: TOTP_STEP, NEXT_TOTP_CODE: TOTP_STEP + 1}.get(code)

    def provisioning_uri(self, secret: str, account: str) -> str:
        return f"otpauth://totp/Rhinvoice:{account}?secret={secret}"
