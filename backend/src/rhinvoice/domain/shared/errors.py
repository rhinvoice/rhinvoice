"""Domain error hierarchy.

Every error carries a stable machine readable ``code`` so that the API layer
can map it to a response and the frontend can translate it.
"""

from collections.abc import Mapping


class DomainError(Exception):
    code: str = "domain_error"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, str] | None = None,
        code: str | None = None,
    ) -> None:
        """``code`` names a specific rule (e.g. "no_positions") instead of the class code."""
        super().__init__(message)
        self.message = message
        self.details: Mapping[str, str] = dict(details or {})
        if code is not None:
            self.code = code


class ValidationError(DomainError):
    """A value or a combination of values violates a business rule."""

    code = "validation_error"

    def __init__(self, field: str, message: str, *, code: str | None = None) -> None:
        super().__init__(message, details={field: message}, code=code)
        self.field = field


class InvalidStateError(DomainError):
    """An operation is not allowed in the current state of an aggregate."""

    code = "invalid_state"


class CurrencyMismatchError(DomainError):
    code = "currency_mismatch"
