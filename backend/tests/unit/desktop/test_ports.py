"""Ports for the database and the web interface."""

import socket
from collections.abc import Iterator

import pytest

from rhinvoice.desktop.ports import free_port, listening


def test_free_ports_can_be_bound() -> None:
    port = free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


@pytest.fixture
def taken() -> Iterator[int]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        yield listener.getsockname()[1]


def test_a_port_another_program_listens_on_is_noticed(taken: int) -> None:
    assert listening(taken)


def test_a_free_port_is_not_listened_on() -> None:
    assert not listening(free_port())
