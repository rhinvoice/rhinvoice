"""The checklist for a new installation: what is set up, what is still missing.

The steps follow from the data (a company, a bank account, customers, an
invoice, a backup); only checking the number sequences and hiding the list are
remembered separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.application.common import PageRequest
from rhinvoice.application.customer.ports import CustomerQuery
from rhinvoice.application.document.ports import DocumentQuery
from rhinvoice.domain.document.document import DisplayStatus, DocumentType

if TYPE_CHECKING:
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock

_ONE = PageRequest(limit=1)
_ISSUED = frozenset(DisplayStatus) - {DisplayStatus.DRAFT}
"""Invoices that were issued, whatever happened to them since."""


class OnboardingStep(StrEnum):
    COMPANY = "company"
    BANK_ACCOUNT = "bank_account"
    NUMBERING = "numbering"
    CUSTOMERS = "customers"
    FIRST_INVOICE = "first_invoice"
    BACKUP = "backup"


@dataclass(frozen=True, slots=True)
class OnboardingStatus:
    steps: tuple[tuple[OnboardingStep, bool], ...]
    """Each step in order, with whether it is done."""
    dismissed: bool

    @property
    def complete(self) -> bool:
        return all(done for _, done in self.steps)


@dataclass(frozen=True, slots=True)
class OnboardingHandlers:
    uow: UnitOfWorkFactory
    clock: Clock

    def status(self) -> OnboardingStatus:
        with self.uow() as uow:
            return self._status(uow)

    def check_numbering(self) -> OnboardingStatus:
        with self.uow() as uow:
            uow.onboarding.check_numbering(self.clock.now())
            uow.commit()
            return self._status(uow)

    def dismiss(self) -> OnboardingStatus:
        with self.uow() as uow:
            uow.onboarding.dismiss(self.clock.now())
            uow.commit()
            return self._status(uow)

    def show(self) -> OnboardingStatus:
        """Show the hidden checklist again (undo)."""
        with self.uow() as uow:
            uow.onboarding.show()
            uow.commit()
            return self._status(uow)

    def _status(self, uow: UnitOfWork) -> OnboardingStatus:
        marks = uow.onboarding.marks()
        customers = uow.customers.search(CustomerQuery(include_archived=True, page=_ONE))
        invoices = uow.documents.search(
            DocumentQuery(
                today=self.clock.today(),
                types=frozenset({DocumentType.INVOICE}),
                statuses=_ISSUED,
                page=_ONE,
            )
        )
        return OnboardingStatus(
            steps=(
                (OnboardingStep.COMPANY, uow.company.get() is not None),
                (OnboardingStep.BANK_ACCOUNT, bool(uow.bank_accounts.list())),
                (OnboardingStep.NUMBERING, marks.numbering_checked),
                (OnboardingStep.CUSTOMERS, customers.total > 0),
                (OnboardingStep.FIRST_INVOICE, invoices.total > 0),
                (OnboardingStep.BACKUP, uow.backups.last_success() is not None),
            ),
            dismissed=marks.dismissed,
        )
