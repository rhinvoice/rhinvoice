from __future__ import annotations

from typing import TYPE_CHECKING, Self

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from rhinvoice.infrastructure.db.repositories.backups import SqlBackupRepository
from rhinvoice.infrastructure.db.repositories.documents import SqlDocumentRepository
from rhinvoice.infrastructure.db.repositories.dunning import SqlDunningRepository
from rhinvoice.infrastructure.db.repositories.identity import (
    SqlSessionRepository,
    SqlUserRepository,
)
from rhinvoice.infrastructure.db.repositories.importing import SqlImportTemplateRepository
from rhinvoice.infrastructure.db.repositories.mail import SqlMailRepository
from rhinvoice.infrastructure.db.repositories.masterdata import (
    SqlArticleRepository,
    SqlBankAccountRepository,
    SqlCompanyRepository,
    SqlCustomerRepository,
    SqlNumberSequenceRepository,
)
from rhinvoice.infrastructure.db.repositories.onboarding import SqlOnboardingRepository
from rhinvoice.infrastructure.db.repositories.recurring import SqlRecurringRepository
from rhinvoice.infrastructure.db.repositories.texts import (
    SqlLegalNoticeRepository,
    SqlTextTemplateRepository,
)

if TYPE_CHECKING:
    from types import TracebackType

    from sqlalchemy import Connection, Engine, RootTransaction


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def database_is_reachable(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


class SqlUnitOfWork:
    """One database transaction; everything not committed is rolled back."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection: Connection | None = None
        self._transaction: RootTransaction | None = None

    def __enter__(self) -> Self:
        self._connection = self._engine.connect()
        self._transaction = self._connection.begin()
        self.users = SqlUserRepository(self._connection)
        self.sessions = SqlSessionRepository(self._connection)
        self.company = SqlCompanyRepository(self._connection)
        self.bank_accounts = SqlBankAccountRepository(self._connection)
        self.customers = SqlCustomerRepository(self._connection)
        self.articles = SqlArticleRepository(self._connection)
        self.sequences = SqlNumberSequenceRepository(self._connection)
        self.documents = SqlDocumentRepository(self._connection)
        self.text_templates = SqlTextTemplateRepository(self._connection)
        self.legal_notices = SqlLegalNoticeRepository(self._connection)
        self.backups = SqlBackupRepository(self._connection)
        self.import_templates = SqlImportTemplateRepository(self._connection)
        self.onboarding = SqlOnboardingRepository(self._connection)
        self.dunning = SqlDunningRepository(self._connection)
        self.mail = SqlMailRepository(self._connection)
        self.recurring = SqlRecurringRepository(self._connection)
        return self

    def _active(self) -> tuple[Connection, RootTransaction]:
        if self._connection is None or self._transaction is None:
            msg = "unit of work used outside of a with block"
            raise RuntimeError(msg)
        return self._connection, self._transaction

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        connection, transaction = self._active()
        # commit() always opens a fresh transaction, so there is one to roll back.
        transaction.rollback()
        connection.close()
        self._connection = None
        self._transaction = None

    def commit(self) -> None:
        connection, transaction = self._active()
        transaction.commit()
        self._transaction = connection.begin()
