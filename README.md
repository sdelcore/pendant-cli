# Pendant BLE Tools

Python tools for communicating with the Limitless Pendant device over Bluetooth Low Energy.

The protocol was reverse-engineered from the Limitless Android app (v2.1.6). Communication
uses Google Protocol Buffers over BLE GATT characteristics.

## Features

- Download recorded audio from the Pendant
- Real-time audio streaming
- Device status and info
- **Encryption key injection** - Set your own encryption key for future recordings
- Decode raw Opus audio to WAV

## Requirements

- Linux with BlueZ (bluetoothctl), or macOS (see [macOS](#macos))
- Python 3.10+
- Nix (recommended) or manual package installation

## Quick Start

```bash
# Enter the Nix development environment
nix develop

# Set your device address (use pendant bt scan to find it)
export PENDANT_ADDRESS="XX:XX:XX:XX:XX:XX"

# 1. Scan for the Pendant device
pendant bt scan

# 2. Pair with the device (required first time)
pendant bt pair

# 3. Check device status
pendant status

# 4. Download stored recordings and decode to WAV
pendant download -d

# 5. Decode a raw opus file to WAV
pendant decode recording.opus
```

## macOS

On macOS the CLI uses a [Bleak](https://github.com/hbldh/bleak) backend instead of D-Bus/BlueZ. The
backend is chosen automatically (override with `PENDANT_BACKEND=dbus|bleak`), `dbus-python` and
`PyGObject` are only installed on Linux, and `PENDANT_ADDRESS` is optional: without it the first
Pendant found is used. On macOS the address is a CoreBluetooth UUID, not a MAC address.

```bash
uv sync
protoc -I proto --python_out=proto proto/pendant.proto   # generate proto/pendant_pb2.py
brew install opus                                         # libopus, for `pendant decode`
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib       # if opuslib cannot find libopus

pendant bt scan
pendant bt pair      # first time only, Pendant in pairing mode
pendant status
pendant download -d -o recordings
```

Notes:

- **Bluetooth permission.** The terminal app running `pendant` needs Bluetooth access; a process
  without it aborts (SIGABRT) when CoreBluetooth starts.
- **Pairing.** macOS has no pairing API for BLE. It pairs automatically when the Pendant rejects an
  unencrypted write with "insufficient encryption", so the Bleak backend writes to the control
  characteristic *with response*. The Pendant only accepts a new bond in pairing mode (blue LED); a
  device still bonded to another phone answers `Pairing Failed reason=8` in the system log. See
  Limitless' guide to
  [LED colours](https://help.limitless.ai/en/articles/10542073-what-do-the-different-pendant-led-light-colors-mean)
  and [factory reset](https://help.limitless.ai/en/articles/10547401-how-do-i-factory-reset-my-pendant)
  (a reset deletes recordings that were not downloaded yet).
- `bt connect|disconnect|forget|status` wrap `bluetoothctl` and are no-ops with the Bleak backend.
- `pendant download` takes `--timeout` (seconds) and `--idle` (stop after N seconds without new
  pages, Bleak backend only).
- Tested on macOS with firmware `1.1.20`; the D-Bus backend was refactored but not re-tested.

## Commands

```bash
# Device
pendant status              # Battery, recording state, storage
pendant info                # Firmware, hardware, serial number

# Audio
pendant download            # Download stored recordings
pendant download -d         # Download and auto-decode to WAV
pendant decode file.opus    # Decode raw Opus to WAV
pendant record              # Start recording
pendant stop                # Stop recording

# Bluetooth
pendant bt scan             # Scan for BLE devices
pendant bt pair             # Pair and bond (required first time)
pendant bt connect          # Connect to paired device
pendant bt disconnect       # Disconnect (keeps pairing)
pendant bt status           # Check connection status

# Encryption
pendant crypto keygen       # Generate X25519 keypair
pendant crypto setkey       # Send public key to device

# Debug
pendant explore             # Explore GATT services
pendant debug               # Download with flash page inspection
```

## Device Address

Set the `PENDANT_ADDRESS` environment variable to your device's MAC address.
Use `pendant bt scan` to find it.

## Protocol Overview

Communication uses two BLE characteristics:

| UUID | Purpose | Direction |
|------|---------|-----------|
| `632de002-...` | Control | Phone → Pendant (Write) |
| `632de003-...` | Data | Pendant → Phone (Notify) |

Messages are Google Protocol Buffers wrapped in a BLE envelope that handles fragmentation:

```
BLEMessageFromNativeToPendant {
  index: int32           // Incrementing message counter
  ble_fragment_seq: int32 // Fragment number (0-based)
  num_fragments: int32   // Total fragments
  payload: bytes         // Protobuf payload
}
```

See [PROTOCOL.md](PROTOCOL.md) for full protocol documentation.

## Audio Format

Downloaded audio is in **raw Opus format** (concatenated frames without Ogg container).

### Decoding Audio

```bash
pendant decode recording.opus
```

### Audio Specifications
| Property | Value |
|----------|-------|
| Codec | Opus |
| Sample Rate | 16000 Hz |
| Channels | Mono |
| Bit Depth | 16-bit |
| Frame Size | ~960 samples (60ms) |

**Note:** Standard audio tools (ffmpeg, VLC) cannot play raw Opus directly. Use `pendant decode`
which handles frame boundary detection.

### If you have raw PCM data
```bash
ffmpeg -f s16le -ar 16000 -ac 1 -i pendant_audio.raw output.wav
```

## Encryption

The Pendant supports optional audio encryption using X25519 key exchange with ChaCha20-Poly1305.

### Setting Your Own Encryption Key

By default, recordings are encrypted with Limitless's server key. You can inject your own
key to decrypt future recordings:

```bash
# 1. Generate X25519 keypair (saved to keys/ directory)
pendant crypto keygen

# 2. Send public key to device
pendant crypto setkey

# 3. Download recordings (auto-decrypts with your private key)
pendant download
```

**Important:** Existing recordings encrypted with Limitless's key cannot be decrypted
without their private key. Only new recordings after `setkey` will use your key.

## Troubleshooting

### Device not responding
- Ensure device is paired AND bonded (check with `bluetoothctl info $PENDANT_ADDRESS`)
- Tap the Pendant to wake it
- Factory reset if needed (hold button 10+ seconds)

### Connection fails
- Make sure the Pendant isn't connected to your phone
- Try removing the pairing and re-pairing with `pendant bt pair`

### No audio data
- Check storage with `pendant status`
- If storage is 0%, there are no recordings to download
- Use debug mode to inspect: `pendant debug`

### Battery level
- Battery is now read from the standard BLE Battery Service (reliable)
- The custom protobuf BatteryStatus was fixed to use correct field numbers

### Audio won't play
- Downloaded audio is raw Opus (no Ogg container)
- Use `pendant decode file.opus` to decode

### "Device not found"
- Device may be asleep (tap to wake)
- Another application may have an exclusive connection
- Try scanning: `pendant bt scan`

## Development

Generate protobuf Python code:
```bash
protoc --python_out=proto proto/pendant.proto
```

The protobuf definitions are in `proto/pendant.proto`, derived from the decompiled
Android app in `limitless_source/`.

## Files

```
src/pendant/
  cli.py             - Main Click CLI entry point
  commands/          - CLI command implementations
  core/              - Core library (protocol, BLE clients, opus decoder)
proto/
  pendant.proto      - Protocol buffer definitions
  pendant_pb2.py     - Generated Python code (gitignored)
keys/                - Generated encryption keys (gitignored)
PROTOCOL.md          - Full protocol documentation
flake.nix            - Nix development environment
pyproject.toml       - Python package configuration
```

## License

For personal/research use only. The protocol was reverse-engineered from proprietary software.
