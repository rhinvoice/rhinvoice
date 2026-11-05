"""Further files of a document.

Imported invoices keep the reminders or corrected copies of another program; drafts written
here take PDFs such as the third-party invoices of pass-through items (ADR 0040). A draft's
files can be removed again; from issuing on, like the document's PDF, they are only ever
added, never changed or removed (GoBD, OR 958f).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime
    from uuid import UUID

MAX_FILE_NAME = 255
MAX_ATTACHMENTS = 10
"""Attachments of one draft; an imported invoice keeps every file it came with."""
MAX_ATTACHED_BYTES = 20 * 1024 * 1024
"""The attachments of one draft together: they go out after its PDF in one mail, and mail
servers often refuse more than 20 to 25 MB."""
PDF_SUFFIX = ".pdf"
DEFAULT_STEM = "document"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_UNSAFE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')
"""Control characters and what Windows, macOS or a ZIP reader would take for a path."""
_INVISIBLE = frozenset({"Cc", "Cf", "Zl", "Zp"})
"""Unicode controls, format characters (bidi overrides, zero widths) and line separators:
a name such as "Rechnung\u202eexe.pdf" would show as something it is not."""


def _visible(name: str) -> str:
    return "".join("_" if unicodedata.category(char) in _INVISIBLE else char for char in name)


def upload_name(raw: str) -> str:
    """Name an uploaded PDF safely: without folders, control or reserved characters, as .pdf.

    "../../R 42: Notar.PDF" becomes "R 42_ Notar.pdf"; an empty name becomes "document.pdf".
    """
    name = unicodedata.normalize("NFC", raw.replace("\\", "/").rsplit("/", 1)[-1])
    if name.lower().endswith(PDF_SUFFIX):
        name = name[: -len(PDF_SUFFIX)]
    stem = _visible(_UNSAFE.sub("_", name)).strip(" .")
    stem = stem[: MAX_FILE_NAME - len(PDF_SUFFIX)].rstrip(" .") or DEFAULT_STEM
    return stem + PDF_SUFFIX


def unique_name(name: str, taken: Iterable[str]) -> str:
    """Keep the names of one document's files apart, in any case.

    A second "Notar.pdf" becomes "Notar (2).pdf", a third "Notar (3).pdf"; the name is
    shortened where the number would make it too long.
    """
    used = {existing.casefold() for existing in taken}
    stem = name.removesuffix(PDF_SUFFIX)
    candidate, count = name, 1
    while candidate.casefold() in used:
        count += 1
        suffix = f" ({count}){PDF_SUFFIX}"
        candidate = stem[: MAX_FILE_NAME - len(suffix)].rstrip(" .") + suffix
    return candidate


def check_room(attached: Sequence[Attachment], size: int) -> None:
    """Refuse one more attachment of ``size`` bytes on a draft that has ``attached`` already."""
    if len(attached) >= MAX_ATTACHMENTS:
        raise ValidationError(
            "file",
            f"a draft has at most {MAX_ATTACHMENTS} attachments",
            code="too_many_attachments",
        )
    if sum(attachment.size for attachment in attached) + size > MAX_ATTACHED_BYTES:
        raise ValidationError(
            "file",
            "the attachments of a draft are at most 20 MB together",
            code="attachments_too_large",
        )


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
