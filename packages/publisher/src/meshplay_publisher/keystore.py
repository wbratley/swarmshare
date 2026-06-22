from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from meshplay_core.crypto import generate_keypair


@dataclass
class KeyEntry:
    pubkey_hex: str
    seed_hex: str
    name: str
    description: str
    created_at: datetime


def create_key(name: str, description: str = "") -> KeyEntry:
    seed, pubkey = generate_keypair()
    entry = KeyEntry(
        pubkey_hex=pubkey.hex(),
        seed_hex=seed.hex(),
        name=name,
        description=description,
        created_at=datetime.now(UTC),
    )
    _save_key(entry)
    return entry


def load_key(pubkey_hex: str) -> KeyEntry:
    path = _key_path(pubkey_hex)
    if not path.exists():
        raise FileNotFoundError(f"No key found for pubkey {pubkey_hex!r}")
    data = json.loads(path.read_text())
    return KeyEntry(
        pubkey_hex=data["pubkey_hex"],
        seed_hex=data["seed_hex"],
        name=data["name"],
        description=data.get("description", ""),
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def list_keys() -> list[KeyEntry]:
    keys = []
    for path in _keys_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text())
            keys.append(
                KeyEntry(
                    pubkey_hex=data["pubkey_hex"],
                    seed_hex=data["seed_hex"],
                    name=data["name"],
                    description=data.get("description", ""),
                    created_at=datetime.fromisoformat(data["created_at"]),
                )
            )
        except Exception:
            pass
    return sorted(keys, key=lambda k: k.created_at)


def _save_key(entry: KeyEntry) -> None:
    path = _key_path(entry.pubkey_hex)
    data = {
        "pubkey_hex": entry.pubkey_hex,
        "seed_hex": entry.seed_hex,
        "name": entry.name,
        "description": entry.description,
        "created_at": entry.created_at.isoformat(),
    }
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, 0o600)


def _keys_dir() -> Path:
    d = Path.home() / ".meshplay" / "keys"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key_path(pubkey_hex: str) -> Path:
    return _keys_dir() / f"{pubkey_hex}.json"
