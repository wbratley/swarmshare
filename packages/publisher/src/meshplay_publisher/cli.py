from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import typer
from meshplay_core.crypto import sign_manifest
from meshplay_core.manifest import ChannelInfo, Manifest, VideoEntry

from meshplay_publisher.dht import put_manifest_to_dht
from meshplay_publisher.keystore import KeyEntry, create_key, load_key
from meshplay_publisher.torrent import (
    create_torrent_from_bytes,
    create_torrent_from_file,
    file_sha256,
)

app = typer.Typer(name="meshplay-publisher", help="Meshplay publisher CLI.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _channel_dir(pubkey_hex: str) -> Path:
    d = Path.home() / ".meshplay" / "channels" / pubkey_hex
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_or_create_manifest(pubkey_hex: str, key_entry: KeyEntry) -> Manifest:
    path = _channel_dir(pubkey_hex) / "manifest.json"
    if path.exists():
        return Manifest.model_validate_json(path.read_text())
    return Manifest(
        channel=ChannelInfo(
            pubkey=pubkey_hex,
            name=key_entry.name,
            description=key_entry.description,
        ),
        seq=0,
    )


def _save_manifest(pubkey_hex: str, manifest: Manifest) -> None:
    (_channel_dir(pubkey_hex) / "manifest.json").write_text(manifest.model_dump_json(indent=2))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def keygen(
    name: str = typer.Option(..., help="Channel display name"),
    description: str = typer.Option("", help="Channel description"),
) -> None:
    """Generate a new Ed25519 keypair and register a channel."""
    entry = create_key(name, description)
    typer.echo(f"Channel created: {entry.name}")
    typer.echo(f"Public key (share this): {entry.pubkey_hex}")
    typer.echo(f"Key saved to: {Path.home() / '.meshplay' / 'keys' / (entry.pubkey_hex + '.json')}")


@app.command()
def publish(
    video_file: Path = typer.Argument(help="Path to the video file to publish"),  # noqa: B008
    pubkey: str = typer.Option(..., help="Channel public key (64-char hex)"),
    title: str = typer.Option(..., help="Video title"),
    duration: int | None = typer.Option(None, help="Duration in seconds"),
    no_seed: bool = typer.Option(False, "--no-seed", help="Exit after DHT put; do not seed"),
) -> None:
    """Publish a video to a channel."""
    if not video_file.exists():
        typer.echo(f"Error: file not found: {video_file}", err=True)
        raise typer.Exit(1)

    key_entry = load_key(pubkey)
    seed = bytes.fromhex(key_entry.seed_hex)
    channel_dir = _channel_dir(pubkey)
    torrent_dir = channel_dir / "torrents"

    # --- Create video torrent ------------------------------------------------
    typer.echo("Creating video torrent...")
    infohash_v2, infohash_v1, magnet, torrent_path = create_torrent_from_file(
        video_file, torrent_dir
    )
    sha256 = file_sha256(video_file)
    typer.echo(f"  infohash (v2): {infohash_v2}")
    typer.echo(f"  magnet:        {magnet}")

    # --- Update manifest -----------------------------------------------------
    video = VideoEntry(
        id=uuid4(),
        title=title,
        infohash_v2=infohash_v2,
        infohash_v1=infohash_v1,
        sha256=sha256,
        magnet=magnet,
        published_at=datetime.now(UTC),
        duration_seconds=duration,
        size_bytes=video_file.stat().st_size,
    )

    manifest = _load_or_create_manifest(pubkey, key_entry)
    manifest = manifest.model_copy(
        update={"seq": manifest.seq + 1, "videos": [*manifest.videos, video]}
    )
    manifest = sign_manifest(manifest, seed)
    _save_manifest(pubkey, manifest)
    typer.echo(f"Manifest updated (seq={manifest.seq}, videos={len(manifest.videos)})")

    # --- Create manifest torrent ---------------------------------------------
    manifest_bytes = manifest.model_dump_json(indent=2).encode()
    manifest_ih_v2, _, _, manifest_torrent_path = create_torrent_from_bytes(
        "manifest.json", manifest_bytes, channel_dir
    )
    typer.echo(f"  manifest infohash (v2): {manifest_ih_v2}")

    # --- DHT put -------------------------------------------------------------
    typer.echo("Publishing to DHT...")
    ok = put_manifest_to_dht(seed, bytes.fromhex(pubkey), manifest_ih_v2)
    if ok:
        typer.echo("DHT put: OK")
    else:
        typer.echo("Warning: DHT put timed out — content still seeded locally", err=True)

    if no_seed:
        return

    # --- Seed both torrents until Ctrl-C -------------------------------------
    typer.echo("Seeding... (Ctrl-C to stop)")
    import libtorrent as lt  # noqa: PLC0415

    seed_settings = lt.default_settings()
    seed_settings["enable_dht"] = True
    seed_settings["enable_lsd"] = True
    ses = lt.session(seed_settings)
    flags = lt.add_torrent_params_flags_t.flag_seed_mode
    for t_path, sp in [
        (torrent_path, video_file.parent),
        (manifest_torrent_path, channel_dir),
    ]:
        ti = lt.torrent_info(str(t_path))
        ses.add_torrent({"ti": ti, "save_path": str(sp), "flags": flags})

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        typer.echo("\nStopped seeding.")
