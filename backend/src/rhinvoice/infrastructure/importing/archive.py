"""PDF files of an invoice import: uploaded one by one, as a folder or packed in ZIP files.

Only PDF files are taken; whatever else a folder holds (pictures, spreadsheets,
.DS_Store) is left out. A ZIP file is unpacked within limits, so that a small
upload cannot unpack to gigabytes.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.application.importing.files import ImportFile
from rhinvoice.domain.shared.errors import ValidationError

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
"""All files of one import together."""
MAX_ENTRIES = 10_000
MAX_UNPACKED_BYTES = 500 * 1024 * 1024
"""All ZIP files of one import together."""
MAX_ENTRY_BYTES = 20 * 1024 * 1024
"""One PDF; checked before unpacking it."""
_ZIP_SIGNATURE = b"PK\x03\x04"


def _wanted(path: str) -> bool:
    """PDF files only; macOS adds copies of each file's metadata to ZIPs ("__MACOSX/._x.pdf")."""
    parts = path.split("/")
    return path.lower().endswith(".pdf") and not any(
        part.startswith(".") or part == "__MACOSX" for part in parts
    )


def _clean(path: str) -> str:
    """Use "/" between folders and drop empty, "." and ".." parts."""
    parts = path.replace("\\", "/").split("/")
    return "/".join(part for part in parts if part not in {"", ".", ".."})


@dataclass(slots=True)
class _Budget:
    """What all ZIP files of one import may unpack to together."""

    entries: int
    unpacked: int


def _unzip(name: str, content: bytes, budget: _Budget) -> list[ImportFile]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise ValidationError(
            "files", f"{name} cannot be read as ZIP file", code="unreadable_file"
        ) from error
    with archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        budget.entries -= len(entries)
        if budget.entries < 0:
            raise ValidationError(
                "files", f"the ZIP files hold more than {MAX_ENTRIES} files", code="too_many_files"
            )
        wanted = [entry for entry in entries if _wanted(_clean(entry.filename))]
        for entry in wanted:
            if entry.file_size > MAX_ENTRY_BYTES:
                raise ValidationError(
                    "files", f"{_clean(entry.filename)} is larger than 20 MB", code="file_too_large"
                )
        budget.unpacked -= sum(entry.file_size for entry in wanted)
        if budget.unpacked < 0:
            raise ValidationError(
                "files", "the ZIP files unpack to more than 500 MB", code="file_too_large"
            )
        try:
            # The declared sizes are checked above; zipfile reads no more than they say.
            return [
                ImportFile(path=_clean(entry.filename), content=archive.read(entry))
                for entry in wanted
            ]
        # Damaged or crafted archives make zipfile raise all kinds of errors.
        except Exception as error:
            raise ValidationError(
                "files", f"{name} cannot be unpacked", code="unreadable_file"
            ) from error


def read_files(uploads: Iterable[tuple[str, bytes]]) -> tuple[ImportFile, ...]:
    """Collect the PDF files of the uploads (name with folders, content); unpack ZIP files."""
    budget = _Budget(entries=MAX_ENTRIES, unpacked=MAX_UNPACKED_BYTES)
    files: list[ImportFile] = []
    for name, content in uploads:
        path = _clean(name)
        if content.startswith(_ZIP_SIGNATURE) and path.lower().endswith(".zip"):
            files.extend(_unzip(path, content, budget))
        elif _wanted(path):
            files.append(ImportFile(path=path, content=content))
    return tuple(files)
