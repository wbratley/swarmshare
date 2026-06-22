from __future__ import annotations

import time

import libtorrent as lt
from meshplay_core.bep44 import decode_bep44_value

_POLL_INTERVAL = 0.1
_BOOTSTRAP_POLL = 0.5


def get_manifest_infohash(
    pubkey: bytes,
    timeout_seconds: int = 30,
) -> str | None:
    """Look up the manifest infohash for a channel pubkey via BEP44 DHT get.

    Returns the manifest torrent infohash (v2 hex) or None on timeout.
    """
    ses = _make_session()

    _wait_for_bootstrap(ses, timeout_seconds)

    ses.dht_get_mutable_item(pubkey, b"")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for alert in ses.pop_alerts():
            if isinstance(alert, lt.dht_mutable_item_alert) and alert.key == pubkey:
                return decode_bep44_value(lt.bencode(alert.item))  # type: ignore[arg-type]
        time.sleep(_POLL_INTERVAL)

    return None


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
