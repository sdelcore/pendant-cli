"""Settings commands: LED, VAD threshold, device name, WiFi."""

import click

from pendant.core.client import create_client


@click.group()
def settings():
    """Device settings commands."""
    pass


@settings.command()
@click.argument('state', type=int)
@click.pass_context
def led(ctx, state):
    """Set LED state.
    
    STATE is an integer value:
      0 = Off
      1 = On (default behavior)
      
    The exact behavior depends on device firmware.
    """
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo(f"\nSetting LED state to {state}...")
    client.send_command("set_led", state=state)

    client.run_for(2)
    client.disconnect()
    click.echo("LED state set")


@settings.command()
@click.argument('brightness', type=click.IntRange(0, 100))
@click.pass_context
def brightness(ctx, brightness):
    """Set LED brightness (0-100)."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo(f"\nSetting LED brightness to {brightness}%...")
    client.send_command("set_led_brightness", brightness=brightness)

    client.run_for(2)
    client.disconnect()
    click.echo("LED brightness set")


@settings.command()
@click.argument('threshold', type=click.FloatRange(0.0, 1.0))
@click.pass_context
def vad(ctx, threshold):
    """Set Voice Activity Detection threshold (0.0-1.0).
    
    Lower values = more sensitive (detects quieter sounds).
    Higher values = less sensitive (requires louder sounds).
    
    Typical values:
      0.3 = High sensitivity
      0.5 = Default/balanced
      0.7 = Low sensitivity
    """
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo(f"\nSetting VAD threshold to {threshold}...")
    client.send_command("set_vad_threshold", threshold=threshold)

    client.run_for(2)
    client.disconnect()
    click.echo("VAD threshold set")


@settings.command()
@click.argument('name')
@click.pass_context
def name(ctx, name):
    """Set the device name."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo(f"\nSetting device name to '{name}'...")
    client.send_command("set_device_name", name=name)

    client.run_for(2)
    client.disconnect()
    click.echo("Device name set")


@settings.command()
@click.argument('ssid')
@click.argument('password')
@click.pass_context
def wifi_add(ctx, ssid, password):
    """Add WiFi credentials to the device."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo(f"\nAdding WiFi credentials for '{ssid}'...")
    client.send_command("add_wifi_credentials", ssid=ssid, password=password)

    client.run_for(2)
    client.disconnect()
    click.echo("WiFi credentials added")


@settings.command()
@click.argument('ssid')
@click.pass_context
def wifi_connect(ctx, ssid):
    """Connect to a previously configured WiFi network."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo(f"\nConnecting to WiFi '{ssid}'...")
    client.send_command("connect_to_wifi", ssid=ssid)

    client.run_for(5)
    client.disconnect()
    click.echo("WiFi connection initiated")


@settings.command()
@click.pass_context
def wifi_disconnect(ctx):
    """Disconnect from WiFi."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo("\nDisconnecting from WiFi...")
    client.send_command("disconnect_wifi")

    client.run_for(2)
    client.disconnect()
    click.echo("WiFi disconnected")
