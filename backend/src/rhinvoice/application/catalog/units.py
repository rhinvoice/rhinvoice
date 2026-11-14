"""Use cases for the company's units (ADR 0046).

Every installation starts with the units of before (migration 0029); users add, rename,
sort and remove units and take further ones from the catalogue. Lines, articles and
recurring plans refer to a unit: one in use is hidden instead of deleted, and comes back
through the catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.domain.catalog.unit import Unit
from rhinvoice.domain.catalog.unit_presets import PRESETS, preset_of
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence
    from uuid import UUID

    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.catalog.unit_presets import UnitGroup

MAX_UNITS = 100


@dataclass(frozen=True, slots=True)
class SaveUnit:
    label: str
    code: str
    label_en: str = ""
    label_fr: str = ""
    label_it: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class UnitView:
    unit: Unit
    in_use: bool
    """Document lines, articles or recurring plans refer to it: removing hides it."""


class Removal(StrEnum):
    """What removing a unit did."""

    DELETED = "deleted"
    HIDDEN = "hidden"
    """Something uses the unit: it is hidden and comes back through the catalogue."""


@dataclass(frozen=True, slots=True)
class UnitOffer:
    """What the catalogue dialog offers: an entry no unit comes from, or a hidden unit."""

    code: str
    label: str
    group: UnitGroup | None
    """The catalogue's group; None for a hidden unit of the user's own."""
    names: Mapping[Language, str] = field(default_factory=dict[Language, str])
    """The catalogue entry's names; none for a hidden unit of the user's own."""
    description: str = ""
    key: str | None = None
    """The catalogue entry to add."""
    unit_id: UUID | None = None
    """The hidden unit to show again."""


@dataclass(frozen=True, slots=True)
class UnitHandlers:
    uow: UnitOfWorkFactory

    def units(self) -> list[UnitView]:
        """Every unit, hidden ones too, in their order."""
        with self.uow() as uow:
            used = uow.units.used_ids()
            return [UnitView(unit, unit.id in used) for unit in uow.units.list()]

    def create(self, command: SaveUnit) -> UnitView:
        with self.uow() as uow:
            units = uow.units.list(for_update=True)
            _check_room(units, 1)
            unit = Unit(
                id=new_id(),
                code=command.code,
                label=command.label,
                label_en=command.label_en,
                label_fr=command.label_fr,
                label_it=command.label_it,
                description=command.description,
            )
            _check_label(units, unit)
            uow.units.add(unit)
            uow.commit()
        return UnitView(unit, in_use=False)

    def update(self, unit_id: UUID, command: SaveUnit) -> UnitView:
        """Change label, code and texts; issued documents keep the unit they were issued with."""
        with self.uow() as uow:
            units = uow.units.list(for_update=True)
            unit = replace(
                _require(units, unit_id),
                code=command.code,
                label=command.label,
                label_en=command.label_en,
                label_fr=command.label_fr,
                label_it=command.label_it,
                description=command.description,
            )
            _check_label(units, unit)
            uow.units.update(unit)
            view = UnitView(unit, in_use=unit_id in uow.units.used_ids())
            uow.commit()
        return view

    def remove(self, unit_id: UUID) -> Removal:
        """Delete a unit nothing uses, else hide it; the last unit offered stays."""
        with self.uow() as uow:
            units = uow.units.list(for_update=True)
            unit = _require(units, unit_id)
            if not unit.hidden and not any(
                not other.hidden for other in units if other.id != unit_id
            ):
                raise ConflictError(
                    "the last unit offered for lines cannot be removed", code="unit_last_visible"
                )
            # A line or an article saved meanwhile keeps the unit from going, too.
            if unit_id in uow.units.used_ids() or not uow.units.delete(unit_id):
                uow.units.update(replace(unit, hidden=True))
                removal = Removal.HIDDEN
            else:
                removal = Removal.DELETED
            uow.commit()
        return removal

    def show(self, unit_id: UUID) -> UnitView:
        """Offer a hidden unit again, at the end of the list."""
        with self.uow() as uow:
            units = uow.units.list(for_update=True)
            unit = _require(units, unit_id)
            shown = _shown(uow, units, [unit])[0]
            view = UnitView(shown, in_use=unit_id in uow.units.used_ids())
            uow.commit()
        return view

    def reorder(self, unit_ids: Sequence[UUID]) -> list[UnitView]:
        """Sort the units offered; ``unit_ids`` names each of them once, hidden ones stay last."""
        with self.uow() as uow:
            units = uow.units.list(for_update=True)
            visible = [unit.id for unit in units if not unit.hidden]
            if len(unit_ids) != len(visible) or set(unit_ids) != set(visible):
                raise ValidationError(
                    "unit_ids",
                    "the order names every unit offered once",
                    code="unit_order_incomplete",
                )
            uow.units.reorder([*unit_ids, *(unit.id for unit in units if unit.hidden)])
            used = uow.units.used_ids()
            views = [UnitView(unit, unit.id in used) for unit in uow.units.list()]
            uow.commit()
        return views

    def presets(self) -> list[UnitOffer]:
        """List the catalogue entries no unit comes from yet, then the hidden units.

        A hidden unit from the catalogue shows in its group; an entry whose label a unit
        has already is not offered.
        """
        with self.uow() as uow:
            units = uow.units.list()
        taken = {unit.preset for unit in units}
        labels = {unit.label.casefold() for unit in units}
        offers = [
            UnitOffer(
                code=preset.code,
                label=preset.labels[Language.DE],
                group=preset.group,
                names=preset.names,
                key=preset.key,
            )
            for preset in PRESETS
            if preset.key not in taken and preset.labels[Language.DE].casefold() not in labels
        ]
        for unit in units:
            if unit.hidden:
                preset = preset_of(unit.preset)
                offers.append(
                    UnitOffer(
                        code=unit.code,
                        label=unit.label,
                        group=None if preset is None else preset.group,
                        names={} if preset is None else preset.names,
                        description=unit.description,
                        unit_id=unit.id,
                    )
                )
        return offers

    def take_over(self, keys: Sequence[str], unit_ids: Sequence[UUID]) -> list[UnitView]:
        """Show the hidden ``unit_ids`` again and add the catalogue's ``keys``, at the end."""
        with self.uow() as uow:
            units = uow.units.list(for_update=True)
            hidden = [_require(units, unit_id) for unit_id in dict.fromkeys(unit_ids)]
            _shown(uow, units, hidden)
            added: list[Unit] = []
            for key in dict.fromkeys(keys):
                preset = preset_of(key)
                if preset is None:
                    raise NotFoundError(
                        "the catalogue has no such unit", code="unit_preset_unknown"
                    )
                if any(unit.preset == key for unit in units):
                    raise ConflictError(
                        "a unit comes from this entry already", code="unit_preset_taken"
                    )
                unit = preset.to_unit(new_id())
                _check_label([*units, *added], unit)
                added.append(unit)
            _check_room(units, len(added))
            for unit in added:
                uow.units.add(unit)
            used = uow.units.used_ids()
            views = [UnitView(unit, unit.id in used) for unit in uow.units.list()]
            uow.commit()
        return views


