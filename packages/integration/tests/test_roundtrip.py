"""Full publish → DHT → fetch → verify integration test.

Uses two local libtorrent sessions:
  - Publisher (port 16881): creates torrents, seeds them, does BEP44 put
  - Client   (port 16882): bootstraps from publisher DHT, gets manifest, downloads it

Run with: uv run pytest -m integration -v -s
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import libtorrent as lt
import pytest
from meshplay_core.bep44 import encode_bep44_value
from meshplay_core.crypto import (
    generate_keypair,
    sign_manifest,
    signing_key_bytes_for_libtorrent,
    verify_manifest,
)
from meshplay_core.manifest import ChannelInfo, Manifest, VideoEntry
from meshplay_publisher.torrent import (
    create_torrent_from_bytes,
    create_torrent_from_file,
    file_sha256,
)

_BOOTSTRAP_TIMEOUT = 10.0
_DHT_TIMEOUT = 30.0
_DOWNLOAD_TIMEOUT = 60.0
_POLL = 0.1

_PUB_PORT = 16881
_CLI_PORT = 16882


def _local_ip() -> str:
    """Return the primary non-loopback IP of this machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(port: int, local_ip: str, lsd: bool = True) -> lt.session:
    settings = lt.default_settings()
    settings["enable_dht"] = True
    settings["enable_lsd"] = lsd
    settings["enable_upnp"] = False
    settings["enable_natpmp"] = False
    settings["listen_interfaces"] = f"{local_ip}:{port}"
    settings["alert_mask"] = lt.alert_category.dht | lt.alert_category.status
    # Allow loopback / TEST-NET addresses in the DHT routing table so two
    # sessions on the same host can exchange DHT traffic.
    settings["dht_restrict_routing_ips"] = False
    settings["dht_restrict_search_ips"] = False
    # No external bootstrap — this test is fully self-contained.
    settings["dht_bootstrap_nodes"] = ""
    return lt.session(settings)


