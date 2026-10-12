"""Shared test helpers."""

import io
import re
from contextlib import AbstractContextManager

import pytest
from pypdf import PdfWriter

A4 = (595, 842)


def raises_exactly[E: BaseException](
    exception: type[E],
    message: str,
) -> AbstractContextManager[pytest.ExceptionInfo[E]]:
    """Expect ``exception`` whose message equals ``message`` exactly."""
    return pytest.raises(exception, match=f"^{re.escape(message)}$")


def blank_pdf() -> bytes:
    """Make a one-page PDF, a stand-in for Chromium's output."""
    writer = PdfWriter()
    writer.add_blank_page(*A4)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