def default_unit(units: Sequence[Unit]) -> Unit:
    """Return the unit of articles that name none: the first one offered."""
    unit = next((unit for unit in units if not unit.hidden), None)
    if unit is None:
        raise ValidationError("unit_id", "a unit is required", code="unit_missing")
    return unit


def chosen_unit(
    units: Sequence[Unit], unit_id: UUID | None, *, kept: Collection[UUID] = ()
) -> UUID | None:
    """Check the unit of a line or an article (ADR 0046).

    A hidden unit stays where it was chosen before (``kept``) but is not chosen anew.
    """
    if unit_id is None:
        return None
    unit = next((unit for unit in units if unit.id == unit_id), None)
    if unit is None:
        raise ValidationError("unit_id", "unknown unit", code="unit_unknown")
    if unit.hidden and unit.id not in kept:
        raise ValidationError("unit_id", "the unit is hidden", code="unit_hidden")
    return unit.id


def _shown(uow: UnitOfWork, units: Sequence[Unit], showing: Sequence[Unit]) -> list[Unit]:
    """Offer the hidden ones of ``showing`` again, after the units offered so far."""
    hidden = [unit for unit in showing if unit.hidden]
    for unit in hidden:
        uow.units.update(replace(unit, hidden=False))
    if hidden:
        moved = {unit.id for unit in hidden}
        uow.units.reorder(
            [
                *(unit.id for unit in units if not unit.hidden),
                *(unit.id for unit in hidden),
                *(unit.id for unit in units if unit.hidden and unit.id not in moved),
            ]
        )
    return [replace(unit, hidden=False) for unit in showing]


def _require(units: Sequence[Unit], unit_id: UUID) -> Unit:
    for unit in units:
        if unit.id == unit_id:
            return unit
    raise NotFoundError("unit not found")


def _check_room(units: Sequence[Unit], adding: int) -> None:
    if len(units) + adding > MAX_UNITS:
        raise ConflictError(f"at most {MAX_UNITS} units", code="too_many_units")


def _check_label(units: Sequence[Unit], unit: Unit) -> None:
    """Labels tell units apart in every list: no two alike, whatever the case."""
    taken = {other.label.casefold() for other in units if other.id != unit.id}
    if unit.label.casefold() in taken:
        message = "another unit has this label"
        raise ConflictError(message, details={"label": message}, code="unit_label_taken")
