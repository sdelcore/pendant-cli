"""Bluetooth commands: pair, connect, disconnect, forget, status, scan."""

import asyncio

import click

from pendant.core.bluetooth import (
    pair_device,
    connect_device,
    disconnect_device,
    forget_device,
    print_bt_status,
)
from pendant.core.client import backend_name, create_client
from pendant.core.config import DEFAULT_PENDANT_ADDRESS, AUDIO_SERVICE_UUID

_NO_BLUEZ = (
    "Not needed with the Bleak backend (macOS): the connection is opened per command and "
    "bonding is handled by the OS. Use 'pendant bt pair' once to bond, and remove the "
    "Pendant from System Settings > Bluetooth if you ever need to forget it."
)


@click.group()
def bt():
    """Bluetooth pairing and connection commands."""
    pass


@bt.command()
@click.pass_context
def pair(ctx):
    """Pair and bond with the pendant (required first time)."""
    address = ctx.obj['address']
    if backend_name() == "bleak":
        # The OS pairs when the Pendant rejects an unencrypted write; the Pendant must be
        # in pairing mode (blue LED). Any command works, status is harmless.
        client = create_client(address)
        if not client.connect():
            raise click.ClickException("Failed to connect to device")
        try:
            client.send_command("get_device_status")
            client.run_for(2)
        finally:
            client.disconnect()
        click.echo("\nPaired and bonded.")
        return
    if not pair_device(address):
        raise click.ClickException("Pairing failed")


@bt.command()
@click.pass_context
def connect(ctx):
    """Connect to an already-paired pendant."""
    address = ctx.obj['address']
    if backend_name() == "bleak":
        click.echo(_NO_BLUEZ)
        return
    if not connect_device(address):
        raise click.ClickException("Connection failed")


@bt.command()
@click.pass_context
def disconnect(ctx):
    """Disconnect from pendant (keeps pairing)."""
    address = ctx.obj['address']
    if backend_name() == "bleak":
        click.echo(_NO_BLUEZ)
        return
    disconnect_device(address)


@bt.command()
@click.pass_context
def forget(ctx):
    """Remove pairing completely."""
    address = ctx.obj['address']
    if backend_name() == "bleak":
        click.echo(_NO_BLUEZ)
        return
    forget_device(address)


@bt.command()
@click.pass_context
def status(ctx):
    """Check Bluetooth connection status."""
    address = ctx.obj['address']
    if backend_name() == "bleak":
        click.echo(_NO_BLUEZ)
        return
    print_bt_status(address)


@bt.command()
@click.option('--all', '-a', 'show_all', is_flag=True, help='Show all BLE devices')
@click.option('--time', '-t', 'duration', default=10.0, help='Scan duration in seconds')
def scan(show_all, duration):
    """Scan for BLE devices and find pendants."""
    asyncio.run(_scan_for_devices(duration, show_all))


async def _scan_for_devices(duration: float, show_all: bool):
    """Scan for BLE devices and highlight Pendant devices."""
    from bleak import BleakScanner

    click.echo(f"Scanning for BLE devices ({duration}s)...")
    click.echo("-" * 70)

    devices = await BleakScanner.discover(timeout=duration, return_adv=True)

    if not devices:
        click.echo("No BLE devices found.")
        return

    pendant_devices = []
    other_devices = []

    for addr, (device, adv) in devices.items():
        name = device.name or adv.local_name or "Unknown"
        rssi = adv.rssi if adv else None

        # Check if this is a Pendant
        is_pendant = False
        reason = ""

        # Check by known MAC address
        if addr.upper() == DEFAULT_PENDANT_ADDRESS.upper():
            is_pendant = True
            reason = "known address"
        # Check by name
        elif name and "pendant" in name.lower():
            is_pendant = True
            reason = "name match"
        # Check by service UUID
        elif adv and AUDIO_SERVICE_UUID.lower() in [str(u).lower() for u in (adv.service_uuids or [])]:
            is_pendant = True
            reason = "service UUID"

        device_info = {
            "address": addr,
            "name": name,
            "rssi": rssi,
            "is_pendant": is_pendant,
            "reason": reason,
        }

        if is_pendant:
            pendant_devices.append(device_info)
        else:
            other_devices.append(device_info)

    # Display Pendant devices first
    if pendant_devices:
        click.echo("\nPendant devices found:")
        for d in pendant_devices:
            rssi_str = f" (RSSI: {d['rssi']})" if d['rssi'] else ""
            click.echo(f"  * {d['address']} - {d['name']}{rssi_str}")
            click.echo(f"    Detected by: {d['reason']}")
    else:
        click.echo("\nNo Pendant devices found.")

    # Display other devices if requested
    if show_all and other_devices:
        click.echo(f"\nOther BLE devices ({len(other_devices)}):")
        for d in sorted(other_devices, key=lambda x: x['rssi'] or -100, reverse=True):
            rssi_str = f" (RSSI: {d['rssi']})" if d['rssi'] else ""
            click.echo(f"    {d['address']} - {d['name']}{rssi_str}")
