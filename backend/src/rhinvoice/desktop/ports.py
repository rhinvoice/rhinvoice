"""Ports on 127.0.0.1 for the database and the web interface."""

from __future__ import annotations

import socket

CONNECT_SECONDS = 1.0


class PortInUseError(Exception):
    """Another program listens on the port of the web interface."""


def free_port() -> int:
    """Find a port on 127.0.0.1 that nothing listens on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def require_free(port: int) -> None:
    """Refuse a port that another program listens on, before the browser would open that one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(CONNECT_SECONDS)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            msg = f'port {port} is in use by another program; set another "port" in rhinvoice.json'
            raise PortInUseError(msg)
