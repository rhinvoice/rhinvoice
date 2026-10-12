"""Further files of an issued invoice, such as reminders or corrected copies of another program.

Like the invoice's PDF they are only ever added, never changed or removed (GoBD, OR 958f).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

MAX_FILE_NAME = 255
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class Attachment:
    id: UUID
    document_id: UUID
    file_name: str
    """The name the file had, with the folders it came from ("2016/R20160032_teil.pdf")."""
    sha256: str
    size: int
    """Bytes."""
    added_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "file_name",
            clean_text(self.file_name, "file_name", max_length=MAX_FILE_NAME, required=True),
        )
        if not _SHA256.fullmatch(self.sha256):
            raise ValidationError("sha256", "a SHA-256 hash has 64 lowercase hex digits")
        if self.size <= 0:
            raise ValidationError("size", "an attachment is not empty")
