"""The end of the program's log and the name of the system, for a problem report."""

from pathlib import Path

from rhinvoice.application.support.ports import ProgramLog
from rhinvoice.infrastructure.support.program_log import TAIL_BYTES, ProgramLogFile, system_name


def test_the_last_lines_of_the_log(tmp_path: Path) -> None:
    path = tmp_path / "rhinvoice.log"
    path.write_text("".join(f"line {number}\n" for number in range(1, 11)), encoding="utf-8")
    assert ProgramLogFile(path).last_lines(3) == "line 8\nline 9\nline 10"
    assert ProgramLogFile(path).last_lines(50).startswith("line 1\n")


def test_a_long_log_is_read_from_its_end(tmp_path: Path) -> None:
    path = tmp_path / "rhinvoice.log"
    line = "x" * 99 + "\n"
    path.write_text(line * (3 * TAIL_BYTES // len(line)) + "the last one\n", encoding="utf-8")
    lines = ProgramLogFile(path).last_lines(10_000).splitlines()
    # Only whole lines: the one the cut starts in is left out.
    assert set(lines[:-1]) == {"x" * 99}
    assert lines[-1] == "the last one"
    assert len(lines) <= TAIL_BYTES // len(line) + 1


def test_bytes_that_are_no_text_do_not_stop_the_report(tmp_path: Path) -> None:
    path = tmp_path / "rhinvoice.log"
    path.write_bytes(b"caf\xe9\n")
    assert ProgramLogFile(path).last_lines(5) == "caf�"


def test_without_a_log_the_report_has_no_lines(tmp_path: Path) -> None:
    assert ProgramLogFile(tmp_path / "rhinvoice.log").last_lines(5) == ""


def test_the_system_is_named_as_people_know_it() -> None:
    assert system_name("Windows", "11", "AMD64", "") == "Windows 11 (AMD64)"
    assert system_name("Darwin", "25.0.0", "arm64", "26.0") == "macOS 26.0 (arm64)"
    assert system_name("Darwin", "25.0.0", "arm64", "") == "Darwin 25.0.0 (arm64)"
    assert system_name("Linux", "6.8.0", "x86_64", "") == "Linux 6.8.0 (x86_64)"


def test_the_log_file_has_every_member_of_its_port() -> None:
    members = {name for name in vars(ProgramLog) if not name.startswith("_")}
    assert members == {"last_lines"}
    assert members <= set(dir(ProgramLogFile))
