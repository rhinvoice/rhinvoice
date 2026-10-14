"""Composition root: wires the adapters into the use case handlers."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rhinvoice.application.backup.handlers import BackupHandlers
from rhinvoice.application.catalog.handlers import ArticleHandlers
from rhinvoice.application.company.handlers import CompanyHandlers
from rhinvoice.application.customer.handlers import CustomerHandlers
from rhinvoice.application.demo.handlers import DemoHandlers
from rhinvoice.application.document.dashboard import DashboardHandlers
from rhinvoice.application.document.handlers import DocumentHandlers
from rhinvoice.application.document.printing import PrintHandlers
from rhinvoice.application.dunning.handlers import DunningHandlers
from rhinvoice.application.identity.handlers import IdentityHandlers
from rhinvoice.application.importing.handlers import ImportHandlers
from rhinvoice.application.mail.handlers import MailHandlers
from rhinvoice.application.numbering.handlers import NumberingHandlers
from rhinvoice.application.onboarding.handlers import OnboardingHandlers
from rhinvoice.application.recurring.handlers import RecurringHandlers
from rhinvoice.application.text.handlers import TextHandlers
from rhinvoice.domain.shared.clock import Clock, SystemClock
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork, make_engine
from rhinvoice.infrastructure.einvoice.cii import CiiWriter
from rhinvoice.infrastructure.importing.reader import SpreadsheetReader
from rhinvoice.infrastructure.mail.content import PrintedMailContent
from rhinvoice.infrastructure.mail.smtp import SmtpSender
from rhinvoice.infrastructure.rendering.chromium import LocalChromiumPrinter
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from rhinvoice.infrastructure.rendering.pdf import ChromiumPdfRenderer, GotenbergPrinter
from rhinvoice.infrastructure.security import Argon2PasswordHasher, PyOtpTotpService

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from rhinvoice.api.settings import Settings
    from rhinvoice.application.document.printing import PdfRenderer


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    engine: Engine
    clock: Clock
    identity: IdentityHandlers
    company: CompanyHandlers
    customers: CustomerHandlers
    articles: ArticleHandlers
    numbering: NumberingHandlers
    documents: DocumentHandlers
    dashboard: DashboardHandlers
    texts: TextHandlers
    printing: PrintHandlers
    backup: BackupHandlers
    imports: ImportHandlers
    onboarding: OnboardingHandlers
    dunning: DunningHandlers
    demo: DemoHandlers
    mail: MailHandlers
    recurring: RecurringHandlers
    demo_reset: threading.Event = field(default_factory=threading.Event)
    """Set while a public demo is being reset: the API answers 503 meanwhile."""


def pdf_renderer(settings: Settings, html: JinjaDocumentRenderer) -> PdfRenderer | None:
    """Gotenberg in the Docker setup, else a browser on this computer, else no PDFs."""
    if settings.gotenberg_url is not None:
        return ChromiumPdfRenderer(html, GotenbergPrinter(settings.gotenberg_url))
    if settings.chromium_path is not None:
        return ChromiumPdfRenderer(html, LocalChromiumPrinter(settings.chromium_path))
    return None


def build_container(settings: Settings, clock: Clock | None = None) -> Container:
    engine = make_engine(settings.database_url)
    effective_clock = clock or SystemClock(settings.zone)

    def uow() -> SqlUnitOfWork:
        return SqlUnitOfWork(engine)

    documents = DocumentHandlers(uow=uow, clock=effective_clock)
    imports = ImportHandlers(uow=uow, clock=effective_clock, reader=SpreadsheetReader())
    company = CompanyHandlers(uow=uow)
    customers = CustomerHandlers(uow=uow, clock=effective_clock)
    articles = ArticleHandlers(uow=uow, clock=effective_clock)
    html = JinjaDocumentRenderer(settings.theme_dir)
    pdf = pdf_renderer(settings, html)
    printing = PrintHandlers(
        uow=uow,
        clock=effective_clock,
        documents=documents,
        renderer=html,
        pdf_renderer=pdf,
        e_invoices=CiiWriter(),
    )
    identity = IdentityHandlers(
        uow=uow,
        hasher=Argon2PasswordHasher(),
        totp=PyOtpTotpService(),
        clock=effective_clock,
        # A public demo shares one login: failed attempts must not lock it for everyone.
        lockout=not settings.demo,
    )
    mail = MailHandlers(
        uow=uow,
        clock=effective_clock,
        documents=documents,
        content=PrintedMailContent(printing),
        sender=SmtpSender(),
    )
    return Container(
        settings=settings,
        engine=engine,
        clock=effective_clock,
        identity=identity,
        company=company,
        customers=customers,
        articles=articles,
        numbering=NumberingHandlers(uow=uow, clock=effective_clock),
        documents=documents,
        dashboard=DashboardHandlers(uow=uow, clock=effective_clock),
        texts=TextHandlers(uow=uow),
        printing=printing,
        backup=BackupHandlers(uow=uow, clock=effective_clock),
        imports=imports,
        onboarding=OnboardingHandlers(uow=uow, clock=effective_clock),
        dunning=DunningHandlers(uow=uow, clock=effective_clock, documents=documents),
        demo=DemoHandlers(
            uow=uow,
            clock=effective_clock,
            identity=identity,
            company=company,
            customers=customers,
            articles=articles,
            documents=documents,
            imports=imports,
        ),
        mail=mail,
        recurring=RecurringHandlers(
            uow=uow, clock=effective_clock, documents=documents, printing=printing, mail=mail
        ),
    )
