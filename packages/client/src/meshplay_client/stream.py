from __future__ import annotations

import sys
import time
from pathlib import Path

import libtorrent as lt

_POLL_INTERVAL = 0.5


def fetch_manifest(
    manifest_infohash_v2: str,
    cache_dir: Path,
    timeout_seconds: int = 60,
) -> Path | None:
    """Download the manifest torrent and return the path to manifest.json.

    Uses a v2 magnet URI constructed from the infohash.  Returns None on timeout.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    settings = lt.default_settings()
    settings["enable_dht"] = True
    settings["enable_lsd"] = True
    settings["alert_mask"] = lt.alert_category.status | lt.alert_category.dht
    ses = lt.session(settings)

    magnet = f"magnet:?xt=urn:btmh:1220{manifest_infohash_v2}&dn=manifest.json"
    params = lt.parse_magnet_uri(magnet)
    params.save_path = str(cache_dir)
    handle = ses.add_torrent(params)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for alert in ses.pop_alerts():
            if isinstance(alert, lt.torrent_finished_alert) and alert.handle == handle:
                return cache_dir / "manifest.json"
            if isinstance(alert, lt.torrent_error_alert) and alert.handle == handle:
                return None
        time.sleep(_POLL_INTERVAL)

    return None


def stream_video(
    magnet_or_infohash: str,
    output_dir: Path,
    timeout_seconds: int = 300,
) -> Path | None:
    """Download a video torrent with sequential piece-picking.

    Accepts a magnet URI or a v2 infohash hex (64 chars).
    Prints download progress to stderr.
    Returns the file path when fully downloaded, or None on timeout.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = lt.default_settings()
    settings["enable_dht"] = True
    settings["enable_lsd"] = True
    settings["alert_mask"] = lt.alert_category.status | lt.alert_category.dht
    ses = lt.session(settings)

    if magnet_or_infohash.startswith("magnet:"):
        params = lt.parse_magnet_uri(magnet_or_infohash)
    else:
        magnet = f"magnet:?xt=urn:btmh:1220{magnet_or_infohash}"
        params = lt.parse_magnet_uri(magnet)

    params.save_path = str(output_dir)
    params.flags |= lt.torrent_flags.sequential_download
    handle = ses.add_torrent(params)
    handle.set_sequential_download(True)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = handle.status()
        print(
            f"\r  {status.progress * 100:.1f}%  "
            f"↓ {status.download_rate / 1024:.1f} KB/s  "
            f"peers: {status.num_peers}     ",
            end="",
            file=sys.stderr,
            flush=True,
        )
        if status.state >= lt.torrent_status.finished:
            print("", file=sys.stderr)
            tf = handle.torrent_file()
            if tf is not None:
                files = tf.files()
                if files.num_files() > 0:
                    return output_dir / files.file_path(0)
            return output_dir
        time.sleep(_POLL_INTERVAL)

    print("", file=sys.stderr)
    return None
