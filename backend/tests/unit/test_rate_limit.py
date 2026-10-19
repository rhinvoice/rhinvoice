from rhinvoice.api.rate_limit import MAX_CLIENTS, ClientLimits, RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_client_gets_its_limit_per_window() -> None:
    clock = Clock()
    limiter = RateLimiter(2, 60, clock)
    assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]
    # Others are counted on their own.
    assert limiter.allow("b")
    clock.now += 59.9
    assert not limiter.allow("a")
    clock.now += 0.1
    assert limiter.allow("a")


def test_many_clients_do_not_fill_the_memory() -> None:
    clock = Clock()
    limiter = RateLimiter(1, 60, clock)
    for client in range(MAX_CLIENTS):
        limiter.allow(str(client))
    clock.now += 60
    assert limiter.allow("new")
    # The expired clients are forgotten.
    assert limiter.clients == 1
    clock.now += 1
    assert not limiter.allow("new")


def test_the_demo_limits() -> None:
    limits = ClientLimits.default(demo=True)
    assert all(limits.logins.allow("a") for _ in range(10))
    assert not limits.logins.allow("a")
    assert limits.changes is not None
    assert all(limits.changes.allow("a") for _ in range(60))
    assert not limits.changes.allow("a")


def test_every_installation_limits_sign_ins_but_not_changes() -> None:
    limits = ClientLimits.default()
    assert all(limits.logins.allow("a") for _ in range(10))
    assert not limits.logins.allow("a")
    assert limits.changes is None
