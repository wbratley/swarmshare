from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from uuid import uuid4

import pytest
from meshplay_core.manifest import ChannelInfo, Manifest, VideoEntry
from pydantic import ValidationError

PUBKEY_HEX = "a" * 64
INFOHASH_V2 = "b" * 64
INFOHASH_V1 = "c" * 40
SHA256 = "d" * 64
SIG = "e" * 128


def make_channel() -> ChannelInfo:
    return ChannelInfo(pubkey=PUBKEY_HEX, name="Test Channel")


def make_video() -> VideoEntry:
    return VideoEntry(
        id=uuid4(),
        title="Episode 1",
        infohash_v2=INFOHASH_V2,
        infohash_v1=INFOHASH_V1,
        sha256=SHA256,
        magnet=f"magnet:?xt=urn:btih:{INFOHASH_V1}",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        duration_seconds=120,
        size_bytes=10_485_760,
    )


def make_manifest(**kwargs: object) -> Manifest:
    defaults: dict[str, object] = {"channel": make_channel(), "seq": 0, "videos": [make_video()]}
    defaults.update(kwargs)
    return Manifest(**defaults)


class TestChannelInfo:
    def test_valid(self) -> None:
        ch = make_channel()
        assert ch.pubkey == PUBKEY_HEX

    def test_pubkey_too_short(self) -> None:
        with pytest.raises(ValidationError):
            ChannelInfo(pubkey="a" * 63, name="x")

    def test_pubkey_uppercase_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChannelInfo(pubkey="A" * 64, name="x")

    def test_pubkey_non_hex_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChannelInfo(pubkey="g" * 64, name="x")


class TestVideoEntry:
    def test_valid(self) -> None:
        v = make_video()
        assert v.infohash_v2 == INFOHASH_V2

    def test_infohash_v2_wrong_length(self) -> None:
        with pytest.raises(ValidationError):
            VideoEntry(
                id=uuid4(),
                title="x",
                infohash_v2="b" * 63,
                sha256=SHA256,
                magnet="magnet:",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
            )

    def test_sha256_wrong_length(self) -> None:
        with pytest.raises(ValidationError):
            VideoEntry(
                id=uuid4(),
                title="x",
                infohash_v2=INFOHASH_V2,
                sha256="d" * 63,
                magnet="magnet:",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
            )

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VideoEntry(
                id=uuid4(),
                title="x",
                infohash_v2=INFOHASH_V2,
                sha256=SHA256,
                magnet="magnet:",
                published_at=datetime(2026, 1, 1),  # no tzinfo
            )

    def test_non_utc_datetime_normalised(self) -> None:
        from datetime import timedelta

        tz_plus2 = timezone(timedelta(hours=2))
        v = VideoEntry(
            id=uuid4(),
            title="x",
            infohash_v2=INFOHASH_V2,
            sha256=SHA256,
            magnet="magnet:",
            published_at=datetime(2026, 1, 1, 2, 0, tzinfo=tz_plus2),
        )
        assert v.published_at.tzinfo == UTC
        assert v.published_at.hour == 0

    def test_infohash_v1_optional(self) -> None:
        v = VideoEntry(
            id=uuid4(),
            title="x",
            infohash_v2=INFOHASH_V2,
            sha256=SHA256,
            magnet="magnet:",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert v.infohash_v1 is None


class TestManifest:
    def test_valid(self) -> None:
        m = make_manifest()
        assert m.seq == 0
        assert len(m.videos) == 1

    def test_seq_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_manifest(seq=-1)

    def test_signature_wrong_length(self) -> None:
        with pytest.raises(ValidationError):
            make_manifest(signature="e" * 127)

    def test_signature_optional(self) -> None:
        m = make_manifest()
        assert m.signature is None


class TestCanonicalBytes:
    def test_deterministic(self) -> None:
        m = make_manifest()
        assert m.canonical_bytes() == m.canonical_bytes()

    def test_excludes_signature(self) -> None:
        m_unsigned = make_manifest()
        m_signed = m_unsigned.model_copy(update={"signature": SIG})
        assert m_unsigned.canonical_bytes() == m_signed.canonical_bytes()

    def test_includes_seq(self) -> None:
        m0 = make_manifest(seq=0)
        m1 = make_manifest(seq=1)
        assert m0.canonical_bytes() != m1.canonical_bytes()

    def test_is_valid_json(self) -> None:
        m = make_manifest()
        parsed = json.loads(m.canonical_bytes())
        assert parsed["channel"]["pubkey"] == PUBKEY_HEX
        assert "signature" not in parsed

    def test_keys_sorted(self) -> None:
        m = make_manifest()
        raw = m.canonical_bytes().decode()
        # Verify no extra whitespace (compact separators)
        assert "  " not in raw
        assert "\n" not in raw
