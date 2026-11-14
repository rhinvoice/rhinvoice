"""Units of measure owned by the company (ADR 0046).

A unit has the label documents print, optionally another one for English, French or Italian
documents, and the code of the EN 16931 unit code list (UN/ECE Recommendation 20 with the
Recommendation 21 codes, BT-130) that the e-invoice sends. Several units may share a code
("Std." and "Stunde" are both HUR). Issuing freezes code and label on each line.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

MAX_UNIT_LABEL = 20
MAX_UNIT_DESCRIPTION = 100
TRANSLATED = (Language.EN, Language.FR, Language.IT)
"""The languages a unit may have a label of its own for; others print the main label."""


# The file names the source and the version of the list.
_CODE_LIST = files("rhinvoice.domain.catalog").joinpath("unit_codes.json")
UNIT_CODES: Mapping[str, str] = MappingProxyType(
    json.loads(_CODE_LIST.read_text(encoding="utf-8"))["codes"]
)
"""Every code of the EN 16931 unit code list with its official English name."""


def check_unit_code(code: str) -> None:
    """Refuse a code the e-invoice validators would reject (BR-CL-23)."""
    if code not in UNIT_CODES:
        raise ValidationError(
            "code", f"'{code}' is not in the EN 16931 unit code list", code="unit_code_unknown"
        )


@dataclass(frozen=True, slots=True)
class LineUnit:
    """A unit as a line shows it: its code and its label in the document's language."""

    code: str
    label: str


@dataclass(frozen=True, slots=True)
class Unit:
    id: UUID
    code: str
    """The code of the EN 16931 unit code list, sent in the e-invoice."""
    label: str
    """Printed on documents, also in languages without a label of their own."""
    label_en: str = ""
    label_fr: str = ""
    label_it: str = ""
    description: str = ""
    """For the user only, e.g. "Doppelzentner (100 kg)"; never printed."""
    preset: str | None = None
    """The catalogue entry the unit was taken from (its key)."""
    hidden: bool = False
    """Not offered for new lines; lines, articles and plans that use it keep it."""

    def __post_init__(self) -> None:
        check_unit_code(self.code)
        object.__setattr__(
            self, "label", clean_text(self.label, "label", max_length=MAX_UNIT_LABEL, required=True)
        )
        for language in TRANSLATED:
            name = f"label_{language}"
            object.__setattr__(
                self, name, clean_text(getattr(self, name), name, max_length=MAX_UNIT_LABEL)
            )
        object.__setattr__(
            self,
            "description",
            clean_text(self.description, "description", max_length=MAX_UNIT_DESCRIPTION),
        )

    @property
    def translations(self) -> dict[Language, str]:
        """The labels of its own the unit has for English, French or Italian documents."""
        own = {
            Language.EN: self.label_en,
            Language.FR: self.label_fr,
            Language.IT: self.label_it,
        }
        return {language: label for language, label in own.items() if label}

    def label_in(self, language: Language) -> str:
        """Return the label documents in ``language`` print."""
        return self.translations.get(language, self.label)

    def frozen(self, language: Language) -> LineUnit:
        """Return what a line of a document in ``language`` keeps of the unit when issued."""
        return LineUnit(code=self.code, label=self.label_in(language))


def known_unit(unit_id: UUID, units: Mapping[UUID, Unit]) -> Unit:
    """Return one of the company's units; a line cannot refer to an unknown one."""
    unit = units.get(unit_id)
    if unit is None:
        raise ValidationError("unit_id", "unknown unit", code="unit_unknown")
    return unit
