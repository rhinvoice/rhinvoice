"""The company's units and the catalogue they come from (ADR 0046)."""

from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel, text
from rhinvoice.application.catalog.units import MAX_UNITS, Removal, SaveUnit, UnitOffer, UnitView
from rhinvoice.domain.catalog.unit import MAX_UNIT_DESCRIPTION, MAX_UNIT_LABEL, UNIT_CODES, Unit
from rhinvoice.domain.catalog.unit_presets import UnitGroup
from rhinvoice.domain.shared.language import Language

router = APIRouter(prefix="/api/units", tags=["units"], responses=ERROR_RESPONSES)

CODE_PATTERN = r"^[0-9A-Z]{2,3}$"
PresetKey = Annotated[str, Field(pattern=CODE_PATTERN)]


class UnitLabels(ApiModel):
    """Labels of English, French and Italian documents; empty: the main label."""

    en: str = text(MAX_UNIT_LABEL)
    fr: str = text(MAX_UNIT_LABEL)
    it: str = text(MAX_UNIT_LABEL)

    @classmethod
    def of(cls, unit: Unit) -> Self:
        return cls(en=unit.label_en, fr=unit.label_fr, it=unit.label_it)


class UnitRequest(ApiModel):
    label: str = text(MAX_UNIT_LABEL, required=True)
    """Printed on documents, also in the languages without a label of their own."""
    code: str = Field(pattern=CODE_PATTERN)
    """A code of the EN 16931 unit code list (GET /api/units/codes), sent in e-invoices."""
    labels: UnitLabels = Field(default_factory=UnitLabels)
    description: str = text(MAX_UNIT_DESCRIPTION)
    """For the user only; never printed."""

    def to_command(self) -> SaveUnit:
        return SaveUnit(
            label=self.label,
            code=self.code,
            label_en=self.labels.en,
            label_fr=self.labels.fr,
            label_it=self.labels.it,
            description=self.description,
        )


class UnitResponse(ApiModel):
    id: UUID
    code: str
    label: str
    labels: UnitLabels
    description: str
    preset: str | None
    """The catalogue entry the unit comes from."""
    hidden: bool
    """Not offered for new lines and articles; those that use it keep it."""
    in_use: bool
    """Document lines, articles or recurring plans refer to it: removing hides it."""

    @classmethod
    def of(cls, view: UnitView) -> Self:
        unit = view.unit
        return cls(
            id=unit.id,
            code=unit.code,
            label=unit.label,
            labels=UnitLabels.of(unit),
            description=unit.description,
            preset=unit.preset,
            hidden=unit.hidden,
            in_use=view.in_use,
        )


class UnitCodeResponse(ApiModel):
    code: str
    name: str
    """The official English name."""


class UnitOfferResponse(ApiModel):
    """A catalogue entry to add (``key``) or a hidden unit to show again (``unit_id``)."""

    key: str | None
    unit_id: UUID | None
    group: UnitGroup | None
    """The catalogue's group; none for a hidden unit of the user's own."""
    code: str
    label: str
    names: dict[Language, str]
    """The catalogue entry's names in the four languages; empty for the user's own units."""
    description: str

    @classmethod
    def of(cls, offer: UnitOffer) -> Self:
        return cls(
            key=offer.key,
            unit_id=offer.unit_id,
            group=offer.group,
            code=offer.code,
            label=offer.label,
            names=dict(offer.names),
            description=offer.description,
        )


class TakeOverRequest(ApiModel):
    keys: list[PresetKey] = Field(default_factory=list[PresetKey], max_length=MAX_UNITS)
    """Catalogue entries to add."""
    unit_ids: list[UUID] = Field(default_factory=list[UUID], max_length=MAX_UNITS)
    """Hidden units to show again."""


class UnitOrderRequest(ApiModel):
    unit_ids: list[UUID] = Field(max_length=MAX_UNITS)
    """Every unit offered (not hidden), each once, in the new order."""


class RemovalResponse(ApiModel):
    removal: Removal
    """deleted, or hidden when lines, articles or recurring plans use the unit."""


@router.get("")
def list_units(_user: CurrentUser, container: ContainerDep) -> list[UnitResponse]:
    """Every unit of the company, hidden ones too, in their order."""
    return [UnitResponse.of(view) for view in container.units.units()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_unit(body: UnitRequest, _user: CurrentUser, container: ContainerDep) -> UnitResponse:
    """Add an own unit at the end of the list.

    422 unit_code_unknown; 409 unit_label_taken, too_many_units.
    """
    return UnitResponse.of(container.units.create(body.to_command()))


@router.get("/codes")
def list_unit_codes(_user: CurrentUser) -> list[UnitCodeResponse]:
    """List the EN 16931 unit codes (UN/ECE Recommendation 20 and 21) with their names."""
    return [UnitCodeResponse(code=code, name=name) for code, name in UNIT_CODES.items()]


@router.get("/presets")
def list_unit_presets(_user: CurrentUser, container: ContainerDep) -> list[UnitOfferResponse]:
    """List the catalogue entries no unit comes from yet, then the hidden units."""
    return [UnitOfferResponse.of(offer) for offer in container.units.presets()]


@router.post("/presets")
def take_over_unit_presets(
    body: TakeOverRequest, _user: CurrentUser, container: ContainerDep
) -> list[UnitResponse]:
    """Show hidden units again and add catalogue entries, at the end of the list.

    404 unit_preset_unknown; 409 unit_preset_taken, unit_label_taken, too_many_units.
    """
    views = container.units.take_over(body.keys, body.unit_ids)
    return [UnitResponse.of(view) for view in views]


@router.put("/order")
def order_units(
    body: UnitOrderRequest, _user: CurrentUser, container: ContainerDep
) -> list[UnitResponse]:
    """Sort the units offered; the order is that of the unit selects.

    422 unit_order_incomplete.
    """
    return [UnitResponse.of(view) for view in container.units.reorder(body.unit_ids)]


@router.put("/{unit_id}")
def save_unit(
    unit_id: UUID, body: UnitRequest, _user: CurrentUser, container: ContainerDep
) -> UnitResponse:
    """Change label, code and texts; issued documents keep what they were issued with.

    422 unit_code_unknown; 409 unit_label_taken.
    """
    return UnitResponse.of(container.units.update(unit_id, body.to_command()))


@router.post("/{unit_id}/remove")
def remove_unit(unit_id: UUID, _user: CurrentUser, container: ContainerDep) -> RemovalResponse:
    """Delete a unit nothing uses, else hide it.

    409 unit_last_visible: the last unit offered stays.
    """
    return RemovalResponse(removal=container.units.remove(unit_id))


@router.post("/{unit_id}/show")
def show_unit(unit_id: UUID, _user: CurrentUser, container: ContainerDep) -> UnitResponse:
    """Offer a hidden unit again, at the end of the list."""
    return UnitResponse.of(container.units.show(unit_id))
