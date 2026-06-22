# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install all packages (run from repo root)
uv sync --all-packages

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy packages/core/src packages/publisher/src packages/client/src

# Unit tests (all packages)
uv run pytest -m "not integration"

# Single test file
uv run pytest packages/core/tests/test_crypto.py -v

# Integration tests (require live DHT — run manually)
uv run pytest -m integration -v

# Run CLI tools
uv run meshplay-publisher --help
uv run meshplay-client --help
```

## Architecture

Meshplay is a decentralized video streaming service. Channel identity is an Ed25519 keypair; videos are BitTorrent torrents; the feed is a signed manifest discovered via BEP44 (mutable DHT items). No central server.

### Package layout

```
packages/
  core/       Zero I/O, zero networking. Manifest schema (Pydantic), Ed25519 crypto
              (PyNaCl), and BEP44 value encoding. Everything else depends on this.
  publisher/  CLI: keygen, publish. libtorrent for torrent creation + BEP44 DHT put.
  client/     CLI: subscribe, fetch, stream. libtorrent for BEP44 DHT get + download.
```

### Data flow

```
Publisher:
  keygen  → Ed25519 seed stored at ~/.meshplay/keys/<pubkey_hex>.json (0o600)
  publish → libtorrent creates video torrent (infohash)
           → manifest JSON updated + signed (seq bumped)
           → libtorrent creates manifest torrent
           → both torrents seeded
           → BEP44 DHT put: key=pubkey, value={"mfst": manifest_infohash}

Client:
  subscribe → pubkey stored in ~/.meshplay/subscriptions.json
  fetch     → BEP44 DHT get → manifest infohash → download manifest torrent
            → verify Ed25519 signature → display video list
  stream    → add torrent with sequential_download=True → progress to stderr
```

### Key design decisions

- **Dual signing**: BEP44 signs the DHT pointer; the manifest JSON also carries its own embedded signature so it's self-authenticating out-of-band.
- **Canonical bytes for signing**: `manifest.canonical_bytes()` = JSON with `signature` excluded, keys sorted, no whitespace. `seq` is included so downgrade/replay attacks are detectable.
- **Hex everywhere**: pubkeys, infohashes, signatures all stored and displayed as lowercase hex (no base64 variants).
- **Seed only stored**: only the 32-byte Ed25519 seed is persisted; the 64-byte libtorrent private key (`seed || pubkey`) is derived on demand via `bytes(nacl.signing.SigningKey(seed))`.
- **libtorrent only in publisher/client**: `core` uses a minimal pure-Python bencode for `bep44.py` so it stays dependency-free of the 6 MB libtorrent wheel and tests stay fast.
- **Ephemeral sessions (MVP)**: each CLI command creates and destroys its own libtorrent session. Persistent relay daemon is post-MVP.

### BEP44 item format

DHT key = 32-byte Ed25519 pubkey. Value (bencoded, always < 1000 bytes):
```json
{"mfst": "<40-char lowercase hex infohash of manifest torrent>"}
```
The manifest JSON is distributed as its own small torrent — not directly in the DHT value — because BEP44 values are capped at ~1000 bytes.
