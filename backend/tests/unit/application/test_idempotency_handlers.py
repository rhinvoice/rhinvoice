"""A request with an Idempotency-Key runs once; a repeat gets what the first got (ADR 0041)."""

from datetime import timedelta
from uuid import UUID

import pytest

from rhinvoice.application.idempotency.handlers import IdempotencyHandlers
from rhinvoice.domain.idempotency.request import (
    KEEP,
    MAX_STORED_BODY,
    UNFINISHED_AFTER,
    KeyState,
    Verdict,
    fingerprint,
)
from rhinvoice.domain.shared.clock import FixedClock
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store

ANNA = UUID(int=1)
BEN = UUID(int=2)
KEY = UUID(int=10)
CREATE = fingerprint("POST", "/api/documents", "", b'{"type":"invoice"}')
OTHER = fingerprint("POST", "/api/documents", "", b'{"type":"quote"}')


@pytest.fixture
def handlers(store: Store, clock: FixedClock) -> IdempotencyHandlers:
    return IdempotencyHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


def test_the_first_request_runs_and_its_answer_is_given_to_a_repeat(
    handlers: IdempotencyHandlers, store: Store
) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    assert store.idempotency[ANNA, KEY].state is KeyState.RUNNING
    assert store.idempotency[ANNA, KEY].started_at == NOW
    handlers.succeed(ANNA, KEY, 201, b'{"id":"1"}')

    repeat = handlers.begin(ANNA, KEY, CREATE)
    assert repeat is not None
    assert repeat.verdict is Verdict.REPLAY
    assert repeat.stored.status_code == 201
    assert repeat.stored.body == b'{"id":"1"}'


def test_a_repeat_while_the_first_runs_is_told_so(handlers: IdempotencyHandlers) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    repeat = handlers.begin(ANNA, KEY, CREATE)
    assert repeat is not None
    assert repeat.verdict is Verdict.IN_PROGRESS


def test_a_request_cut_off_before_its_answer_stays_unclear(
    handlers: IdempotencyHandlers, clock: FixedClock
) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    clock.set(NOW + UNFINISHED_AFTER)
    repeat = handlers.begin(ANNA, KEY, CREATE)
    assert repeat is not None
    assert repeat.verdict is Verdict.UNFINISHED


def test_a_failed_request_frees_its_key_for_the_corrected_one(
    handlers: IdempotencyHandlers, store: Store
) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    handlers.fail(ANNA, KEY)
    assert (ANNA, KEY) not in store.idempotency
    assert handlers.begin(ANNA, KEY, OTHER) is None


def test_the_key_of_another_request_is_refused(handlers: IdempotencyHandlers) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    handlers.succeed(ANNA, KEY, 201, b"{}")
    repeat = handlers.begin(ANNA, KEY, OTHER)
    assert repeat is not None
    assert repeat.verdict is Verdict.REUSED


def test_keys_belong_to_their_user(handlers: IdempotencyHandlers) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    handlers.succeed(ANNA, KEY, 201, b'{"id":"1"}')
    # The same key of another user is a request of its own: it runs.
    assert handlers.begin(BEN, KEY, CREATE) is None


def test_a_large_answer_is_not_kept(handlers: IdempotencyHandlers, store: Store) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    handlers.succeed(ANNA, KEY, 200, b"x" * (MAX_STORED_BODY + 1))
    assert store.idempotency[ANNA, KEY].body is None
    repeat = handlers.begin(ANNA, KEY, CREATE)
    assert repeat is not None
    assert repeat.verdict is Verdict.DONE


def test_an_answer_of_the_largest_size_is_kept(handlers: IdempotencyHandlers, store: Store) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    handlers.succeed(ANNA, KEY, 200, b"x" * MAX_STORED_BODY)
    assert store.idempotency[ANNA, KEY].body == b"x" * MAX_STORED_BODY


def test_an_answer_without_a_body_to_keep(handlers: IdempotencyHandlers, store: Store) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    handlers.succeed(ANNA, KEY, 200, None)
    assert store.idempotency[ANNA, KEY].state is KeyState.DONE
    assert store.idempotency[ANNA, KEY].status_code == 200
    assert store.idempotency[ANNA, KEY].body is None


def test_keys_are_kept_for_a_week_and_forgotten_after(
    handlers: IdempotencyHandlers, clock: FixedClock
) -> None:
    assert handlers.begin(ANNA, KEY, CREATE) is None
    handlers.succeed(ANNA, KEY, 201, b'{"id":"1"}')
    clock.set(NOW + KEEP)
    repeat = handlers.begin(ANNA, KEY, CREATE)
    assert repeat is not None
    assert repeat.verdict is Verdict.REPLAY
    clock.set(NOW + KEEP + timedelta(microseconds=1))
    # Older than a week, the key is gone: the request would run again.
    assert handlers.begin(ANNA, KEY, CREATE) is None


def test_each_step_is_committed_on_its_own(handlers: IdempotencyHandlers, store: Store) -> None:
    handlers.begin(ANNA, KEY, CREATE)
    assert (ANNA, KEY) in store.idempotency
    handlers.succeed(ANNA, KEY, 201, b"{}")
    assert store.idempotency[ANNA, KEY].state is KeyState.DONE
