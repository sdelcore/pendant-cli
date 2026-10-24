"""Backend selection: D-Bus/BlueZ on Linux, Bleak everywhere else."""

import os
import sys


def _dbus_available() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    try:
        import dbus  # noqa: F401
        from gi.repository import GLib  # noqa: F401
    except ImportError:
        return False
    return True


def backend_name() -> str:
    """'dbus' or 'bleak'. Override with PENDANT_BACKEND=dbus|bleak."""
    forced = os.environ.get("PENDANT_BACKEND", "").lower()
    if forced in ("dbus", "bleak"):
        return forced
    return "dbus" if _dbus_available() else "bleak"


def create_client(address=None):
    """Create a client for the current platform.

    Both backends expose: connect(), send_command(), run_for(), stop(), disconnect(),
    read_battery(), plus the audio buffers filled by the response handler.
    """
    if backend_name() == "dbus":
        from .dbus_client import DBusClient
        return DBusClient(address)
    from .bleak_client import BleakBackend
    return BleakBackend(address)
