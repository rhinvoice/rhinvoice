"""What a problem report carries: the version, the system and the end of the log."""

from rhinvoice.application.support.handlers import (
    LOG_LINES,
    Installation,
    SupportHandlers,
    SupportReport,
)


class Log:
    def __init__(self) -> None:
        self.asked: list[int] = []

    def last_lines(self, count: int) -> str:
        self.asked.append(count)
        return "INFO: Application startup complete."


def test_the_program_for_windows_and_mac_reports_the_end_of_its_log() -> None:
    log = Log()
    report = SupportHandlers("0.7.4", "Windows 11 (AMD64)", log).report()
    assert report == SupportReport(
        version="0.7.4",
        system="Windows 11 (AMD64)",
        installation=Installation.DESKTOP,
        log="INFO: Application startup complete.",
    )
    assert log.asked == [LOG_LINES]


def test_a_server_keeps_its_log_with_docker() -> None:
    report = SupportHandlers("0.7.4", "Linux 6.8 (x86_64)", None).report()
    assert report.installation is Installation.SERVER
    assert report.log is None
