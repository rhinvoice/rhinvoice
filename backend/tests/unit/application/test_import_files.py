"""Finding the PDF of an invoice number among the files of an import."""

import hashlib

import pytest

from rhinvoice.application.importing.files import (
    FileIndex,
    FileMatch,
    ImportFile,
    matching_count,
    unique,
)


def original(match: FileMatch | None) -> ImportFile:
    assert match is not None
    assert match.invoice is not None
    return match.invoice


def pdf(path: str, content: bytes | None = None) -> ImportFile:
    return ImportFile(path=path, content=content if content is not None else path.encode())


def test_a_file_knows_its_name_and_hash() -> None:
    file = ImportFile("2016 CH/Rechnung R20160001.pdf", b"%PDF-1.4")
    assert file.name == "Rechnung R20160001.pdf"
    assert file.sha256 == hashlib.sha256(b"%PDF-1.4").hexdigest()
    assert ImportFile("R1.pdf", b"").name == "R1.pdf"


@pytest.mark.parametrize(
    ("number", "name"),
    [
        ("R20150001", "Rechnung R20150001.pdf"),
        ("R20150001", "r20150001.PDF"),
        ("R20150001", "Rechnung 20150001.pdf"),
        ("R2015-0001", "Invoice R2015-0001.pdf"),
        ("R2015-0001", "Invoice 2015-0001.pdf"),
        # File names may join what the number separates.
        ("R2015-0001", "R20150001.pdf"),
        ("R2015-0001", "R2015_0001.pdf"),
        ("2015-001", "RE 2015-001 Muster AG.pdf"),
        ("1042", "Rechnung 1042.pdf"),
        ("1042", "1042.pdf"),
        ("R123", "Rechnung 123.pdf"),
        ("R2015-0001", "R2015-0001.final.pdf"),
    ],
)
def test_the_number_is_found_in_the_file_name(number: str, name: str) -> None:
    match = FileIndex([pdf(f"2015/{name}")]).find(number)
    assert match is not None
    assert original(match).name == name


@pytest.mark.parametrize(
    ("number", "name"),
    [
        # Other numbers with the same digits.
        ("R20150001", "Rechnung R201500012.pdf"),
        ("R20150001", "Rechnung R120150001.pdf"),
        ("R20150001", "RechnungR20150001.pdf"),
        ("1042", "Rechnung 10420.pdf"),
        ("1042", "Rechnung 21042.pdf"),
        ("2015-001", "2015-0011.pdf"),
        # Too short to tell anything.
        ("12", "Rechnung 12.pdf"),
        ("R1", "R1.pdf"),
        ("Rechnung", "Rechnung.pdf"),
        ("R20150001", "Gutschrift 20150002.pdf"),
    ],
)
def test_other_numbers_are_not_mistaken_for_it(number: str, name: str) -> None:
    assert FileIndex([pdf(name)]).find(number) is None


def test_the_plain_file_is_the_invoice_and_the_others_its_attachments() -> None:
    files = [
        pdf("2016 CH/Rechnung R20160032_teil.pdf"),
        pdf("2019 CH/Rechnung R20160032_done.pdf"),
        pdf("2016 CH/pdf/Rechnung R20160032.pdf"),
        pdf("2016 CH/Zahlungserinnerung zu Rechnung R20160032.pdf"),
        pdf("2016 CH/Rechnung R20160032.pdf"),
        pdf("2016 CH/Rechnung R20160033.pdf"),
    ]
    index = FileIndex(files)
    match = index.find("R20160032")
    assert match is not None
    # Plain names first, then the least nested.
    assert original(match).path == "2016 CH/Rechnung R20160032.pdf"
    assert [file.path for file in match.attachments] == [
        "2016 CH/Rechnung R20160032_teil.pdf",
        "2016 CH/Zahlungserinnerung zu Rechnung R20160032.pdf",
        "2016 CH/pdf/Rechnung R20160032.pdf",
        "2019 CH/Rechnung R20160032_done.pdf",
    ]
    assert index.unused == [file.path for file in sorted(index.files, key=lambda f: f.path)]
    index.claim(match)
    assert index.unused == ["2016 CH/Rechnung R20160033.pdf"]


