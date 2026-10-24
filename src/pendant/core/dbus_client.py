"""D-Bus backend for communicating with already-connected pendant."""

import subprocess
from typing import Optional, Callable

from .config import DEFAULT_PENDANT_ADDRESS, CONTROL_UUID, AUDIO_DATA_UUID
from .protocol import PendantProtocol
from .bluetooth import ensure_connected
from .response_handler import ResponseHandlerMixin


class DBusClient(ResponseHandlerMixin):
    """D-Bus backend for communicating with already-connected pendant."""

    def __init__(self, address: str = DEFAULT_PENDANT_ADDRESS):
        self.address = address
        self.device_path = f"/org/bluez/hci0/dev_{address.replace(':', '_')}"
        self.protocol = PendantProtocol()
        self.bus = None
        self.ctrl_char = None
        self.data_char = None
        self.loop = None
        self.on_response: Optional[Callable] = None
        self.private_key = None  # For decryption
        self.mtu = 23  # Default BLE MTU, updated after connection

        # Audio collection
        self.opus_data = bytearray()
        self.pcm_data = bytearray()
        self.encrypted_data = bytearray()
        self.page_count = 0
        self.responses = []
        self.page_timestamps = []  # List of page_info dicts with timestamps
        self._status_printed = False  # Track if status already printed
        self._info_printed = False  # Track if info already printed

    def _init_dbus(self):
        """Initialize D-Bus connection."""
        import dbus
        import dbus.mainloop.glib

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()

    def _find_characteristic(self, uuid: str) -> Optional[str]:
        """Find GATT characteristic by UUID."""
        import dbus

        om = dbus.Interface(
            self.bus.get_object('org.bluez', '/'),
            'org.freedesktop.DBus.ObjectManager'
        )
        objects = om.GetManagedObjects()

        for path, interfaces in objects.items():
            if 'org.bluez.GattCharacteristic1' in interfaces:
                props = interfaces['org.bluez.GattCharacteristic1']
                if props.get('UUID', '').lower() == uuid.lower():
                    return path
        return None

    def _on_properties_changed(self, interface, changed, invalidated, path):
        """Handle D-Bus PropertiesChanged signal."""
        if interface == 'org.bluez.GattCharacteristic1' and 'Value' in changed:
            data = bytes(changed['Value'])
            payload = self.protocol.parse_ble_message(data)
            if payload:
                response = self.protocol.parse_response(payload)
                if response:
                    self._handle_response(response)

    def check_connection(self) -> bool:
        """Check if device is connected."""
        try:
            result = subprocess.run(
                ['bluetoothctl', 'info', self.address],
                capture_output=True, text=True, timeout=5
            )
            return 'Connected: yes' in result.stdout
        except Exception:
            return False

    def connect(self) -> bool:
        """Ensure device is connected and initialize D-Bus."""
        import dbus

        self._init_dbus()

        # Auto-connect if not connected
        if not ensure_connected(self.address):
            return False

        # Find characteristics
        ctrl_path = self._find_characteristic(CONTROL_UUID)
        data_path = self._find_characteristic(AUDIO_DATA_UUID)

        if not ctrl_path or not data_path:
            print("GATT characteristics not found. Device may need reconnection.")
            return False

        self.ctrl_char = dbus.Interface(
            self.bus.get_object('org.bluez', ctrl_path),
            'org.bluez.GattCharacteristic1'
        )
        self.data_char = dbus.Interface(
            self.bus.get_object('org.bluez', data_path),
            'org.bluez.GattCharacteristic1'
        )

        # Subscribe to notifications
        self.bus.add_signal_receiver(
            self._on_properties_changed,
            signal_name='PropertiesChanged',
            dbus_interface='org.freedesktop.DBus.Properties',
            path_keyword='path'
        )

        # Enable notifications
        try:
            self.data_char.StartNotify()
        except dbus.exceptions.DBusException as e:
            if 'Already notifying' not in str(e):
                print(f"Warning: {e}")

        # Query negotiated MTU via AcquireWrite
        try:
            import os
            fd, mtu = self.ctrl_char.AcquireWrite({})
            os.close(fd)  # We only need the MTU value
            self.mtu = int(mtu)
            print(f"MTU: {self.mtu} bytes")
        except Exception:
            # BlueZ negotiates MTU automatically
            print(f"MTU: BlueZ default")

        return True

    def send_command(self, cmd_type: str, **kwargs):
        """Send a command to the pendant."""
        import dbus

        cmd = self.protocol.create_command(cmd_type, **kwargs)
        self.ctrl_char.WriteValue(dbus.Array(cmd, signature='y'), {})

    def run_with_timeout(self, timeout_seconds: int = 60):
        """Run the GLib main loop with timeout."""
        from gi.repository import GLib

        self.loop = GLib.MainLoop()

        def stop():
            self.loop.quit()
            return False

        GLib.timeout_add_seconds(timeout_seconds, stop)
        self.loop.run()

    def run_for(self, seconds: int, idle_stop: Optional[int] = None):
        """Receive notifications for up to ``seconds`` (or until stop() is called).

        ``idle_stop`` is accepted for API parity with the Bleak backend and is ignored here.
        """
        self.run_with_timeout(seconds)

    def read_battery(self) -> Optional[int]:
        """Battery percentage from the standard BLE Battery Service."""
        return get_battery_from_dbus(self.address)

    def stop(self):
        """Stop the main loop."""
        if self.loop:
            self.loop.quit()

    def disconnect(self):
        """Clean up."""
        try:
            if self.data_char:
                self.data_char.StopNotify()
        except Exception:
            pass


def get_battery_from_dbus(address: str = DEFAULT_PENDANT_ADDRESS) -> Optional[int]:
    """Get battery percentage from standard BLE Battery Service via D-Bus."""
    try:
        import dbus
        bus = dbus.SystemBus()
        device_path = f"/org/bluez/hci0/dev_{address.replace(':', '_')}"
        device = bus.get_object('org.bluez', device_path)
        props = dbus.Interface(device, 'org.freedesktop.DBus.Properties')
        percentage = props.Get('org.bluez.Battery1', 'Percentage')
        return int(percentage)
    except Exception:
        return None
