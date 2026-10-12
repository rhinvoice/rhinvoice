"""PDF files of imported invoices, found by the invoice number in their names.

Programs and people name invoice files after the number: "Rechnung R20150001.pdf",
"R2015-0001.pdf", "2015/20150001_korrektur.pdf". Of all files with a number,
the one with nothing else in its name is the invoice; the others (reminders,
corrected copies, versions) are kept with it as attachments. A file named as a
reminder or a copy never becomes the invoice: then the invoice gets no PDF and
all its files are attachments. Copies with the same content count once, and a
file belongs to one invoice only.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_WORDS = frozenset({"rechnung", "invoice", "faktura", "facture", "fattura", "re", "nr", "no"})
"""Words a plain invoice file may have around its number."""
_NOT_ORIGINAL = frozenset(
    {
        "mahnung",
        "erinnerung",
        "zahlungserinnerung",
        "reminder",
        "korrektur",
        "korrigiert",
        "kopie",
        "copy",
        "storno",
        "gutschrift",
        "entwurf",
        "draft",
        "alt",
        "old",
    }
)
"""Words of files that are about an invoice but not the invoice itself."""
_DIGITS = re.compile(r"\d+")
_MIN_DIGITS = 3
"""A shorter number ("12") is found in too many names to tell anything."""
_TOKEN = re.compile(r"[^\W_]+")
_SEPARATOR = re.compile(r"[\W_]+")
_LEADING_LETTERS = re.compile(r"^\D+")
_KIND_NOT_ORIGINAL = 2
_WORD_BEFORE = re.compile(r"([^\W\d_]+)[\W_]*$")


@dataclass(frozen=True, slots=True)
class ImportFile:
    path: str
    """Name with the folders it came from, "/" between them ("2016 CH/Rechnung R20160001.pdf")."""
    content: bytes
    sha256: str = field(init=False, repr=False, compare=False)
    """Hash of the content, computed once (files may have 20 MB)."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class FileMatch:
    invoice: ImportFile | None
    """The file that is the invoice; None when all files of the number are reminders or copies."""
    attachments: tuple[ImportFile, ...]
    """Further files with the number, in name order."""

    @property
    def files(self) -> tuple[ImportFile, ...]:
        return self.attachments if self.invoice is None else (self.invoice, *self.attachments)


def _flexible(number: str) -> str:
    """Regex of the number whose separators may be another one or none ("2015-1" ~ "2015_1")."""
    return r"[\W_]?".join(re.escape(part) for part in _SEPARATOR.split(number) if part)


def _pattern(number: str) -> re.Pattern[str] | None:
    """Match the number in a file name, also without its letters ("R2015-1" in "2015-1")."""
    digits = "".join(_DIGITS.findall(number))
    if len(digits) < _MIN_DIGITS:
        return None
    exact = _flexible(number)
    # "R20150001" is also found as "20150001": the letters are often left out of file names.
    core = _flexible(_LEADING_LETTERS.sub("", number))
    return re.compile(rf"(?<![^\W_])(?:(?P<exact>{exact})|(?P<core>{core}))(?!\d)", re.IGNORECASE)


def _found(name: str, pattern: re.Pattern[str]) -> re.Match[str] | None:
    """Find the number in the name; without its letters only where no other letters stand instead.

    "Rechnung 100.pdf" is invoice "RE-100", "GS-100.pdf" is the credit note of another series.
    """
    for match in pattern.finditer(name):
        if match.lastgroup == "exact":
            return match
        before = _WORD_BEFORE.search(name[: match.start()])
        if before is None or before.group(1).lower() in _WORDS:
            return match
    return None


def _rest(name: str, match: re.Match[str]) -> list[str]:
    """Words of the file name besides the number, the extension and the plain words."""
    stem = name[: match.start()] + " " + name[match.end() :]
    stem = stem.rsplit(".", 1)[0]
    return [word for word in _TOKEN.findall(stem.lower()) if word not in _WORDS]


def _kind(file: ImportFile, match: re.Match[str]) -> int:
    """0: a plain invoice file, 1: one with other words, 2: a reminder or copy."""
    rest = _rest(file.name, match)
    if any(word in _NOT_ORIGINAL for word in rest):
        return _KIND_NOT_ORIGINAL
    return 1 if rest else 0


def unique(files: Iterable[ImportFile]) -> list[ImportFile]:
    """Drop copies with the same content, keeping the least nested one."""
    kept: dict[str, ImportFile] = {}
    for file in sorted(files, key=lambda file: (file.path.count("/"), len(file.path), file.path)):
        kept.setdefault(file.sha256, file)
    return sorted(kept.values(), key=lambda file: file.path)


class FileIndex:
    """Finds the files of an invoice number among many without trying each name."""

    def __init__(self, files: Sequence[ImportFile]) -> None:
        self.files = unique(files)
        self._by_digits: dict[str, list[ImportFile]] = {}
        for file in self.files:
            for run in set(_DIGITS.findall(file.name)):
                self._by_digits.setdefault(run, []).append(file)
        self.used: set[str] = set()
        """Paths of the files given to an invoice so far."""

    def find(self, number: str) -> FileMatch | None:
        pattern = _pattern(number)
        if pattern is None:
            return None
        runs = _DIGITS.findall(number)
        # File names may join what the number separates ("R2015-0001" in "R20150001.pdf").
        candidates = {
            file.path: file
            for key in {max(runs, key=len), "".join(runs)}
            for file in self._by_digits.get(key, ())
            # A file belongs to one invoice only.
            if file.path not in self.used
        }
        ranked: list[tuple[int, int, int, str, ImportFile]] = []
        for file in candidates.values():
            match = _found(file.name, pattern)
            if match is not None:
                kind = _kind(file, match)
                ranked.append((kind, file.path.count("/"), len(file.name), file.path, file))
        if not ranked:
            return None
        ranked.sort(key=lambda entry: entry[:4])
        best = ranked[0]
        invoice = None if best[0] == _KIND_NOT_ORIGINAL else best[4]
        others = sorted((entry[4] for entry in ranked if entry[4] is not invoice), key=_path)
        return FileMatch(invoice=invoice, attachments=tuple(others))

    def claim(self, match: FileMatch) -> None:
        self.used.update(file.path for file in match.files)

    @property
    def unused(self) -> list[str]:
        return [file.path for file in self.files if file.path not in self.used]


def _path(file: ImportFile) -> str:
    return file.path


def matching_count(numbers: Iterable[str], index: FileIndex) -> int:
    """How many of the numbers have a file: tells the column of the invoice numbers."""
    return sum(1 for number in numbers if index.find(number) is not None)
