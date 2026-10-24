"""Device commands: status, info, listen."""

import click

from pendant.core.client import create_client
from datetime import datetime


@click.command()
@click.pass_context
def status(ctx):
    """Get device status (recording, storage, battery)."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    # Get battery from standard BLE Battery Service (most reliable)
    battery = client.read_battery()
    if battery is not None:
        click.echo(f"\n  Battery: {battery}%")

    click.echo("\nGetting device status...")
    client.send_command("get_device_status")

    client.run_for(3)
    client.disconnect()


@click.command()
@click.pass_context
def info(ctx):
    """Get device information (firmware, hardware, serial)."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo("\nGetting device info...")
    client.send_command("get_device_info")

    client.run_for(3)
    client.disconnect()


@click.command()
@click.option('--timeout', '-t', default=60, help='Timeout in seconds (0 = indefinite)')
@click.pass_context
def listen(ctx, timeout):
    """Listen for device events (button presses, status updates).
    
    Press Ctrl+C to stop listening.
    """
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo("\nListening for device events...")
    click.echo("Press Ctrl+C to stop.\n")

    # Custom response handler for listening mode
    def on_event(response):
        rtype = response.get("type")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if rtype == "button_status":
            pressed = response.get("pressed", False)
            action = "pressed" if pressed else "released"
            click.echo(f"[{timestamp}] Button {action}")
        elif rtype == "battery_status":
            level = response.get("level", 0)
            charging = response.get("charging", False)
            status = "charging" if charging else "discharging"
            click.echo(f"[{timestamp}] Battery: {level}% ({status})")
        elif rtype == "device_status":
            recording = response.get("is_recording", False)
            storage = response.get("storage_used_percent", 0)
            click.echo(f"[{timestamp}] Status: recording={recording}, storage={storage}%")
        elif rtype and rtype != "parse_error":
            click.echo(f"[{timestamp}] Event: {rtype}")

    client.on_response = on_event

    try:
        client.run_for(timeout if timeout > 0 else 3600)
    except KeyboardInterrupt:
        click.echo("\nStopped listening.")
    finally:
        client.disconnect()
