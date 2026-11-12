# ruff: noqa: RUF001 - French and Italian elide with the typographic apostrophe.
"""Country presets for tax rates (ADR 0044).

Every country brings its standard, reduced and (where it has one) special rate from the dated
rate sets of its profile, a zero rate and an exempt rate. Special schemes such as the German
average rates of § 24 UStG are extra presets a company takes over on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.tax_rate import RateCategory, RateValue, TaxRate

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from uuid import UUID

    from rhinvoice.domain.tax.rates import TaxRateSet

STANDARD = "standard"
REDUCED = "reduced"
SPECIAL = "special"
ZERO = "zero"
EXEMPT = "exempt"
BASE_KEYS = (STANDARD, REDUCED, SPECIAL, ZERO, EXEMPT)
"""The presets every company starts with, in this order (special only where it exists).

The names are those of the former fixed categories, so nothing reads differently after the
migration."""

_NAMES: Mapping[str, Mapping[Language, str]] = {
    STANDARD: {
        Language.DE: "Normalsatz",
        Language.EN: "Standard rate",
        Language.FR: "Taux normal",
        Language.IT: "Aliquota normale",
    },
    REDUCED: {
        Language.DE: "Reduzierter Satz",
        Language.EN: "Reduced rate",
        Language.FR: "Taux réduit",
        Language.IT: "Aliquota ridotta",
    },
    ZERO: {
        Language.DE: "0 % (steuerbar)",
        Language.EN: "0 % (taxable)",
        Language.FR: "0 % (imposable)",
        Language.IT: "0 % (imponibile)",
    },
    EXEMPT: {
        Language.DE: "Von der Steuer ausgenommen",
        Language.EN: "Exempt",
        Language.FR: "Exclu du champ de l’impôt",
        Language.IT: "Escluso dall’imposta",
    },
}
_EXEMPTION_REASON: Mapping[Language, str] = {
    Language.DE: "Steuerbefreite Leistung",
    Language.EN: "Exempt supply",
    Language.FR: "Prestation exonérée",
    Language.IT: "Prestazione esente",
}
"""The reason of the exempt preset; users name the exact legal basis."""


@dataclass(frozen=True, slots=True)
class RatePreset:
    key: str
    names: Mapping[Language, str]
    category: RateCategory
    values: tuple[RateValue, ...]
    exemption_reasons: Mapping[Language, str] | None = None
    notices: Mapping[Language, str] | None = None
    sources: tuple[str, ...] = ()
    """Official sources of the percentages."""

    def to_rate(self, rate_id: UUID, language: Language) -> TaxRate:
        """Return the preset as a company's rate, worded in ``language``."""
        return TaxRate(
            id=rate_id,
            name=self.names[language],
            category=self.category,
            values=self.values,
            exemption_reason=(self.exemption_reasons or {}).get(language, ""),
            notice=(self.notices or {}).get(language, ""),
            preset=self.key,
        )


def _values(
    rate_sets: Sequence[TaxRateSet], pick: Callable[[TaxRateSet], Decimal | None]
) -> tuple[RateValue, ...]:
    """Return one value per change of the percentage, from the profile's dated rate sets."""
    values: list[RateValue] = []
    for rate_set in rate_sets:
        percent = pick(rate_set)
        if percent is not None and (not values or values[-1].percent != percent):
            values.append(RateValue(rate_set.valid_from, percent))
    return tuple(values)


def base_presets(
    rate_sets: Sequence[TaxRateSet], special_names: Mapping[Language, str] | None
) -> tuple[RatePreset, ...]:
    """Return the presets every company of a country starts with, from its dated rate sets."""
    first = rate_sets[0].valid_from
    zero = (RateValue(first, Decimal(0)),)
    presets = [
        RatePreset(
            STANDARD,
            _NAMES[STANDARD],
            RateCategory.STANDARD,
            _values(rate_sets, lambda rates: rates.standard),
        ),
        RatePreset(
            REDUCED,
            _NAMES[REDUCED],
            RateCategory.STANDARD,
            _values(rate_sets, lambda rates: rates.reduced),
        ),
    ]
    if special_names is not None:
        presets.append(
            RatePreset(
                SPECIAL,
                special_names,
                RateCategory.STANDARD,
                _values(rate_sets, lambda rates: rates.special),
            )
        )
    presets += [
        RatePreset(ZERO, _NAMES[ZERO], RateCategory.ZERO, zero),
        RatePreset(
            EXEMPT,
            _NAMES[EXEMPT],
            RateCategory.EXEMPT,
            zero,
            exemption_reasons=_EXEMPTION_REASON,
        ),
    ]
    return tuple(presets)
