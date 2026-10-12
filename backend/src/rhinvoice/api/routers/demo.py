"""Whether this installation is a public demo, and how to get in."""

from fastapi import APIRouter

from rhinvoice.api.dependencies import ContainerDep
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.demo.handlers import DEMO_EMAIL, DEMO_PASSWORD
from rhinvoice.domain.shared.country import Country

router = APIRouter(prefix="/api/demo", tags=["demo"], responses=ERROR_RESPONSES)


class DemoLink(ApiModel):
    country: Country
    url: str


class DemoResponse(ApiModel):
    enabled: bool
    country: Country | None
    email: str | None
    """The shared demo login; None outside a demo."""
    password: str | None
    reset_minutes: int | None
    """Minutes between two resets of all data."""
    links: list[DemoLink]
    """The demos of the other countries."""


@router.get("")
def demo(container: ContainerDep) -> DemoResponse:
    """Tell the login page whether this is a public demo; needs no login."""
    settings = container.settings
    if not settings.demo:
        return DemoResponse(
            enabled=False, country=None, email=None, password=None, reset_minutes=None, links=[]
        )
    return DemoResponse(
        enabled=True,
        country=settings.demo_country,
        email=DEMO_EMAIL,
        password=DEMO_PASSWORD,
        reset_minutes=settings.demo_reset_interval // 60,
        links=[
            DemoLink(country=country, url=url)
            for country, url in settings.demo_link_list
            if country != settings.demo_country
        ],
    )
