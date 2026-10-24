"""Audio commands: download, decode, record, stop."""

import json
from datetime import datetime
from pathlib import Path

import click

from pendant.core.config import MIN_VALID_TIMESTAMP_MS
from pendant.core.client import create_client
from pendant.core.protocol import load_private_key
from pendant.core.opus import decode_opus_file


@click.command()
@click.option('--decode', '-d', is_flag=True, help='Auto-decode opus to WAV')
@click.option('--output', '-o', type=click.Path(), default='.', help='Output directory')
@click.option('--timeout', '-t', default=120, show_default=True,
              help='Maximum seconds to keep receiving pages')
@click.option('--idle', default=15, show_default=True,
              help='Stop after this many seconds without new pages (Bleak backend only)')
@click.pass_context
def download(ctx, decode, output, timeout, idle):
    """Download stored recordings from the pendant."""
    address = ctx.obj['address']
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = create_client(address)

    # Try to load private key for decryption
    client.private_key = load_private_key()
    if client.private_key:
        click.echo("Loaded encryption key for decryption")

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo("\nSyncing time...")
    client.send_command("set_current_time")

    client.run_for(2)

    click.echo("\nDownloading audio (this may take a while)...")
    client.send_command("download_flash_pages", batch=True, realtime=False)
    client.run_for(max(timeout - 2, 1), idle_stop=idle)
    client.disconnect()

    # Save audio
    click.echo(f"\n\nDownload complete!")
    click.echo(f"  Pages: {client.page_count}")
    click.echo(f"  Opus: {len(client.opus_data)} bytes")
    click.echo(f"  PCM: {len(client.pcm_data)} bytes")
    if client.encrypted_data:
        click.echo(f"  Encrypted: {len(client.encrypted_data)} bytes (could not decrypt)")

    # Determine filename from first page's recording timestamp (if available)
    recording_start_ms = None
    if client.page_timestamps:
        # Find first page with a valid real-world timestamp
        for page_info in client.page_timestamps:
            ts = page_info.get("absolute_timestamp_ms", 0)
            if ts > MIN_VALID_TIMESTAMP_MS:
                recording_start_ms = ts
                break

    if recording_start_ms:
        # Use recording start time for filename
        recording_dt = datetime.fromtimestamp(recording_start_ms / 1000)
        timestamp = recording_dt.strftime('%Y%m%d_%H%M%S')
    else:
        # Fallback to download time (pendant wasn't time-synced)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    opus_fname = None

    if client.opus_data:
        opus_fname = output_dir / f"pendant_{timestamp}.opus"
        opus_fname.write_bytes(client.opus_data)
        click.echo(f"\nSaved: {opus_fname}")

    if client.pcm_data:
        fname = output_dir / f"pendant_{timestamp}.raw"
        fname.write_bytes(client.pcm_data)
        click.echo(f"Saved: {fname}")
        click.echo(f"  Convert: ffmpeg -f s16le -ar 16000 -ac 1 -i {fname} output.wav")

    if client.encrypted_data:
        fname = output_dir / f"pendant_{timestamp}.enc"
        fname.write_bytes(client.encrypted_data)
        click.echo(f"Saved encrypted: {fname}")
        click.echo("  To decrypt, run 'pendant crypto keygen' then 'pendant crypto setkey', then re-record and download")

    # Save timestamp metadata as JSON sidecar
    if client.page_timestamps and client.opus_data:
        # Check if timestamps are real (synced) or just device uptime
        first_ts = client.page_timestamps[0].get("absolute_timestamp_ms", 0) if client.page_timestamps else 0
        timestamps_synced = first_ts > MIN_VALID_TIMESTAMP_MS

        metadata = {
            "recording_start_ms": recording_start_ms,
            "recording_start_iso": datetime.fromtimestamp(recording_start_ms / 1000).isoformat() if recording_start_ms else None,
            "download_time_iso": datetime.now().isoformat(),
            "timestamps_synced": timestamps_synced,
            "total_pages": client.page_count,
            "total_audio_bytes": len(client.opus_data),
            "pages": client.page_timestamps
        }
        json_fname = output_dir / f"pendant_{timestamp}.json"
        json_fname.write_text(json.dumps(metadata, indent=2))
        click.echo(f"Saved metadata: {json_fname}")

    # Auto-decode opus to WAV if requested
    if decode and opus_fname and opus_fname.exists():
        wav_fname = opus_fname.with_suffix('.wav')
        click.echo(f"\nDecoding to WAV...")
        try:
            if decode_opus_file(str(opus_fname), str(wav_fname)):
                click.echo(f"Decoded: {wav_fname}")
        except Exception as e:
            click.echo(f"Decode failed: {e}")
            click.echo(f"  Manual: pendant decode {opus_fname}")
    elif opus_fname and not decode:
        click.echo(f"  Decode: pendant decode {opus_fname}")


@click.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.argument('output_file', type=click.Path(), required=False)
@click.option('--verbose', '-v', is_flag=True, help='Show detailed frame info')
def decode(input_file, output_file, verbose):
    """Decode raw Opus file to WAV."""
    if output_file is None:
        output_file = input_file.replace('.opus', '.wav')
        if output_file == input_file:
            output_file = input_file + '.wav'

    success = decode_opus_file(input_file, output_file, verbose=verbose)
    if not success:
        raise click.ClickException("Decoding failed")


@click.command()
@click.pass_context
def record(ctx):
    """Start recording on the pendant."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo("\nStarting recording...")
    client.send_command("start_recording")

    client.run_for(2)
    client.disconnect()
    click.echo("Recording started (if device supports remote start)")


@click.command()
@click.pass_context
def stop(ctx):
    """Stop recording on the pendant."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo("\nStopping recording...")
    client.send_command("stop_recording")

    client.run_for(2)
    client.disconnect()
    click.echo("Recording stopped")


@click.command()
@click.pass_context
def clear(ctx):
    """Clear all recordings from device storage."""
    address = ctx.obj['address']
    client = create_client(address)

    if not client.connect():
        raise click.ClickException("Failed to connect to device")

    click.echo("\nClearing device storage...")
    client.send_command("clear_storage")

    client.run_for(2)
    client.disconnect()
    click.echo("Storage cleared!")
