from __future__ import annotations

import re
from pathlib import Path

import typer
from meshplay_core.crypto import verify_manifest
from meshplay_core.manifest import Manifest

from meshplay_client import dht as dht_mod
from meshplay_client import stream as stream_mod
from meshplay_client import subscriptions as subs_mod

app = typer.Typer(name="meshplay-client", help="Meshplay client CLI.")

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_pubkey(pubkey: str) -> None:
    if not _HEX64_RE.match(pubkey):
        typer.echo("Error: pubkey must be a 64-character lowercase hex string.", err=True)
        raise typer.Exit(1)


@app.command()
def subscribe(
    pubkey: str = typer.Argument(help="Channel public key (64-char hex)"),  # noqa: B008
) -> None:
    """Subscribe to a channel by its public key."""
    _validate_pubkey(pubkey)
    subs_mod.subscribe(pubkey)
    typer.echo(f"Subscribed to {pubkey}")


@app.command()
def unsubscribe(
    pubkey: str = typer.Argument(help="Channel public key (64-char hex)"),  # noqa: B008
) -> None:
    """Unsubscribe from a channel."""
    _validate_pubkey(pubkey)
    subs_mod.unsubscribe(pubkey)
    typer.echo(f"Unsubscribed from {pubkey}")


@app.command()
def fetch(
    pubkey: str = typer.Argument(help="Channel public key (64-char hex)"),  # noqa: B008
    timeout: int = typer.Option(30, help="DHT lookup timeout in seconds"),
) -> None:
    """Fetch and display the latest manifest for a channel."""
    _validate_pubkey(pubkey)

    typer.echo("Looking up manifest in DHT...")
    manifest_infohash = dht_mod.get_manifest_infohash(
        bytes.fromhex(pubkey), timeout_seconds=timeout
    )
    if manifest_infohash is None:
        typer.echo("Error: DHT lookup timed out — channel not found or not seeded", err=True)
        raise typer.Exit(1)
    typer.echo(f"  manifest infohash (v2): {manifest_infohash}")

    cache_dir = Path.home() / ".meshplay" / "cache" / pubkey
    typer.echo("Downloading manifest torrent...")
    manifest_path = stream_mod.fetch_manifest(manifest_infohash, cache_dir, timeout_seconds=60)
    if manifest_path is None or not manifest_path.exists():
        typer.echo("Error: manifest download timed out", err=True)
        raise typer.Exit(1)

    manifest = Manifest.model_validate_json(manifest_path.read_text())

    sig_ok = verify_manifest(manifest)
    sig_label = "VALID" if sig_ok else "INVALID (WARNING: do not trust this manifest)"

    typer.echo("")
    typer.echo(f"Channel:   {manifest.channel.name}")
    typer.echo(f"Pubkey:    {manifest.channel.pubkey}")
    if manifest.channel.description:
        typer.echo(f"About:     {manifest.channel.description}")
    typer.echo(f"Sequence:  {manifest.seq}")
    typer.echo(f"Signature: {sig_label}")
    typer.echo(f"Videos:    {len(manifest.videos)}")

    for i, video in enumerate(manifest.videos, 1):
        typer.echo("")
        typer.echo(f"  [{i}] {video.title}")
        typer.echo(f"      infohash: {video.infohash_v2}")
        typer.echo(f"      magnet:   {video.magnet}")
        typer.echo(f"      published: {video.published_at.strftime('%Y-%m-%d %H:%M UTC')}")
        if video.size_bytes is not None:
            mb = video.size_bytes / 1_048_576
            typer.echo(f"      size:     {mb:.1f} MB")
        if video.duration_seconds is not None:
            m, s = divmod(video.duration_seconds, 60)
            typer.echo(f"      duration: {m}m {s}s")

    if not sig_ok:
        raise typer.Exit(2)


@app.command()
def stream(
    infohash_or_magnet: str = typer.Argument(  # noqa: B008
        help="Video infohash_v2 (64-char hex) or magnet URI"
    ),
    output: Path = typer.Option(Path("."), "--output", "-o", help="Directory to save the video"),  # noqa: B008
    timeout: int = typer.Option(300, help="Download timeout in seconds"),
) -> None:
    """Stream a video by its v2 infohash or magnet URI."""
    typer.echo("Connecting to peers...")
    result = stream_mod.stream_video(infohash_or_magnet, output, timeout_seconds=timeout)
    if result is None:
        typer.echo("Error: download timed out", err=True)
        raise typer.Exit(1)
    typer.echo(f"Saved to: {result}")
