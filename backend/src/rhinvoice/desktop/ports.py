"""Ports on 127.0.0.1 for the database and the web interface."""

from __future__ import annotations

import socket

CONNECT_SECONDS = 1.0


def free_port() -> int:
    """Find a port on 127.0.0.1 that nothing listens on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def listening(port: int) -> bool:
    """Tell whether a program listens on this port of 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(CONNECT_SECONDS)
        return probe.connect_ex(("127.0.0.1", port)) == 0
