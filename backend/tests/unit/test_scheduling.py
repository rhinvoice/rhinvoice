"""The background job of the web server."""

import threading

import pytest

from rhinvoice.infrastructure.scheduling import PeriodicJob


def test_the_job_runs_until_stopped() -> None:
    ran = threading.Event()
    calls: list[int] = []

    def job() -> None:
        calls.append(len(calls))
        if len(calls) == 3:
            ran.set()

    periodic = PeriodicJob(job, interval=0.01, first_delay=0.01, name="test job")
    periodic.start()
    assert ran.wait(5)
    periodic.stop()
    stopped_at = len(calls)
    assert stopped_at >= 3
    threading.Event().wait(0.05)
    assert len(calls) == stopped_at


def test_a_failing_run_is_logged_and_the_next_one_tries_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> None:
        msg = "database down"
        raise RuntimeError(msg)

    periodic = PeriodicJob(broken, interval=60, first_delay=60, name="recurring invoices")
    periodic.run_once()
    assert "recurring invoices failed; trying again later" in caplog.text
    assert "database down" in caplog.text
    # Never started: stopping returns at once.
    periodic.stop(timeout=0)
