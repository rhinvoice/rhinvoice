"""The in-memory fakes must implement every member of the application ports.

mypy and pyright check the signatures statically (see the annotated
assignments); the runtime check guards against forgotten members when a port
grows.
"""

import inspect

import pytest

from rhinvoice.application.catalog.ports import ArticleRepository
from rhinvoice.application.company.ports import BankAccountRepository, CompanyRepository
from rhinvoice.application.customer.ports import CustomerRepository
from rhinvoice.application.dunning.ports import DunningRepository
from rhinvoice.application.identity.ports import (
    PasswordHasher,
    SessionRepository,
    TotpService,
    UserRepository,
)
from rhinvoice.application.importing.ports import ImportTemplateRepository
from rhinvoice.application.mail.ports import MailRepository
from rhinvoice.application.numbering.ports import NumberSequenceRepository
from rhinvoice.application.onboarding.ports import OnboardingRepository
from rhinvoice.application.recurring.ports import RecurringRepository
from rhinvoice.application.text.ports import LegalNoticeRepository, TextTemplateRepository
from rhinvoice.application.uow import UnitOfWork
from tests.unit.application.fakes import (
    FakePasswordHasher,
    FakeTotpService,
    InMemoryArticleRepository,
    InMemoryBankAccountRepository,
    InMemoryCompanyRepository,
    InMemoryCustomerRepository,
    InMemoryDunningRepository,
    InMemoryImportTemplateRepository,
    InMemoryLegalNoticeRepository,
    InMemoryMailRepository,
    InMemoryNumberSequenceRepository,
    InMemoryOnboardingRepository,
    InMemoryRecurringRepository,
    InMemorySessionRepository,
    InMemoryTextTemplateRepository,
    InMemoryUnitOfWork,
    InMemoryUserRepository,
    Store,
)

PAIRS: list[tuple[type, object]] = [
    (UnitOfWork, InMemoryUnitOfWork(Store()).__enter__()),
    (UserRepository, InMemoryUserRepository({})),
    (SessionRepository, InMemorySessionRepository({})),
    (PasswordHasher, FakePasswordHasher()),
    (TotpService, FakeTotpService()),
    (CompanyRepository, InMemoryCompanyRepository(None, None)),
    (BankAccountRepository, InMemoryBankAccountRepository({})),
    (CustomerRepository, InMemoryCustomerRepository({})),
    (ArticleRepository, InMemoryArticleRepository({})),
    (NumberSequenceRepository, InMemoryNumberSequenceRepository({})),
    (TextTemplateRepository, InMemoryTextTemplateRepository({})),
    (LegalNoticeRepository, InMemoryLegalNoticeRepository({})),
    (ImportTemplateRepository, InMemoryImportTemplateRepository({})),
    (OnboardingRepository, InMemoryOnboardingRepository(None, None)),
    (DunningRepository, InMemoryDunningRepository([], {})),
    (MailRepository, InMemoryMailRepository(None, {})),
    (RecurringRepository, InMemoryRecurringRepository({}, [])),
]


def protocol_members(protocol: type) -> set[str]:
    return {
        name
        for name, _ in inspect.getmembers(protocol)
        if not name.startswith("_") or name in {"__enter__", "__exit__"}
    }


@pytest.mark.parametrize(("protocol", "fake"), PAIRS)
def test_fake_has_all_protocol_members(protocol: type, fake: object) -> None:
    members = protocol_members(protocol)
    assert members
    missing = {name for name in members if not hasattr(fake, name)}
    assert missing == set()


def test_fakes_are_statically_compatible() -> None:
    store = Store()
    uow: UnitOfWork = InMemoryUnitOfWork(store)
    users: UserRepository = InMemoryUserRepository(store.users)
    sessions: SessionRepository = InMemorySessionRepository(store.sessions)
    hasher: PasswordHasher = FakePasswordHasher()
    totp: TotpService = FakeTotpService()
    company: CompanyRepository = InMemoryCompanyRepository(None, None)
    accounts: BankAccountRepository = InMemoryBankAccountRepository({})
    import_templates: ImportTemplateRepository = InMemoryImportTemplateRepository({})
    onboarding: OnboardingRepository = InMemoryOnboardingRepository(None, None)
    dunning: DunningRepository = InMemoryDunningRepository([], {})
    mail: MailRepository = InMemoryMailRepository(None, {})
    recurring: RecurringRepository = InMemoryRecurringRepository({}, [])
    customers: CustomerRepository = InMemoryCustomerRepository({})
    articles: ArticleRepository = InMemoryArticleRepository({})
    sequences: NumberSequenceRepository = InMemoryNumberSequenceRepository({})
    templates: TextTemplateRepository = InMemoryTextTemplateRepository({})
    notices: LegalNoticeRepository = InMemoryLegalNoticeRepository({})
    ports = (
        mail,
        recurring,
        uow,
        users,
        sessions,
        hasher,
        totp,
        company,
        accounts,
        customers,
        articles,
        sequences,
        templates,
        notices,
        import_templates,
        onboarding,
        dunning,
    )
    assert all(port is not None for port in ports)
