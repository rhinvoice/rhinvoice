"""Use cases for the company's tax rates (ADR 0044).

A company starts with the presets of its country; users add, rename or hide rates and take
over further presets (special schemes). Lines, articles and recurring plans refer to a rate:
a rate in use cannot be deleted, only hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import parse_decimal
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.presets import STANDARD
from rhinvoice.domain.tax.tax_rate import RateCategory, RateValue, TaxRate

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from datetime import date
    from uuid import UUID

    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.company.company import Company

MAX_TAX_RATES = 40


@dataclass(frozen=True, slots=True)
class SaveTaxRate:
    name: str
    category: RateCategory
    values: tuple[tuple[date, str], ...]
    """The dated percentages: the day each applies from, and the percentage."""
    exemption_reason: str = ""
    notice: str = ""


@dataclass(frozen=True, slots=True)
class TaxRateView:
    rate: TaxRate
    in_use: bool
    """Document lines, articles or recurring plans refer to it: hide it instead of deleting."""


@dataclass(frozen=True, slots=True)
class PresetOffer:
    """A preset of the company's country that no rate comes from yet, in the company's words."""

    key: str
    name: str
    category: RateCategory
    values: tuple[RateValue, ...]
    notice: str
    exemption_reason: str
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaxRateHandlers:
    uow: UnitOfWorkFactory

    def rates(self) -> list[TaxRateView]:
        """Every rate, hidden ones too, in their order."""
        with self.uow() as uow:
            used = uow.tax_rates.used_ids()
            return [TaxRateView(rate, rate.id in used) for rate in uow.tax_rates.list()]

    def create(self, command: SaveTaxRate) -> TaxRateView:
        with self.uow() as uow:
            rates = uow.tax_rates.list(for_update=True)
            _check_room(rates)
            rate = TaxRate(
                id=new_id(),
                name=command.name,
                category=command.category,
                values=_values(command),
                exemption_reason=command.exemption_reason,
                notice=command.notice,
            )
            _check_name(rates, rate)
            uow.tax_rates.add(rate)
            uow.commit()
        return TaxRateView(rate, in_use=False)

    def update(self, rate_id: UUID, command: SaveTaxRate) -> TaxRateView:
        """Change name, texts and percentages; the category stays (lines depend on it)."""
        with self.uow() as uow:
            rates = uow.tax_rates.list(for_update=True)
            previous = _require(rates, rate_id)
            if command.category is not previous.category:
                raise ValidationError(
                    "category",
                    "the category of a rate cannot change; add a new rate instead",
                    code="rate_category_fixed",
                )
            rate = replace(
                previous,
                name=command.name,
                values=_values(command),
                exemption_reason=command.exemption_reason,
                notice=command.notice,
            )
            _check_name(rates, rate)
            uow.tax_rates.update(rate)
            view = TaxRateView(rate, in_use=rate_id in uow.tax_rates.used_ids())
            uow.commit()
        return view

    def hide(self, rate_id: UUID) -> TaxRateView:
        """Offer the rate no more for new lines; those that use it keep it."""
        return self._show(rate_id, hidden=True)

    def show(self, rate_id: UUID) -> TaxRateView:
        return self._show(rate_id, hidden=False)

    def delete(self, rate_id: UUID) -> None:
        """Delete a rate nothing refers to; one in use can be hidden."""
        with self.uow() as uow:
            _require(uow.tax_rates.list(for_update=True), rate_id)
            if rate_id in uow.tax_rates.used_ids():
                raise ConflictError(
                    "documents, articles or recurring plans use the rate; hide it instead",
                    code="tax_rate_in_use",
                )
            uow.tax_rates.delete(rate_id)
            uow.commit()

    def presets(self) -> list[PresetOffer]:
        """List the presets of the company's country that no rate comes from, e.g. § 24 UStG."""
        with self.uow() as uow:
            company = _company(uow)
            taken = {rate.preset for rate in uow.tax_rates.list()}
        offers: list[PresetOffer] = []
        for preset in profile_of(company.country).presets:
            if preset.key not in taken:
                rate = preset.to_rate(new_id(), company.default_language)
                offers.append(
                    PresetOffer(
                        key=preset.key,
                        name=rate.name,
                        category=rate.category,
                        values=rate.values,
                        notice=rate.notice,
                        exemption_reason=rate.exemption_reason,
                        sources=preset.sources,
                    )
                )
        return offers

    def take_over_preset(self, key: str) -> TaxRateView:
        """Add the rate of a preset of the company's country, in the company's language."""
        with self.uow() as uow:
            company = _company(uow)
            rates = uow.tax_rates.list(for_update=True)
            preset = next(
                (preset for preset in profile_of(company.country).presets if preset.key == key),
                None,
            )
            if preset is None:
                raise NotFoundError("the country has no such preset", code="unknown_preset")
            if any(rate.preset == key for rate in rates):
                raise ConflictError("a rate comes from this preset already", code="preset_taken")
            _check_room(rates)
            rate = preset.to_rate(new_id(), company.default_language)
            _check_name(rates, rate)
            uow.tax_rates.add(rate)
            uow.commit()
        return TaxRateView(rate, in_use=False)

    def apply_preset_updates(self) -> list[TaxRate]:
        """Add the percentages a release brought to the rates of presets (run at startup).

        A rate gets them only while its percentages are those of its preset so far: a rate
        the user changed is theirs. Running it again changes nothing.
        """
        with self.uow() as uow:
            company = uow.company.get()
            if company is None:
                return []
            presets = {preset.key: preset for preset in profile_of(company.country).presets}
            updated: list[TaxRate] = []
            for rate in uow.tax_rates.list(for_update=True):
                preset = None if rate.preset is None else presets.get(rate.preset)
                if preset is not None and _behind(rate.values, preset.values):
                    newer = replace(rate, values=preset.values)
                    uow.tax_rates.update(newer)
                    updated.append(newer)
            uow.commit()
        return updated

    def _show(self, rate_id: UUID, *, hidden: bool) -> TaxRateView:
        with self.uow() as uow:
            rate = replace(_require(uow.tax_rates.list(for_update=True), rate_id), hidden=hidden)
            uow.tax_rates.update(rate)
            view = TaxRateView(rate, in_use=rate_id in uow.tax_rates.used_ids())
            uow.commit()
        return view


