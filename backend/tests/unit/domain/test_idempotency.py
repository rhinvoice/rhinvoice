"""A request repeated with the same Idempotency-Key runs once (ADR 0041)."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.idempotency.request import (
    KEEP,
    MAX_STORED_BODY,
    UNFINISHED_AFTER,
    Fingerprint,
    KeyState,
    StoredRequest,
    Verdict,
    fingerprint,
    judge,
)

STARTED = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
REQUEST = fingerprint("POST", "/api/documents", "", b'{"type":"invoice"}')


def test_a_fingerprint_names_method_address_and_body() -> None:
    assert len(REQUEST) == 64
    assert fingerprint("post", "/api/documents", "", b'{"type":"invoice"}') == REQUEST
    others = {
        fingerprint("PUT", "/api/documents", "", b'{"type":"invoice"}'),
        fingerprint("POST", "/api/customers", "", b'{"type":"invoice"}'),
        fingerprint("POST", "/api/documents", "type=quote", b'{"type":"invoice"}'),
        fingerprint("POST", "/api/documents", "", b'{"type":"quote"}'),
    }
    assert REQUEST not in others
    assert len(others) == 4


@given(st.text(), st.text())
def test_parts_of_a_request_cannot_be_shifted_into_each_other(first: str, second: str) -> None:
    # "/a" + "b" and "/ab" + "" must differ: each part is counted with its length.
    if first + second and second:
        assert fingerprint("POST", first, second, b"") != fingerprint(
            "POST", first + second, "", b""
        )


def done(body: bytes | None) -> StoredRequest:
    return StoredRequest(REQUEST, KeyState.DONE, STARTED, 201, body)


def test_a_repeat_of_a_done_request_gets_its_response() -> None:
    assert judge(done(b'{"id":"1"}'), REQUEST, STARTED + KEEP) is Verdict.REPLAY


def test_a_repeat_of_a_done_request_without_its_large_response_is_refused() -> None:
    assert judge(done(None), REQUEST, STARTED) is Verdict.DONE


def test_the_same_key_for_another_request_is_refused_whatever_its_state() -> None:
    other = fingerprint("POST", "/api/documents", "", b'{"type":"quote"}')
    assert judge(done(b"{}"), other, STARTED) is Verdict.REUSED
    running = StoredRequest(REQUEST, KeyState.RUNNING, STARTED)
    assert judge(running, other, STARTED) is Verdict.REUSED


@pytest.mark.parametrize(
    ("after", "verdict"),
    [
        (timedelta(0), Verdict.IN_PROGRESS),
        (UNFINISHED_AFTER - timedelta(microseconds=1), Verdict.IN_PROGRESS),
        (UNFINISHED_AFTER, Verdict.UNFINISHED),
        (UNFINISHED_AFTER + timedelta(hours=1), Verdict.UNFINISHED),
    ],
)
def test_a_running_request_is_waited_for_until_it_counts_as_cut_off(
    after: timedelta, verdict: Verdict
) -> None:
    running = StoredRequest(REQUEST, KeyState.RUNNING, STARTED)
    assert judge(running, REQUEST, STARTED + after) is verdict


def test_the_limits_follow_the_decision() -> None:
    # ADR 0041: a weekend with the page open, a cut-off request, the largest kept answer.
    assert timedelta(days=7) == KEEP
    assert timedelta(minutes=10) == UNFINISHED_AFTER
    assert MAX_STORED_BODY == 1024 * 1024


@given(st.binary(), st.integers(min_value=0, max_value=64))
def test_a_body_added_in_parts_gives_the_fingerprint_of_the_whole(body: bytes, cut: int) -> None:
    parts = Fingerprint("POST", "/api/documents/1/files", "")
    parts.update(body[:cut])
    parts.update(body[cut:])
    assert parts.hexdigest() == fingerprint("POST", "/api/documents/1/files", "", body)
