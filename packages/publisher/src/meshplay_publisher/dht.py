from __future__ import annotations

import time

import libtorrent as lt
from meshplay_core.bep44 import encode_bep44_value
from meshplay_core.crypto import signing_key_bytes_for_libtorrent

_POLL_INTERVAL = 0.1
_BOOTSTRAP_POLL = 0.5


def put_manifest_to_dht(
    seed: bytes,
    pubkey: bytes,
    manifest_infohash: str,
    timeout_seconds: int = 30,
) -> bool:
    """Publish the manifest pointer to the DHT via BEP44.

    Creates an ephemeral libtorrent session, bootstraps the DHT, puts the
    signed mutable item, waits for at least one node to confirm receipt, then
    returns. The item persists in DHT nodes until their TTL expires (~10 min)
    and is refreshed by any seeding session that remains running.

    Returns True if at least one DHT node confirmed the put before timeout.
    """
    ses = _make_session()

    _wait_for_bootstrap(ses, timeout_seconds)

    private_key_64 = signing_key_bytes_for_libtorrent(seed)
    bep44_value = encode_bep44_value(manifest_infohash)
    ses.dht_put_mutable_item(private_key_64, pubkey, bep44_value, b"")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for alert in ses.pop_alerts():
            if isinstance(alert, lt.dht_put_alert) and alert.public_key == pubkey:
                return alert.num_success > 0
        time.sleep(_POLL_INTERVAL)

    return False


def _make_session() -> lt.session:
    settings = lt.default_settings()
    settings["enable_dht"] = True
    settings["enable_lsd"] = False
    settings["enable_upnp"] = False
    settings["enable_natpmp"] = False
    settings["alert_mask"] = lt.alert_category.dht | lt.alert_category.status
    return lt.session(settings)


def _wait_for_bootstrap(ses: lt.session, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for alert in ses.pop_alerts():
            if isinstance(alert, lt.dht_bootstrap_alert):
                return
        time.sleep(_BOOTSTRAP_POLL)