def test_without_a_plain_file_the_shortest_name_is_the_invoice() -> None:
    match = FileIndex([pdf("Rechnung R20150007_new.pdf"), pdf("Rechnung R20150007 v2.pdf")]).find(
        "R20150007"
    )
    assert match is not None
    assert original(match).name == "Rechnung R20150007 v2.pdf"
    assert [file.name for file in match.attachments] == ["Rechnung R20150007_new.pdf"]


def test_copies_with_the_same_content_count_once() -> None:
    files = [
        pdf("2015 CH/sub/Rechnung R20150007.pdf", b"same"),
        pdf("2015 CH/Rechnung R20150007 Kopie.pdf", b"same"),
        pdf("2015 CH/Rechnung R20150007.pdf", b"same"),
        pdf("2015 CH/Rechnung R20150007_new.pdf", b"other"),
    ]
    assert [file.path for file in unique(files)] == [
        "2015 CH/Rechnung R20150007.pdf",
        "2015 CH/Rechnung R20150007_new.pdf",
    ]
    match = FileIndex(files).find("R20150007")
    assert match is not None
    assert original(match).path == "2015 CH/Rechnung R20150007.pdf"
    assert [file.path for file in match.attachments] == ["2015 CH/Rechnung R20150007_new.pdf"]


def test_the_files_tell_the_column_of_the_numbers() -> None:
    index = FileIndex([pdf("Rechnung R20150001.pdf"), pdf("Rechnung R20150002.pdf")])
    assert matching_count(["R20150001", "R20150002", "R20150003"], index) == 2
    assert matching_count(["1", "2", "3"], index) == 0


def test_plain_names_win_over_shorter_paths() -> None:
    files = [pdf("R1234_v2.pdf"), pdf("2015/sub/RECHNUNG R1234.pdf"), pdf("2015/R1234.copy.pdf")]
    match = FileIndex(files).find("R1234")
    assert match is not None
    # "Rechnung" is no extra word, in any case; "copy" after another dot is one.
    assert original(match).path == "2015/sub/RECHNUNG R1234.pdf"
    assert [file.path for file in match.attachments] == ["2015/R1234.copy.pdf", "R1234_v2.pdf"]


def test_a_number_is_found_by_its_longest_digits() -> None:
    match = FileIndex([pdf("Rechnung RE-15-20150001.pdf")]).find("RE-15-20150001")
    assert match is not None


@pytest.mark.parametrize(
    "name",
    [
        "R20150001_korrektur.pdf",
        "1 mahnung zu rechnung r20150001_mahnung.pdf",
        "Kopie R20150001.pdf",
    ],
)
def test_reminders_and_copies_are_attachments_only(name: str) -> None:
    match = FileIndex([pdf(name)]).find("R20150001")
    assert match is not None
    assert match.invoice is None
    assert [file.name for file in match.attachments] == [name]
    assert match.files == match.attachments


def test_other_series_with_the_same_digits_are_not_mixed_up() -> None:
    index = FileIndex([pdf("RE-100.pdf"), pdf("GS-100.pdf"), pdf("Rechnung 100.pdf", b"other")])
    match = index.find("RE-100")
    assert match is not None
    assert match.invoice is not None
    assert original(match).name == "RE-100.pdf"
    assert [file.name for file in match.attachments] == ["Rechnung 100.pdf"]
    credit = index.find("GS-100")
    assert credit is not None
    assert credit.invoice is not None
    assert credit.invoice.name == "GS-100.pdf"


def test_a_file_belongs_to_one_invoice_only() -> None:
    index = FileIndex([pdf("Rechnung 20150001.pdf")])
    first = index.find("R20150001")
    assert first is not None
    index.claim(first)
    assert index.find("A20150001") is None
