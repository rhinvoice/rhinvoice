"""PDF uploads of an invoice import: single files, folders and ZIP files."""

import io
import zipfile

import pytest

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.infrastructure.importing import archive
from rhinvoice.infrastructure.importing.archive import read_files
from tests.helpers import raises_exactly

PDF = b"%PDF-1.4 invoice"


def zipped(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        for name, content in entries.items():
            package.writestr(name, content)
        package.writestr(zipfile.ZipInfo("2015/empty-folder/"), b"")
    return buffer.getvalue()


def test_pdf_files_are_taken_and_everything_else_left_out() -> None:
    files = read_files(
        [
            ("2016 CH/Rechnung R20160001.pdf", PDF),
            ("2016 CH\\Rechnung R20160002.PDF", PDF),
            ("./../2016 CH//Rechnung R20160003.pdf", PDF),
            ("2026 CH/zeit/zeit-05-26.png", b"\x89PNG"),
            ("2026 CH/.DS_Store", b"\x00"),
            (".hidden/Rechnung R1.pdf", PDF),
            ("2023/Rechnungsübersicht.xlsx", b"PK\x03\x04"),
        ]
    )
    assert [file.path for file in files] == [
        "2016 CH/Rechnung R20160001.pdf",
        "2016 CH/Rechnung R20160002.PDF",
        "2016 CH/Rechnung R20160003.pdf",
    ]
    assert files[0].content == PDF


def test_zip_files_are_unpacked() -> None:
    package = zipped(
        {
            "IN/2015/Rechnung R20150001.pdf": PDF,
            "IN/2015/notes.txt": b"x",
            "__MACOSX/IN/2015/._Rechnung R20150001.pdf": b"meta",
        }
    )
    files = read_files([("Rechnungen.zip", package), ("R20150002.pdf", PDF)])
    assert [(file.path, file.content) for file in files] == [
        ("IN/2015/Rechnung R20150001.pdf", PDF),
        ("R20150002.pdf", PDF),
    ]
    # A ZIP needs its name: anything else starting like one is no upload of PDFs.
    assert read_files([("archive.bin", package)]) == ()


def test_damaged_zip_files_are_refused() -> None:
    with raises_exactly(ValidationError, "broken.zip cannot be read as ZIP file") as caught:
        read_files([("broken.zip", b"PK\x03\x04 not really")])
    assert caught.value.code == "unreadable_file"
    package = bytearray(zipped({"R20150001.pdf": PDF * 50}))
    # Damage the compressed data of the entry: the header still reads.
    start = package.index(b"R20150001.pdf") + len("R20150001.pdf")
    package[start : start + 20] = b"\xff" * 20
    with raises_exactly(ValidationError, "damaged.zip cannot be unpacked") as caught:
        read_files([("damaged.zip", bytes(package))])
    assert caught.value.code == "unreadable_file"


def test_zip_files_are_unpacked_within_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    package = zipped({"a/R20150001.pdf": PDF, "a/R20150002.pdf": PDF})
    monkeypatch.setattr(archive, "MAX_ENTRIES", 1)
    with raises_exactly(ValidationError, "the ZIP files hold more than 1 files") as caught:
        read_files([("big.zip", package)])
    assert caught.value.code == "too_many_files"
    monkeypatch.setattr(archive, "MAX_ENTRIES", 10)
    monkeypatch.setattr(archive, "MAX_UNPACKED_BYTES", len(PDF))
    with raises_exactly(ValidationError, "the ZIP files unpack to more than 500 MB") as caught:
        read_files([("big.zip", package)])
    assert caught.value.code == "file_too_large"


def test_the_limits_count_all_zip_files_together(monkeypatch: pytest.MonkeyPatch) -> None:
    package = zipped({"a/R20150001.pdf": PDF})
    monkeypatch.setattr(archive, "MAX_UNPACKED_BYTES", len(PDF) * 2)
    assert len(read_files([("a.zip", package), ("b.zip", package)])) == 2
    with raises_exactly(ValidationError, "the ZIP files unpack to more than 500 MB"):
        read_files([("a.zip", package), ("b.zip", package), ("c.zip", package)])
    monkeypatch.setattr(archive, "MAX_UNPACKED_BYTES", 10**9)
    monkeypatch.setattr(archive, "MAX_ENTRIES", 2)
    with raises_exactly(ValidationError, "the ZIP files hold more than 2 files"):
        read_files([("a.zip", package), ("b.zip", package), ("c.zip", package)])


def test_a_large_pdf_is_refused_before_it_is_unpacked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive, "MAX_ENTRY_BYTES", len(PDF))
    assert len(read_files([("a.zip", zipped({"R1.pdf": PDF}))])) == 1
    with raises_exactly(ValidationError, "IN/R2.pdf is larger than 20 MB") as caught:
        read_files([("a.zip", zipped({"IN/R2.pdf": PDF + b"x"}))])
    assert caught.value.code == "file_too_large"
