"""Company logo shown on documents."""

from __future__ import annotations

from dataclasses import dataclass

from rhinvoice.domain.shared.errors import ValidationError

MAX_LOGO_BYTES = 1024 * 1024

# Raster formats only: SVG may contain scripts and would need sanitising.
_SIGNATURES: tuple[tuple[str, bytes], ...] = (
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("image/jpeg", b"\xff\xd8\xff"),
)


def _sniff(content: bytes) -> str | None:
    for media_type, signature in _SIGNATURES:
        if content.startswith(signature):
            return media_type
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True, slots=True)
class Logo:
    content: bytes
    media_type: str

    @classmethod
    def from_upload(cls, content: bytes) -> Logo:
        """Validate the size and detect the type from the file content, not its name."""
        if not content:
            raise ValidationError("logo", "the logo file is empty")
        if len(content) > MAX_LOGO_BYTES:
            raise ValidationError("logo", "the logo must be at most 1 MB")
        media_type = _sniff(content)
        if media_type is None:
            raise ValidationError("logo", "the logo must be a PNG, JPEG or WebP image")
        return cls(content=content, media_type=media_type)
