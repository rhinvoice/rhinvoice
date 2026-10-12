import re
from dataclasses import dataclass
from typing import Self

from rhinvoice.domain.shared.errors import ValidationError

# Deliberately permissive: RFC 5322 is too complex to validate with a regex and
# delivery is the only real proof. We reject obvious typos only.
# Control characters are excluded explicitly because "\s" differs between Python
# and ECMAScript regexes; the same pattern is published in the OpenAPI schema.
_ATOM = r"[^@\s\x00-\x1f\x7f-\x9f\ufeff]+"
EMAIL_PATTERN = rf"^{_ATOM}@{_ATOM}\.{_ATOM}$"
_EMAIL_REGEX = re.compile(EMAIL_PATTERN)
MAX_EMAIL_LENGTH = 254


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) > MAX_EMAIL_LENGTH or not _EMAIL_REGEX.fullmatch(self.value):
            raise ValidationError("email", f"'{self.value}' is not a valid e-mail address")

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw.strip().lower())

    def __str__(self) -> str:
        return self.value
