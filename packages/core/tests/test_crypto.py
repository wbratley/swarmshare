from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from meshplay_core.crypto import (
    generate_keypair,
    pubkey_from_seed,
    sign_manifest,
    signing_key_bytes_for_libtorrent,
    verify_manifest,
)
from meshplay_core.manifest import ChannelInfo, Manifest, VideoEntry


def make_manifest(pubkey_hex: str, seq: int = 0) -> Manifest:
    video = VideoEntry(
        id=uuid4(),
        title="Test Video",
        infohash_v2="b" * 64,
        sha256="d" * 64,
        magnet="magnet:?xt=urn:btih:" + "b" * 64,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return Manifest(
        channel=ChannelInfo(pubkey=pubkey_hex, name="Test Channel"),
        seq=seq,
        videos=[video],
    )


class TestKeygen:
    def test_seed_is_32_bytes(self) -> None:
        seed, _ = generate_keypair()
        assert len(seed) == 32

    def test_pubkey_is_32_bytes(self) -> None:
        _, pubkey = generate_keypair()
        assert len(pubkey) == 32

    def test_unique_each_call(self) -> None:
        seed1, _ = generate_keypair()
        seed2, _ = generate_keypair()
        assert seed1 != seed2

    def test_pubkey_derived_from_seed(self) -> None:
        seed, pubkey = generate_keypair()
        assert pubkey_from_seed(seed) == pubkey


class TestSigningKeyForLibtorrent:
    def test_is_64_bytes(self) -> None:
        seed, _ = generate_keypair()
        key = signing_key_bytes_for_libtorrent(seed)
        assert len(key) == 64

    def test_is_sha512_expanded_form(self) -> None:
        import hashlib

        seed, _ = generate_keypair()
        key = signing_key_bytes_for_libtorrent(seed)
        # The expanded key is SHA-512(seed) with RFC 8032 clamping applied.
        expected = bytearray(hashlib.sha512(seed).digest())
        expected[0] &= 248
        expected[31] &= 63
        expected[31] |= 64
        assert key == bytes(expected)

    def test_not_seed_pubkey_concatenation(self) -> None:
        seed, pubkey = generate_keypair()
        key = signing_key_bytes_for_libtorrent(seed)
        # Libtorrent expects SHA-512(seed) with clamping, NOT seed||pubkey.
        assert key != seed + pubkey


class TestSignAndVerify:
    def test_sign_populates_signature(self) -> None:
        seed, pubkey = generate_keypair()
        m = make_manifest(pubkey.hex())
        signed = sign_manifest(m, seed)
        assert signed.signature is not None
        assert len(signed.signature) == 128  # 64 bytes as hex

    def test_original_unchanged(self) -> None:
        seed, pubkey = generate_keypair()
        m = make_manifest(pubkey.hex())
        sign_manifest(m, seed)
        assert m.signature is None  # sign_manifest returns a new instance

    def test_verify_valid_signature(self) -> None:
        seed, pubkey = generate_keypair()
        m = make_manifest(pubkey.hex())
        signed = sign_manifest(m, seed)
        assert verify_manifest(signed) is True

    def test_verify_unsigned_returns_false(self) -> None:
        _, pubkey = generate_keypair()
        m = make_manifest(pubkey.hex())
        assert verify_manifest(m) is False

    def test_verify_tampered_title(self) -> None:
        seed, pubkey = generate_keypair()
        m = make_manifest(pubkey.hex())
        signed = sign_manifest(m, seed)
        # Tamper: change video title after signing
        tampered_video = signed.videos[0].model_copy(update={"title": "EVIL"})
        tampered = signed.model_copy(update={"videos": [tampered_video]})
        assert verify_manifest(tampered) is False

    def test_verify_tampered_seq(self) -> None:
        seed, pubkey = generate_keypair()
        m = make_manifest(pubkey.hex(), seq=1)
        signed = sign_manifest(m, seed)
        # Downgrade attack: change seq to 0 without re-signing
        downgraded = signed.model_copy(update={"seq": 0})
        assert verify_manifest(downgraded) is False

    def test_verify_wrong_pubkey(self) -> None:
        seed, pubkey = generate_keypair()
        _, other_pubkey = generate_keypair()
        m = make_manifest(pubkey.hex())
        signed = sign_manifest(m, seed)
        # Swap channel pubkey to a different key
        wrong_channel = signed.channel.model_copy(update={"pubkey": other_pubkey.hex()})
        wrong = signed.model_copy(update={"channel": wrong_channel})
        assert verify_manifest(wrong) is False

    def test_verify_corrupted_signature_hex(self) -> None:
        seed, pubkey = generate_keypair()
        m = make_manifest(pubkey.hex())
        signed = sign_manifest(m, seed)
        bad_sig = "f" * 128
        corrupted = signed.model_copy(update={"signature": bad_sig})
        assert verify_manifest(corrupted) is False

    def test_sign_verify_higher_seq(self) -> None:
        seed, pubkey = generate_keypair()
        for seq in range(3):
            m = make_manifest(pubkey.hex(), seq=seq)
            signed = sign_manifest(m, seed)
            assert verify_manifest(signed) is True

    @pytest.mark.parametrize("title", ["Hello", "Unicode: café", "Symbols: <>&\"'"])
    def test_sign_verify_various_titles(self, title: str) -> None:
        seed, pubkey = generate_keypair()
        video = VideoEntry(
            id=uuid4(),
            title=title,
            infohash_v2="b" * 64,
            sha256="d" * 64,
            magnet="magnet:",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        m = Manifest(
            channel=ChannelInfo(pubkey=pubkey.hex(), name="Ch"),
            seq=0,
            videos=[video],
        )
        signed = sign_manifest(m, seed)
        assert verify_manifest(signed) is True
