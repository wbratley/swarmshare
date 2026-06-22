from __future__ import annotations

import os
from pathlib import Path

import pytest
from meshplay_core.crypto import pubkey_from_seed
from meshplay_publisher.keystore import KeyEntry, create_key, list_keys, load_key


@pytest.fixture(autouse=True)
def isolated_keys_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect all key I/O to a temp directory for each test."""
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()

    import meshplay_publisher.keystore as ks

    monkeypatch.setattr(ks, "_keys_dir", lambda: keys_dir)
    monkeypatch.setattr(ks, "_key_path", lambda hex: keys_dir / f"{hex}.json")


class TestCreateKey:
    def test_returns_key_entry(self) -> None:
        entry = create_key("Test Channel")
        assert isinstance(entry, KeyEntry)

    def test_pubkey_is_64_hex(self) -> None:
        entry = create_key("Ch")
        assert len(entry.pubkey_hex) == 64
        assert all(c in "0123456789abcdef" for c in entry.pubkey_hex)

    def test_seed_is_64_hex(self) -> None:
        entry = create_key("Ch")
        assert len(entry.seed_hex) == 64

    def test_seed_derives_pubkey(self) -> None:
        entry = create_key("Ch")
        seed = bytes.fromhex(entry.seed_hex)
        assert pubkey_from_seed(seed).hex() == entry.pubkey_hex

    def test_name_stored(self) -> None:
        entry = create_key("My Channel", description="desc")
        assert entry.name == "My Channel"
        assert entry.description == "desc"

    def test_unique_keys(self) -> None:
        a = create_key("A")
        b = create_key("B")
        assert a.pubkey_hex != b.pubkey_hex
        assert a.seed_hex != b.seed_hex

    def test_file_created(self, tmp_path: Path) -> None:
        import meshplay_publisher.keystore as ks

        entry = create_key("Ch")
        path = ks._key_path(entry.pubkey_hex)
        assert path.exists()

    def test_file_permissions_are_600(self, tmp_path: Path) -> None:
        import meshplay_publisher.keystore as ks

        entry = create_key("Ch")
        path = ks._key_path(entry.pubkey_hex)
        mode = oct(os.stat(path).st_mode)[-3:]
        assert mode == "600"


class TestLoadKey:
    def test_round_trip(self) -> None:
        created = create_key("Round Trip")
        loaded = load_key(created.pubkey_hex)
        assert loaded.pubkey_hex == created.pubkey_hex
        assert loaded.seed_hex == created.seed_hex
        assert loaded.name == created.name

    def test_missing_key_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_key("a" * 64)


class TestListKeys:
    def test_empty(self) -> None:
        assert list_keys() == []

    def test_returns_all_keys(self) -> None:
        create_key("A")
        create_key("B")
        create_key("C")
        keys = list_keys()
        assert len(keys) == 3

    def test_sorted_by_created_at(self) -> None:
        a = create_key("A")
        b = create_key("B")
        keys = list_keys()
        assert keys[0].pubkey_hex == a.pubkey_hex
        assert keys[1].pubkey_hex == b.pubkey_hex
