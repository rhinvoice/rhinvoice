from rhinvoice.domain.shared.errors import DomainError


class NotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    code = "conflict"


class AuthenticationError(DomainError):
    code = "authentication_failed"


class AccountLockedError(AuthenticationError):
    code = "account_locked"


class TotpRequiredError(AuthenticationError):
    code = "totp_required"


class UnavailableError(DomainError):
    """A service the use case needs is not configured or not reachable."""

    code = "unavailable"


class DemoLockedError(DomainError):
    """The public demo does not allow this (it would lock other visitors out or send mail)."""

    code = "demo_locked"


class DeliveryError(DomainError):
    """The mail server refused a mail or could not be reached; ``code`` says which."""

    code = "mail_failed"