def seed_rates(uow: UnitOfWork, company: Company) -> None:
    """Give a company the base presets of its country, worded in its language."""
    taken = {rate.name.casefold() for rate in uow.tax_rates.list(for_update=True)}
    for preset in profile_of(company.country).base_presets:
        rate = preset.to_rate(new_id(), company.default_language)
        # Only after a change of country: an own rate may carry a preset's name already.
        if rate.name.casefold() not in taken:
            uow.tax_rates.add(rate)


def reseed_rates(uow: UnitOfWork, company: Company) -> None:
    """Replace the presets of the former country by the new one's, while nothing uses a rate.

    Once lines, articles or plans use rates, they all stay and the user adapts them.
    """
    if uow.tax_rates.used_ids():
        return
    for rate in uow.tax_rates.list(for_update=True):
        if rate.preset is not None:
            uow.tax_rates.delete(rate.id)
    seed_rates(uow, company)


def default_rate(rates: Sequence[TaxRate]) -> TaxRate:
    """Return the rate of positions that name none: the standard rate, else the first taxed one."""
    taxed = [rate for rate in rates if not rate.hidden and rate.category is RateCategory.STANDARD]
    if not taxed:
        raise ValidationError("tax_rate_id", "a tax rate is required", code="tax_rate_missing")
    return next((rate for rate in taxed if rate.preset == STANDARD), taxed[0])


def chosen_rate(
    rates: Sequence[TaxRate],
    rate_id: UUID | None,
    *,
    pass_through: bool,
    kept: Collection[UUID] = (),
) -> tuple[TaxCategory, UUID | None]:
    """Resolve the tax choice of a line or an article into its kind and rate (ADR 0044).

    No rate means the default one. A hidden rate stays where it was chosen before (``kept``)
    but is not chosen anew. Pass-through items take no rate (refused by the domain).
    """
    if pass_through:
        return TaxCategory.PASS_THROUGH, rate_id
    if rate_id is None:
        chosen = default_rate(rates)
        return chosen.kind, chosen.id
    rate = next((rate for rate in rates if rate.id == rate_id), None)
    if rate is None:
        raise ValidationError("tax_rate_id", "unknown tax rate", code="tax_rate_unknown")
    if rate.hidden and rate.id not in kept:
        raise ValidationError("tax_rate_id", "the tax rate is hidden", code="tax_rate_hidden")
    return rate.kind, rate.id


def _behind(values: tuple[RateValue, ...], latest: tuple[RateValue, ...]) -> bool:
    """Whether ``values`` are the start of ``latest``, without its newest values."""
    return len(values) < len(latest) and latest[: len(values)] == values


def _values(command: SaveTaxRate) -> tuple[RateValue, ...]:
    """Parse the dated percentages, oldest first."""
    values: list[RateValue] = []
    for index, (valid_from, percent) in enumerate(command.values):
        try:
            values.append(RateValue(valid_from, parse_decimal(percent, "percent")))
        except ValidationError as error:
            raise ValidationError(
                f"values.{index}.{error.field}", error.message, code=error.code
            ) from None
    return tuple(sorted(values, key=lambda value: value.valid_from))


def _company(uow: UnitOfWork) -> Company:
    company = uow.company.get()
    if company is None:
        raise ConflictError("set up the company first", code="company_not_set_up")
    return company


def _require(rates: Sequence[TaxRate], rate_id: UUID) -> TaxRate:
    for rate in rates:
        if rate.id == rate_id:
            return rate
    raise NotFoundError("tax rate not found")


def _check_room(rates: Sequence[TaxRate]) -> None:
    if len(rates) >= MAX_TAX_RATES:
        raise ConflictError(f"at most {MAX_TAX_RATES} tax rates", code="too_many_tax_rates")


def _check_name(rates: Sequence[TaxRate], rate: TaxRate) -> None:
    """Names tell rates apart in every list: no two alike, whatever the case."""
    taken = {other.name.casefold() for other in rates if other.id != rate.id}
    if rate.name.casefold() in taken:
        message = "another tax rate has this name"
        raise ConflictError(message, details={"name": message}, code="tax_rate_name_taken")
