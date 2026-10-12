from datetime import UTC, datetime

import pytest

from rhinvoice.domain.shared.clock import FixedClock
from tests.unit.application.fakes import Store

NOW = datetime(2026, 3, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)
