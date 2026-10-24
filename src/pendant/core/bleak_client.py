"""Bleak backend (macOS, and Linux without D-Bus) with the same blocking API as DBusClient.

A private asyncio loop runs in a background thread; the public methods are synchronous so the
CLI commands can use either backend interchangeably.
"""

import asyncio
import threading
import time
from typing import Optional, Callable

import click

from .config import (
    DEFAULT_PENDANT_ADDRESS,
    CONTROL_UUID,
    AUDIO_DATA_UUID,
    AUDIO_SERVICE_UUID,
)
from .protocol import PendantProtocol
from .response_handler import ResponseHandlerMixin

BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# ATT errors the Pendant returns until the link is encrypted (bonded).
_ATT_INSUFFICIENT_AUTHENTICATION = 5
_ATT_INSUFFICIENT_ENCRYPTION = 15
_WRITE_ATTEMPTS = 3
_WRITE_RETRY_DELAY_S = 3.0


class BondRequiredError(click.ClickException):
    """The Pendant refused the write because the link is not bonded."""

    def __init__(self):
        super().__init__(
            "The Pendant requires a bonded (encrypted) link and pairing did not complete.\n"
            "Put it in pairing mode (LED blue: factory reset = press+release, then quickly "
            "press+hold until the purple light goes out), keep your phone's Bluetooth off, "
            "and try again."
        )


class BleakBackend(ResponseHandlerMixin):
    """Synchronous facade over bleak."""

    def __init__(self, address: Optional[str] = DEFAULT_PENDANT_ADDRESS):
        self.address = address
        self.protocol = PendantProtocol()
        self.on_response: Optional[Callable] = None
        self.private_key = None  # For decryption
        self.mtu = 23

        # Audio collection
        self.opus_data = bytearray()
        self.pcm_data = bytearray()
        self.encrypted_data = bytearray()
        self.page_count = 0
        self.responses = []
        self.page_timestamps = []
        self._status_printed = False
        self._info_printed = False

        self._client = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ plumbing

    def _start_loop(self):
        if self._loop is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def _run(self, coro, timeout: float = 60.0):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _on_notification(self, _sender, data: bytearray):
        payload = self.protocol.parse_ble_message(bytes(data))
        if payload:
            response = self.protocol.parse_response(payload)
            if response:
                self._handle_response(response)

    # ------------------------------------------------------------------ connection

    async def _find_device(self):
        from bleak import BleakScanner

        label = self.address or "any Pendant"
        print(f"Scanning for {label}...")
        found = await BleakScanner.discover(timeout=10.0, return_adv=True)
        for addr, (dev, adv) in found.items():
            if self.address:
                if addr.upper() == self.address.upper():
                    return dev
            else:
                uuids = [str(u).lower() for u in (adv.service_uuids or [])]
                if AUDIO_SERVICE_UUID in uuids or (dev.name or adv.local_name or "") == "Pendant":
                    self.address = addr
                    print(f"Found Pendant: {addr}")
                    return dev
        return None

    async def _connect(self) -> bool:
        from bleak import BleakClient as BC

        device = await self._find_device()
        if device is None:
            print("Device not found. Make sure it is awake and not connected elsewhere.")
            return False

        self._client = BC(device, timeout=20.0)
        await self._client.connect()
        if not self._client.is_connected:
            print("Failed to connect!")
            return False

        try:
            self.mtu = self._client.mtu_size
            print(f"MTU: {self.mtu} bytes")
        except Exception:
            print("MTU: default")

        await self._client.start_notify(AUDIO_DATA_UUID, self._on_notification)
        return True

    def connect(self) -> bool:
        """Scan, connect and subscribe to notifications."""
        self._start_loop()
        try:
            return self._run(self._connect(), timeout=60.0)
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    # ------------------------------------------------------------------ commands

    async def _write(self, data: bytes):
        from bleak.exc import BleakGATTProtocolError

        for attempt in range(1, _WRITE_ATTEMPTS + 1):
            try:
                # Writes WITH response: this is what makes macOS start pairing when the
                # Pendant answers "insufficient encryption/authentication".
                await self._client.write_gatt_char(CONTROL_UUID, data, response=True)
                return
            except BleakGATTProtocolError as e:
                needs_bond = int(e.args[0]) in (_ATT_INSUFFICIENT_AUTHENTICATION, _ATT_INSUFFICIENT_ENCRYPTION)
                if not needs_bond:
                    raise
                if attempt == _WRITE_ATTEMPTS:
                    raise BondRequiredError() from e
                print(f"Link not encrypted yet (pairing in progress), retry {attempt}/{_WRITE_ATTEMPTS - 1}...")
                await asyncio.sleep(_WRITE_RETRY_DELAY_S)

    def send_command(self, cmd_type: str, **kwargs):
        """Send a command to the pendant."""
        cmd = self.protocol.create_command(cmd_type, **kwargs)
        self._run(self._write(cmd))

    def read_battery(self) -> Optional[int]:
        """Battery percentage from the standard BLE Battery Service."""
        async def _read():
            data = await self._client.read_gatt_char(BATTERY_LEVEL_UUID)
            return int(data[0])
        try:
            return self._run(_read(), timeout=10.0)
        except Exception:
            return None

    # ------------------------------------------------------------------ waiting

    def run_for(self, seconds: float, idle_stop: Optional[float] = None):
        """Receive notifications for up to ``seconds``.

        Returns early if stop() is called, or, when ``idle_stop`` is set, once at least one
        page has arrived and no new page was seen for ``idle_stop`` seconds.
        """
        self._stop.clear()
        deadline = time.monotonic() + seconds
        last_pages = self.page_count
        last_change = time.monotonic()
        while time.monotonic() < deadline and not self._stop.is_set():
            time.sleep(0.2)
            if self.page_count != last_pages:
                last_pages = self.page_count
                last_change = time.monotonic()
            elif idle_stop and self.page_count > 0 and time.monotonic() - last_change >= idle_stop:
                break

    def stop(self):
        """Wake run_for() early."""
        self._stop.set()

    def disconnect(self):
        """Unsubscribe, disconnect and stop the background loop."""
        if self._loop is None:
            return

        async def _close():
            if self._client and self._client.is_connected:
                try:
                    await self._client.stop_notify(AUDIO_DATA_UUID)
                except Exception:
                    pass
                await self._client.disconnect()

        try:
            self._run(_close(), timeout=15.0)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None
