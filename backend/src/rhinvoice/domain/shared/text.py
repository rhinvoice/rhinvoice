"""Normalisation and validation of free text fields."""

import re

from rhinvoice.domain.shared.errors import ValidationError

# Control characters break printed addresses and the QR-bill payload (CR/LF separated).
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_CONTROL_EXCEPT_NEWLINE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def clean_text(value: str, field: str, *, max_length: int, required: bool = False) -> str:
    """Strip surrounding whitespace and enforce presence and maximum length."""
    cleaned = value.strip()
    if _CONTROL.search(cleaned):
        raise ValidationError(field, f"{field} must not contain line breaks or control characters")
    if required and not cleaned:
        raise ValidationError(field, f"{field} is required")
    if len(cleaned) > max_length:
        raise ValidationError(field, f"{field} must be at most {max_length} characters long")
    return cleaned


def clean_multiline(value: str, field: str, *, max_length: int) -> str:
    """Like clean_text, but normalises line endings and trailing spaces per line."""
    normalised = value.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    lines = [line.rstrip() for line in normalised.split("\n")]
    cleaned = "\n".join(lines).strip()
    if _CONTROL_EXCEPT_NEWLINE.search(cleaned):
        raise ValidationError(field, f"{field} must not contain control characters")
    if len(cleaned) > max_length:
        raise ValidationError(field, f"{field} must be at most {max_length} characters long")
    return cleaned
