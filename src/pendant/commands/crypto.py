"""Crypto commands: keygen, setkey."""

import click

from pendant.core.config import KEYS_DIR
from pendant.core.client import create_client
from pendant.core.protocol import generate_keypair


@click.group()
def crypto():
    """Encryption key management commands."""
    pass


@crypto.command()
def keygen():
    """Generate a new X25519 keypair for encryption."""
    private_file, public_file = generate_keypair()

    if private_file and public_file:
        click.echo("Generated new X25519 keypair:")
        click.echo(f"  Private: {private_file}")
        click.echo(f"  Public:  {public_file}")

        public_key_bytes = public_file.read_bytes()
        click.echo(f"\nPublic key (hex): {public_key_bytes.hex()}")
        click.echo("\nNext: Run 'pendant crypto setkey' to send public key to device")
    else:
        raise click.ClickException("Failed to generate keypair")


@crypto.command()
@click.pass_context
def setkey(ctx):
    """Send our public key to the device."""
    address = ctx.obj['address']
    public_file = KEYS_DIR / "public.key"

    if not public_file.exists():
        raise click.ClickException("No public key found. Run 'pendant crypto keygen' first.")

    public_key_bytes = public_file.read_bytes()
    click.echo(f"Sending public key to device: {public_key_bytes.hex()[:32]}...")

    client = create_client(address)
    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    client.send_command("set_server_public_key", public_key=public_key_bytes)

    client.run_for(2)
    client.disconnect()

    click.echo("\nPublic key sent to device.")
    click.echo("The device may encrypt new recordings with this key. On firmware 1.1.20 "
               "(after a factory reset) audio was observed to stay unencrypted, so verify "
               "with 'pendant download' before relying on it.")
