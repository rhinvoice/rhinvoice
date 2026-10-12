"""The onboarding marks in PostgreSQL: one row, the first time of each mark kept."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select

from rhinvoice.application.onboarding.handlers import OnboardingHandlers, OnboardingStep
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.infrastructure.db.tables import onboarding
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork

NOW = datetime(2026, 3, 9, 9, 0, tzinfo=UTC)


def handlers(engine: Engine, now: datetime = NOW) -> OnboardingHandlers:
    return OnboardingHandlers(uow=lambda: SqlUnitOfWork(engine), clock=FixedClock(now))


def test_marks_are_kept_in_one_row(engine: Engine) -> None:
    status = handlers(engine).status()
    assert not any(done for _, done in status.steps)
    assert not status.dismissed
    assert dict(handlers(engine).check_numbering().steps)[OnboardingStep.NUMBERING]
    later = handlers(engine, NOW + timedelta(days=1))
    later.check_numbering()
    assert later.dismiss().dismissed
    with engine.connect() as connection:
        rows = connection.execute(select(onboarding)).mappings().all()
        assert connection.execute(select(func.count()).select_from(onboarding)).scalar_one() == 1
    assert rows[0]["numbering_checked_at"] == NOW
    assert rows[0]["dismissed_at"] == NOW + timedelta(days=1)
    assert handlers(engine).status().dismissed
    assert not handlers(engine).show().dismissed
