"""Static reference data for forms."""

from fastapi import APIRouter

from rhinvoice.api.country_profiles import CountryProfileResponse
from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ISO_COUNTRY_CODES, ApiModel
from rhinvoice.domain.catalog.unit import UNITS
from rhinvoice.domain.country.registry import PROFILES

router = APIRouter(prefix="/api/reference", tags=["reference"], responses=ERROR_RESPONSES)


class UnitResponse(ApiModel):
    code: str
    label_de: str
    label_en: str


@router.get("/units")
def list_units(_user: CurrentUser) -> list[UnitResponse]:
    """UN/ECE Recommendation 20 unit codes supported for document lines."""
    return [UnitResponse(code=code, label_de=de, label_en=en) for code, (de, en) in UNITS.items()]


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
