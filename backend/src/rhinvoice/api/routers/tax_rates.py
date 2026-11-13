"""The company's tax rates and the presets of its country (ADR 0044)."""

from datetime import date
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Path, status
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, PERCENT_PATTERN, ApiModel, plain_number, text
from rhinvoice.application.tax.handlers import PresetOffer, SaveTaxRate, TaxRateView
from rhinvoice.domain.tax.tax_rate import (
    MAX_RATE_NAME,
    MAX_RATE_TEXT,
    MAX_RATE_VALUES,
    RateCategory,
    RateValue,
)

router = APIRouter(prefix="/api/tax-rates", tags=["tax-rates"], responses=ERROR_RESPONSES)

MAX_PRESET_KEY = 40


class RateValueSchema(ApiModel):
    """A percentage and the day it applies from, until the next value."""

    valid_from: date
    percent: str = Field(pattern=PERCENT_PATTERN)
    """From 0 to below 100, at most two decimal places, e.g. "8.1"."""

    @classmethod
    def of(cls, value: RateValue) -> Self:
        return cls(valid_from=value.valid_from, percent=plain_number(value.percent))


class TaxRateRequest(ApiModel):
    name: str = text(MAX_RATE_NAME, required=True)
    category: RateCategory
    """S: taxed above 0 %, Z: zero-rated, E: exempt (needs the exemption reason). It cannot
    change after the rate is created."""
    values: list[RateValueSchema] = Field(min_length=1, max_length=MAX_RATE_VALUES)
    exemption_reason: str = text(MAX_RATE_TEXT)
    """Why the supply is exempt (category E): printed with the line, sent as BT-120."""
    notice: str = text(MAX_RATE_TEXT)
    """Printed on documents that use the rate, e.g. "Durchschnittssatz nach § 24 UStG"."""

    def to_command(self) -> SaveTaxRate:
        return SaveTaxRate(
            name=self.name,
            category=self.category,
            values=tuple((value.valid_from, value.percent) for value in self.values),
            exemption_reason=self.exemption_reason,
            notice=self.notice,
        )


class TaxRateResponse(ApiModel):
    id: UUID
    name: str
    category: RateCategory
    values: list[RateValueSchema]
    """Oldest first; each applies from its date until the next one."""
    exemption_reason: str
    notice: str
    preset: str | None
    """The country preset the rate comes from; a release may add new values to it."""
    hidden: bool
    """Not offered for new lines and articles; those that use it keep it."""
    in_use: bool
    """Document lines, articles or recurring plans refer to it: it can be hidden, not deleted."""

    @classmethod
    def of(cls, view: TaxRateView) -> Self:
        rate = view.rate
        return cls(
            id=rate.id,
            name=rate.name,
            category=rate.category,
            values=[RateValueSchema.of(value) for value in rate.values],
            exemption_reason=rate.exemption_reason,
            notice=rate.notice,
            preset=rate.preset,
            hidden=rate.hidden,
            in_use=view.in_use,
        )


class TaxRatePresetResponse(ApiModel):
    """A preset of the company's country that no rate comes from yet."""

    key: str
    name: str
    """In the company's language."""
    category: RateCategory
    values: list[RateValueSchema]
    notice: str
    exemption_reason: str
    sources: list[str]
    """Official sources of the percentages."""

    @classmethod
    def of(cls, offer: PresetOffer) -> Self:
        return cls(
            key=offer.key,
            name=offer.name,
            category=offer.category,
            values=[RateValueSchema.of(value) for value in offer.values],
            notice=offer.notice,
            exemption_reason=offer.exemption_reason,
            sources=list(offer.sources),
        )


@router.get("")
def list_tax_rates(_user: CurrentUser, container: ContainerDep) -> list[TaxRateResponse]:
    """Every rate of the company, hidden ones too, in their order."""
    return [TaxRateResponse.of(view) for view in container.tax_rates.rates()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tax_rate(
    body: TaxRateRequest, _user: CurrentUser, container: ContainerDep
) -> TaxRateResponse:
    """Add an own rate.

    422 rate_standard_needs_percent, rate_zero_needs_zero, rate_exempt_needs_reason;
    409 tax_rate_name_taken, too_many_tax_rates.
    """
    return TaxRateResponse.of(container.tax_rates.create(body.to_command()))


@router.get("/presets")
def list_tax_rate_presets(
    _user: CurrentUser, container: ContainerDep
) -> list[TaxRatePresetResponse]:
    """List the presets of the company's country no rate comes from yet (e.g. § 24 UStG).

    409 company_not_set_up.
    """
    return [TaxRatePresetResponse.of(offer) for offer in container.tax_rates.presets()]


@router.post("/presets/{key}", status_code=status.HTTP_201_CREATED)
def take_over_tax_rate_preset(
    key: Annotated[str, Path(max_length=MAX_PRESET_KEY)],
    _user: CurrentUser,
    container: ContainerDep,
) -> TaxRateResponse:
    """Add the rate of a preset of the company's country.

    404 unknown_preset; 409 preset_taken, tax_rate_name_taken, too_many_tax_rates,
    company_not_set_up.
    """
    return TaxRateResponse.of(container.tax_rates.take_over_preset(key))


@router.put("/{rate_id}")
def save_tax_rate(
    rate_id: UUID, body: TaxRateRequest, _user: CurrentUser, container: ContainerDep
) -> TaxRateResponse:
    """Change name, texts and percentages; issued documents keep what they were issued with.

    422 rate_category_fixed (the category stays) and the checks of creating;
    409 tax_rate_name_taken.
    """
    return TaxRateResponse.of(container.tax_rates.update(rate_id, body.to_command()))


@router.post("/{rate_id}/hide")
def hide_tax_rate(rate_id: UUID, _user: CurrentUser, container: ContainerDep) -> TaxRateResponse:
    """Offer the rate no more for new lines and articles; those that use it keep it."""
    return TaxRateResponse.of(container.tax_rates.hide(rate_id))


@router.post("/{rate_id}/show")
def show_tax_rate(rate_id: UUID, _user: CurrentUser, container: ContainerDep) -> TaxRateResponse:
    """Offer a hidden rate again."""
    return TaxRateResponse.of(container.tax_rates.show(rate_id))


@router.delete("/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tax_rate(rate_id: UUID, _user: CurrentUser, container: ContainerDep) -> None:
    """Delete a rate nothing refers to.

    409 tax_rate_in_use: lines, articles or recurring plans use it; hide it instead.
    """
    container.tax_rates.delete(rate_id)
