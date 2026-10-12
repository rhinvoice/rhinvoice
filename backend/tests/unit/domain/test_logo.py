import pytest

from rhinvoice.domain.company.logo import MAX_LOGO_BYTES, Logo
from rhinvoice.domain.shared.errors import ValidationError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 8


@pytest.mark.parametrize(
    ("content", "media_type"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")],
)
def test_logo_type_is_detected_from_content(content: bytes, media_type: str) -> None:
    logo = Logo.from_upload(content)
    assert logo.media_type == media_type
    assert logo.content == content


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "the logo file is empty"),
        (
            b"<svg xmlns='http://www.w3.org/2000/svg'/>",
            "the logo must be a PNG, JPEG or WebP image",
        ),
        (b"RIFF\x00\x00\x00\x00WAVE", "the logo must be a PNG, JPEG or WebP image"),
        (PNG + b"\x00" * MAX_LOGO_BYTES, "the logo must be at most 1 MB"),
    ],
)
def test_invalid_logos(content: bytes, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        Logo.from_upload(content)
    assert error.value.details == {"logo": message}


def test_logo_size_boundary() -> None:
    exactly = PNG + b"\x00" * (MAX_LOGO_BYTES - len(PNG))
    assert len(Logo.from_upload(exactly).content) == MAX_LOGO_BYTES
    assert MAX_LOGO_BYTES == 1024 * 1024
