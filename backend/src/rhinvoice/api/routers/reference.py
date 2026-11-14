"""Static reference data for forms."""

from fastapi import APIRouter

from rhinvoice.api.country_profiles import CountryProfileResponse
from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ISO_COUNTRY_CODES
from rhinvoice.domain.country.registry import PROFILES

router = APIRouter(prefix="/api/reference", tags=["reference"], responses=ERROR_RESPONSES)


@router.get("/countries")
def list_countries(_user: CurrentUser) -> list[str]:
    """ISO 3166-1 alpha-2 codes; names are localised in the browser (Intl.DisplayNames)."""
    return ISO_COUNTRY_CODES


@router.get("/country-profiles")
def list_country_profiles(
    _user: CurrentUser, container: ContainerDep
) -> list[CountryProfileResponse]:
    """List what differs between the company countries: VAT, terms, payment codes."""
    today = container.clock.today()
    return [CountryProfileResponse.of(profile, today) for profile in PROFILES.values()]
