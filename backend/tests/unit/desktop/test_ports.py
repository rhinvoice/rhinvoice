"""Ports for the database and the web interface."""

import socket
from collections.abc import Iterator

import pytest

from rhinvoice.desktop.ports import PortInUseError, free_port, require_free
from tests.helpers import raises_exactly


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


def test_a_port_another_program_listens_on_is_refused(taken: int) -> None:
    message = f'port {taken} is in use by another program; set another "port" in rhinvoice.json'
    with raises_exactly(PortInUseError, message):
        require_free(taken)


def test_a_free_port_is_accepted() -> None:
    require_free(free_port())
