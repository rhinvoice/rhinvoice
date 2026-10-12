"""Who a mail goes to."""

from __future__ import annotations

from email.errors import HeaderParseError
from email.headerregistry import Address
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import ValidationError

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_RECIPIENTS = 5


_SPECIAL = frozenset(',;<>"()[]\\:')


def _plain(address: EmailAddress) -> bool:
    """Whether the address is one mailbox the server and the header read alike.

    "a,b@x.example" would be two header addresses but one envelope recipient, and
    "x<ceo@corp.ch>" would go to someone else than the history says.
    """
    if any(character in _SPECIAL for character in address.value):
        return False
    try:
        return Address(addr_spec=address.value).addr_spec == address.value
    except (HeaderParseError, IndexError, ValueError):
        return False


def recipients(raw: Iterable[str]) -> tuple[EmailAddress, ...]:
    """Parse the addresses of a mail: at least one, at most five, each once."""
    found: list[EmailAddress] = []
    for value in raw:
        if not value.strip():
            continue
        try:
            address = EmailAddress.parse(value)
        except ValidationError as error:
            raise ValidationError("to", error.message, code="invalid_recipient") from None
        if not _plain(address):
            raise ValidationError(
                "to", f"'{value.strip()}' is not a plain e-mail address", code="invalid_recipient"
            )
        if address not in found:
            found.append(address)
    if not found:
        raise ValidationError("to", "the mail needs a recipient", code="recipient_missing")
    if len(found) > MAX_RECIPIENTS:
        raise ValidationError("to", f"a mail goes to at most {MAX_RECIPIENTS} recipients")
    return tuple(found)