def _wait_for_listening(ses: lt.session, timeout: float = _BOOTSTRAP_TIMEOUT) -> None:
    """Wait until the session is bound and listening on its port."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for alert in ses.pop_alerts():
            if isinstance(alert, lt.listen_succeeded_alert):
                return
        time.sleep(_POLL)


def _drain_both(
    ses1: lt.session, ses2: lt.session, duration: float = 1.0
) -> None:
    """Drain alerts from both sessions concurrently for `duration` seconds.

    This allows DHT node-verification round-trips to complete after
    add_dht_node() is called. Draining both sessions simultaneously is
    required so neither blocks the other's in-flight DHT messages.
    """
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        ses1.pop_alerts()
        ses2.pop_alerts()
        time.sleep(_POLL)


def _poll_alert(
    ses: lt.session,
    alert_type: type,
    predicate: Callable[[lt.alert], bool],
    timeout: float,
) -> lt.alert | None:
    """Poll ses.pop_alerts() until an alert of alert_type matching predicate is found."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for alert in ses.pop_alerts():
            if isinstance(alert, alert_type) and predicate(alert):
                return alert
        time.sleep(_POLL)
    return None


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFullRoundTrip:
    def test_publish_and_fetch(self, tmp_path: Path) -> None:
        """End-to-end: publish a signed manifest, retrieve and verify it via DHT."""

        local_ip = _local_ip()

        # ------------------------------------------------------------------ #
        # 1. Keypair
        # ------------------------------------------------------------------ #
        seed, pubkey = generate_keypair()
        pubkey_hex = pubkey.hex()

        # ------------------------------------------------------------------ #
        # 2. Fake video file + torrent
        # ------------------------------------------------------------------ #
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(bytes(range(256)) * 400)  # 100 KB deterministic

        torrent_dir = tmp_path / "torrents"
        infohash_v2, infohash_v1, magnet, _torrent_path = create_torrent_from_file(
            video_path, torrent_dir
        )
        sha256 = file_sha256(video_path)

        # ------------------------------------------------------------------ #
        # 3. Build and sign manifest
        # ------------------------------------------------------------------ #
        video = VideoEntry(
            id=uuid4(),
            title="Test Video",
            infohash_v2=infohash_v2,
            infohash_v1=infohash_v1,
            sha256=sha256,
            magnet=magnet,
            published_at=datetime.now(UTC),
            size_bytes=video_path.stat().st_size,
        )
        manifest = Manifest(
            channel=ChannelInfo(pubkey=pubkey_hex, name="Integration Test Channel"),
            seq=1,
            videos=[video],
        )
        manifest = sign_manifest(manifest, seed)

        # ------------------------------------------------------------------ #
        # 4. Create manifest torrent, write the file, ready to seed
        # ------------------------------------------------------------------ #
        manifest_bytes = manifest.model_dump_json(indent=2).encode()
        manifest_dir = tmp_path / "channel"
        manifest_dir.mkdir()

        manifest_ih_v2, _, _, manifest_torrent_path = create_torrent_from_bytes(
            "manifest.json", manifest_bytes, manifest_dir
        )
        # Write the actual file so seed_mode can serve it
        (manifest_dir / "manifest.json").write_bytes(manifest_bytes)

        # ------------------------------------------------------------------ #
        # 5. Publisher session: seed manifest torrent
        # ------------------------------------------------------------------ #
        pub_ses = _make_session(_PUB_PORT, local_ip)

        # Wait until the publisher is listening before proceeding — add_dht_node
        # must be called only after the target session's socket is bound.
        _wait_for_listening(pub_ses)

        manifest_ti = lt.torrent_info(str(manifest_torrent_path))
        pub_ses.add_torrent(  # type: ignore[arg-type]
            {
                "ti": manifest_ti,
                "save_path": str(manifest_dir),
                "flags": lt.add_torrent_params_flags_t.flag_seed_mode,
            }
        )

        # ------------------------------------------------------------------ #
        # 6. Client session: create and mutually bootstrap with publisher
        # ------------------------------------------------------------------ #
        cli_ses = _make_session(_CLI_PORT, local_ip)
        _wait_for_listening(cli_ses)

        # Mutual bootstrap: each session knows about the other from the start.
        pub_ses.add_dht_node((local_ip, _CLI_PORT))
        cli_ses.add_dht_node((local_ip, _PUB_PORT))

        # Drain both sessions concurrently so the initial verification round-trips
        # complete before we issue the DHT put. Without this, add_dht_node nodes
        # are still in an unverified state when the put traversal runs.
        _drain_both(pub_ses, cli_ses, 1.0)

        # ------------------------------------------------------------------ #
        # 7. BEP44 put: publish manifest pointer from publisher
        # ------------------------------------------------------------------ #
        private_key_64 = signing_key_bytes_for_libtorrent(seed)
        bep44_value = encode_bep44_value(manifest_ih_v2)
        pub_ses.dht_put_mutable_item(  # type: ignore[arg-type]
            private_key_64, pubkey, bep44_value, b""
        )

        # Wait for PUT confirmation before proceeding to GET.
        def _is_put_success(alert: lt.alert) -> bool:
            return alert.num_success > 0  # type: ignore[attr-defined]

        put_alert = _poll_alert(pub_ses, lt.dht_put_alert, _is_put_success, _DHT_TIMEOUT)
        assert put_alert is not None, "DHT put timed out or found no nodes to store item"

        # ------------------------------------------------------------------ #
        # 8. BEP44 get: client retrieves manifest pointer
        # ------------------------------------------------------------------ #
        cli_ses.dht_get_mutable_item(pubkey, b"")

        def _is_our_item(alert: lt.alert) -> bool:
            if bytes(alert.key) != pubkey:  # type: ignore[attr-defined]
                return False
            # The alert fires for both found and not-found cases; only match
            # when the item is actually populated (access raises on not-found).
            try:
                item = alert.item  # type: ignore[attr-defined]
                return isinstance(item, dict)
            except RuntimeError:
                return False

        get_alert = _poll_alert(cli_ses, lt.dht_mutable_item_alert, _is_our_item, _DHT_TIMEOUT)
        assert get_alert is not None, "DHT get timed out — publisher session not reachable"

        # In libtorrent 2.0+, alert.item = {'key': pk, 'value': raw_bytes, ...}
        # 'value' contains the pre-bencoded data; bdecode to recover the dict.
        item = get_alert.item  # type: ignore[attr-defined]
        assert isinstance(item, dict), f"Unexpected item type from DHT: {type(item)}"
        raw_value = item.get("value")
        assert isinstance(raw_value, bytes), f"item['value'] not bytes: {type(raw_value)}"
        decoded_value = lt.bdecode(raw_value)
        assert isinstance(decoded_value, dict), f"decoded value not dict: {type(decoded_value)}"
        mfst = decoded_value.get(b"mfst")
        assert isinstance(mfst, bytes), f"mfst value is not bytes: {type(mfst)}"
        fetched_ih = mfst.decode("ascii")
        assert fetched_ih == manifest_ih_v2, (
            f"Fetched infohash {fetched_ih!r} != expected {manifest_ih_v2!r}"
        )

        # ------------------------------------------------------------------ #
        # 9. Download manifest torrent via client session
        # ------------------------------------------------------------------ #
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        magnet_uri = f"magnet:?xt=urn:btmh:1220{manifest_ih_v2}&dn=manifest.json"
        params = lt.parse_magnet_uri(magnet_uri)
        params.save_path = str(cache_dir)
        cli_handle = cli_ses.add_torrent(params)

        # Explicitly peer-connect to publisher to bypass tracker/DHT peer lookup
        cli_handle.connect_peer((local_ip, _PUB_PORT))

        def _is_finished(alert: lt.alert) -> bool:
            return alert.handle == cli_handle  # type: ignore[attr-defined]

        finish_alert = _poll_alert(
            cli_ses, lt.torrent_finished_alert, _is_finished, _DOWNLOAD_TIMEOUT
        )
        assert finish_alert is not None, "Manifest torrent download timed out"

        # ------------------------------------------------------------------ #
        # 10. Parse, verify, and assert
        # ------------------------------------------------------------------ #
        manifest_json_path = cache_dir / "manifest.json"
        assert manifest_json_path.exists(), "manifest.json not found after download"

        fetched_manifest = Manifest.model_validate_json(manifest_json_path.read_text())

        assert verify_manifest(fetched_manifest), "Manifest signature verification FAILED"
        assert fetched_manifest.channel.pubkey == pubkey_hex
        assert fetched_manifest.seq == 1
        assert len(fetched_manifest.videos) == 1
        assert fetched_manifest.videos[0].infohash_v2 == infohash_v2
        assert fetched_manifest.videos[0].title == "Test Video"
