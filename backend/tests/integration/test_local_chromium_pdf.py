"""A real invoice printed by a real Chromium on this computer (ADR 0021).

Uses RHINVOICE_TEST_CHROMIUM, else the headless shell that Playwright installs for the
end-to-end tests; skipped when neither is there.
"""

import io
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pypdf import PdfReader

from rhinvoice.application.document.einvoice import EInvoiceProfile
from rhinvoice.infrastructure.einvoice.cii import CiiWriter
from rhinvoice.infrastructure.rendering.chromium import LocalChromiumPrinter
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from rhinvoice.infrastructure.rendering.pdf import ChromiumPdfRenderer
from tests.einvoice_samples import model, samples

PLAYWRIGHT_CACHES = (
    Path.home() / "Library/Caches/ms-playwright",
    Path.home() / ".cache/ms-playwright",
)


def find_chromium() -> Path | None:
    configured = os.environ.get("RHINVOICE_TEST_CHROMIUM")
    if configured:
        return Path(configured)
    shells = sorted(
        shell
        for cache in PLAYWRIGHT_CACHES
        for shell in cache.glob("chromium_headless_shell-*/chrome-*/chrome-headless-shell")
    )
    return shells[-1] if shells else None


@pytest.fixture(scope="module")
def chromium() -> Iterator[LocalChromiumPrinter]:
    binary = find_chromium()
    if binary is None:
        pytest.skip("no Chromium on this computer")
    browser = LocalChromiumPrinter(binary)
    yield browser
    browser.close()


def test_a_swiss_invoice_with_its_qr_bill_and_e_invoice(chromium: LocalChromiumPrinter) -> None:
    printed = model(samples()["ch-domestic"])
    renderer = ChromiumPdfRenderer(JinjaDocumentRenderer(), chromium)
    content = renderer.pdf(printed, CiiWriter().xml(printed, EInvoiceProfile.EN16931))
    reader = PdfReader(io.BytesIO(content))
    number = printed.view.document.number
    assert number is not None
    assert len(reader.pages) == 2
    assert number in reader.pages[0].extract_text()
    assert "Zahlteil" in reader.pages[1].extract_text()
    assert list(reader.attachments) == ["factur-x.xml"]
