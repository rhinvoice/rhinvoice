from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from rhinvoice.domain.shared.country import Country

type UpdateChannel = Literal["stable", "test"]
"""stable: the latest release; test: release candidates too (vX.Y.Z-rc.N pre-releases)."""


def parse_demo_links(text: str) -> list[tuple[Country, str]]:
    """Read "DE=https://…,AT=https://…"; a malformed entry stops the start."""
    links: list[tuple[Country, str]] = []
    for entry in filter(None, (part.strip() for part in text.split(","))):
        code, separator, url = entry.partition("=")
        url = url.strip()
        if not separator or not url.startswith("https://"):
            msg = f"'{entry}' is not COUNTRY=https://…"
            raise ValueError(msg)
        links.append((Country(code.strip().upper()), url))
    return links


class Settings(BaseSettings):
    """Runtime configuration, read from ``RHINVOICE_*`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="RHINVOICE_", env_file=None)

    database_url: str = Field(
        default="postgresql+psycopg://rhinvoice:rhinvoice-dev@127.0.0.1:5433/rhinvoice",
    )
    timezone: str = "Europe/Zurich"
    cookie_secure: bool = True
    local_port: int | None = None
    """The port of a server on 127.0.0.1 only (the installation without Docker): requests
    must then be addressed to 127.0.0.1 or localhost on this port, and changes must not come
    from another site's page (DNS rebinding, ADR 0034). None, as with Docker: any address,
    the reverse proxy decides which ones reach the server."""
    run_migrations: bool = True
    static_dir: Path | None = None
    theme_dir: Path | None = None
    """Folder with templates that replace the built-in ones (layout, document, reminder, css)."""
    gotenberg_url: str | None = None
    """Base URL of Gotenberg, e.g. http://gotenberg:3000 (the Docker setup)."""
    chromium_path: Path | None = None
    """Chrome, Edge or Chromium on this computer that prints the PDFs when there is no
    Gotenberg (installations without Docker, ADR 0021). Without either there are no PDFs."""
    reset_code_dir: Path | None = None
    """Private folder for the code of a forgotten password (installations without Docker,
    ADR 0024). Without it, an administrator resets passwords with ``rhinvoice user``."""
    log_file: Path | None = None
    """The program's log, whose end a problem report carries (installations without
    Docker). Without it the log stays with the server (docker compose logs app)."""
    update_check: bool = True
    """Ask GitHub once a day whether a newer release exists, to show it in the program
    (ADR 0022). Off: nothing leaves this installation for it."""
    update_channel: UpdateChannel = "stable"
    """Which releases the update check offers. stable: the latest release, never a
    pre-release. test: also release candidates (GitHub pre-releases tagged vX.Y.Z-rc.N),
    for the maintainer's test machines; the same signature check applies."""
    recurring: bool = True
    """Write due recurring invoices in the background of ``rhinvoice serve``."""
    recurring_interval: int = Field(default=600, ge=60)
    """Seconds between two looks for due recurring invoices."""
    demo: bool = False
    """A public demo: the database is emptied and filled with demo data at the start and
    every ``demo_reset_interval`` seconds, and settings that would lock others out are
    refused. Never on an installation with real data (it refuses one with other users)."""
    demo_country: Country = Country.CH
    """The country of the demo company."""
    demo_reset_interval: int = Field(default=3600, ge=300)
    demo_links: str = ""
    """The demos of other countries, e.g. "DE=https://de.demo.example.org,AT=https://…"."""

    @field_validator("demo_links")
    @classmethod
    def _valid_links(cls, value: str) -> str:
        parse_demo_links(value)
        return value

    @property
    def demo_link_list(self) -> list[tuple[Country, str]]:
        """The other demos as (country, URL)."""
        return parse_demo_links(self.demo_links)

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
