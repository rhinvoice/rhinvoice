"""Clock abstraction so that time can be frozen in tests."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, tzinfo
from typing import Protocol
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = ZoneInfo("Europe/Zurich")


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        ...

    def today(self) -> date:
        """Return the current date in the installation's timezone."""
        ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    timezone: tzinfo = DEFAULT_TIMEZONE

    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return self.now().astimezone(self.timezone).date()


@dataclass(slots=True)
class FixedClock:
    """A clock that only moves when told to."""

    current: datetime
    timezone: tzinfo = field(default=DEFAULT_TIMEZONE)

    def __post_init__(self) -> None:
        self._require_aware(self.current)

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None:
            msg = "FixedClock requires an aware datetime"
            raise ValueError(msg)

    def now(self) -> datetime:
        return self.current.astimezone(UTC)

    def today(self) -> date:
        return self.current.astimezone(self.timezone).date()

    def set(self, current: datetime) -> None:
        self._require_aware(current)
        self.current = current
