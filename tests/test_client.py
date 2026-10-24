"""Tests for backend selection and the Bleak backend's blocking helpers (no BLE hardware)."""

import threading
import time

import pytest

from pendant.core import client as client_module
from pendant.core.bleak_client import BleakBackend, BondRequiredError
from pendant.core.response_handler import ResponseHandlerMixin


class TestBackendSelection:
    def test_env_forces_bleak(self, monkeypatch):
        monkeypatch.setenv("PENDANT_BACKEND", "bleak")
        assert client_module.backend_name() == "bleak"
        assert isinstance(client_module.create_client("AA:BB"), BleakBackend)

    def test_env_forces_dbus(self, monkeypatch):
        monkeypatch.setenv("PENDANT_BACKEND", "dbus")
        assert client_module.backend_name() == "dbus"

    def test_non_linux_defaults_to_bleak(self, monkeypatch):
        monkeypatch.delenv("PENDANT_BACKEND", raising=False)
        monkeypatch.setattr(client_module.sys, "platform", "darwin")
        assert client_module.backend_name() == "bleak"

    def test_linux_without_dbus_falls_back_to_bleak(self, monkeypatch):
        monkeypatch.delenv("PENDANT_BACKEND", raising=False)
        monkeypatch.setattr(client_module.sys, "platform", "linux")
        monkeypatch.setattr(client_module, "_dbus_available", lambda: False)
        assert client_module.backend_name() == "bleak"


class TestBleakBackend:
    def test_shares_response_handler(self):
        assert issubclass(BleakBackend, ResponseHandlerMixin)

    def test_address_optional(self):
        assert BleakBackend(None).address is None

    def test_run_for_returns_after_timeout(self):
        c = BleakBackend("x")
        start = time.monotonic()
        c.run_for(0.5)
        assert 0.4 <= time.monotonic() - start < 2.0

    def test_stop_wakes_run_for(self):
        c = BleakBackend("x")
        threading.Timer(0.3, c.stop).start()
        start = time.monotonic()
        c.run_for(10)
        assert time.monotonic() - start < 2.0

    def test_idle_stop_needs_at_least_one_page(self):
        c = BleakBackend("x")
        start = time.monotonic()
        c.run_for(1.0, idle_stop=0.3)  # no pages yet: must wait the full timeout
        assert time.monotonic() - start >= 0.9

    def test_idle_stop_after_pages_stop_arriving(self):
        c = BleakBackend("x")
        c.page_count = 3
        start = time.monotonic()
        c.run_for(10, idle_stop=0.5)
        assert time.monotonic() - start < 3.0

    def test_disconnect_without_connect_is_noop(self):
        BleakBackend("x").disconnect()

    def test_bond_error_message_mentions_pairing_mode(self):
        assert "pairing mode" in BondRequiredError().format_message()
