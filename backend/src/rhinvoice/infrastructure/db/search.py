"""Text matching helpers shared by the repositories.

``rhinvoice_fold`` (lower case, accents removed) and ``rhinvoice_fold_de``
(additionally ä→ae, ö→oe, ü→ue, ß→ss) are SQL functions created by migration
0004, so that "Muller" and "Mueller" both find "Müller".
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy import func, literal, or_

if TYPE_CHECKING:
    from sqlalchemy import Column, ColumnElement

NATURAL_COLLATION = "natural_sort"
"""ICU collation "und-u-kn-true": language-aware and numeric ("9" < "10")."""

_WORD = re.compile(r"\w+", re.UNICODE)


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def text_match(search: str, columns: list[Column[str]]) -> ColumnElement[bool]:
    """Case, accent and umlaut-spelling insensitive substring match."""
    needle = func.rhinvoice_fold(literal(f"%{escape_like(search.strip())}%"))
    return or_(
        *(func.rhinvoice_fold(column).like(needle, escape="\\") for column in columns),
        *(func.rhinvoice_fold_de(column).like(needle, escape="\\") for column in columns),
    )


def prefix_query(search: str) -> str | None:
    """Turn user input into a tsquery: every word must match as a prefix."""
    words = _WORD.findall(search)
    return " & ".join(f"{word}:*" for word in words) if words else None
