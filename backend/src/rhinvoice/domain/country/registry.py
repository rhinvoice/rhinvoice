"""The country profiles Rhinvoice knows; one per supported company country."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rhinvoice.domain.country import at, ch, de, li

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rhinvoice.domain.country.profile import CountryProfile
    from rhinvoice.domain.shared.country import Country

PROFILES: Mapping[Country, CountryProfile] = {
    profile.country: profile for profile in (ch.PROFILE, li.PROFILE, de.PROFILE, at.PROFILE)
}


def profile_of(country: Country) -> CountryProfile:
    """Return the profile of a company's country."""
    return PROFILES[country]
