from __future__ import annotations

import json
from pathlib import Path


def _subs_path() -> Path:
    p = Path.home() / ".meshplay" / "subscriptions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> list[str]:
    p = _subs_path()
    if not p.exists():
        return []
    data: dict[str, list[str]] = json.loads(p.read_text())
    return data.get("subscriptions", [])


def _save(subs: list[str]) -> None:
    _subs_path().write_text(json.dumps({"subscriptions": subs}, indent=2))


def subscribe(pubkey_hex: str) -> None:
    """Add pubkey_hex to subscriptions (idempotent)."""
    subs = _load()
    if pubkey_hex not in subs:
        subs.append(pubkey_hex)
        _save(subs)


def unsubscribe(pubkey_hex: str) -> None:
    """Remove pubkey_hex from subscriptions (no-op if absent)."""
    subs = _load()
    filtered = [s for s in subs if s != pubkey_hex]
    if len(filtered) != len(subs):
        _save(filtered)


def list_subscriptions() -> list[str]:
    """Return all subscribed pubkey hex strings."""
    return _load()
