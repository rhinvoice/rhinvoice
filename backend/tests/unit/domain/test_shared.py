from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from rhinvoice.domain.shared.clock import FixedClock, SystemClock
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.errors import DomainError, InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from tests.helpers import raises_exactly


def test_fixed_clock_reports_utc_and_local_date() -> None:
    clock = FixedClock(datetime(2025, 12, 31, 23, 30, tzinfo=UTC))
    assert clock.now() == datetime(2025, 12, 31, 23, 30, tzinfo=UTC)
    # 23:30 UTC is already the next day in Zurich.
    assert clock.today() == date(2026, 1, 1)
    clock.set(datetime(2026, 2, 1, 10, 0, tzinfo=timezone(timedelta(hours=2))))
    assert clock.now() == datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
    assert clock.now().tzinfo is UTC


def test_clocks_use_their_configured_timezone() -> None:
    pacific = ZoneInfo("Pacific/Kiritimati")  # UTC+14, never the host timezone
    fixed = FixedClock(datetime(2026, 3, 1, 12, 0, tzinfo=UTC), timezone=pacific)
    assert fixed.today() == date(2026, 3, 2)
    # UTC+14 and UTC-11 are 25 hours apart, so their dates always differ.
    east = SystemClock(timezone=pacific)
    west = SystemClock(timezone=ZoneInfo("Pacific/Pago_Pago"))
    assert east.today() != west.today()
    assert east.today() == east.now().astimezone(pacific).date()


def test_fixed_clock_requires_aware_datetime() -> None:
    with raises_exactly(ValueError, "FixedClock requires an aware datetime"):
        FixedClock(datetime(2025, 1, 1))  # noqa: DTZ001
    clock = FixedClock(datetime(2025, 1, 1, tzinfo=UTC))
    with raises_exactly(ValueError, "FixedClock requires an aware datetime"):
        clock.set(datetime(2025, 1, 2))  # noqa: DTZ001


def test_system_clock_returns_aware_now() -> None:
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is UTC
    assert abs(clock.today() - now.date()) <= timedelta(days=1)


def test_country_code_validation() -> None:
    assert str(CountryCode("CH")) == "CH"
    assert CountryCode("DE").is_eu
    assert not CountryCode("LI").is_eu
    with pytest.raises(ValidationError) as error:
        CountryCode("XX")
    assert error.value.details == {"country": "'XX' is not an ISO 3166 country code"}


def test_supported_countries() -> None:
    assert [c.value for c in Country] == ["CH", "LI", "DE", "AT"]


def test_errors_carry_codes_and_details() -> None:
    error = DomainError("boom")
    assert error.code == "domain_error"
    assert error.details == {}
    assert error.message == "boom"
    assert InvalidStateError("x").code == "invalid_state"
    validation = ValidationError("name", "required")
    assert validation.code == "validation_error"
    assert validation.details == {"name": "required"}
    assert validation.message == "required"
    assert str(validation) == "required"


def test_new_id_and_language() -> None:
    assert isinstance(new_id(), UUID)
    assert new_id() != new_id()
    assert Language("de") is Language.DE
