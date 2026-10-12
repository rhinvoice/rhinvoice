"""The unit of work bundles all repositories of one database transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from rhinvoice.application.backup.ports import BackupRepository
    from rhinvoice.application.catalog.ports import ArticleRepository
    from rhinvoice.application.company.ports import BankAccountRepository, CompanyRepository
    from rhinvoice.application.customer.ports import CustomerRepository
    from rhinvoice.application.document.ports import DocumentRepository
    from rhinvoice.application.dunning.ports import DunningRepository
    from rhinvoice.application.identity.ports import SessionRepository, UserRepository
    from rhinvoice.application.importing.ports import ImportTemplateRepository
    from rhinvoice.application.mail.ports import MailRepository
    from rhinvoice.application.numbering.ports import NumberSequenceRepository
    from rhinvoice.application.onboarding.ports import OnboardingRepository
    from rhinvoice.application.recurring.ports import RecurringRepository
    from rhinvoice.application.text.ports import LegalNoticeRepository, TextTemplateRepository


class UnitOfWork(Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def sessions(self) -> SessionRepository: ...

    @property
    def company(self) -> CompanyRepository: ...

    @property
    def bank_accounts(self) -> BankAccountRepository: ...

    @property
    def customers(self) -> CustomerRepository: ...

    @property
    def articles(self) -> ArticleRepository: ...

    @property
    def sequences(self) -> NumberSequenceRepository: ...

    @property
    def documents(self) -> DocumentRepository: ...

    @property
    def text_templates(self) -> TextTemplateRepository: ...

    @property
    def legal_notices(self) -> LegalNoticeRepository: ...

    @property
    def backups(self) -> BackupRepository: ...

    @property
    def import_templates(self) -> ImportTemplateRepository: ...

    @property
    def onboarding(self) -> OnboardingRepository: ...

    @property
    def dunning(self) -> DunningRepository: ...

    @property
    def mail(self) -> MailRepository: ...

    @property
    def recurring(self) -> RecurringRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back everything that was not committed."""
        ...

    def commit(self) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
