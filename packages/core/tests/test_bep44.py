from __future__ import annotations

import pytest
from meshplay_core.bep44 import (
    BEP44_MAX_VALUE_BYTES,
    decode_bep44_value,
    encode_bep44_value,
)

V2_INFOHASH = "a" * 64
V1_INFOHASH = "b" * 40


class TestEncode:
    def test_v2_infohash_roundtrip(self) -> None:
        encoded = encode_bep44_value(V2_INFOHASH)
        assert decode_bep44_value(encoded) == V2_INFOHASH

    def test_v1_infohash_roundtrip(self) -> None:
        encoded = encode_bep44_value(V1_INFOHASH)
        assert decode_bep44_value(encoded) == V1_INFOHASH

    def test_encoded_is_bytes(self) -> None:
        assert isinstance(encode_bep44_value(V2_INFOHASH), bytes)

    def test_v2_well_under_cap(self) -> None:
        encoded = encode_bep44_value(V2_INFOHASH)
        assert len(encoded) < BEP44_MAX_VALUE_BYTES

    def test_v2_exact_size(self) -> None:
        # d + 4:mfst + 64:<hash> + e = 1 + 6 + 67 + 1 = 75 bytes
        encoded = encode_bep44_value(V2_INFOHASH)
        assert len(encoded) == 75

    def test_v1_exact_size(self) -> None:
        # d + 4:mfst + 40:<hash> + e = 1 + 6 + 43 + 1 = 51 bytes
        encoded = encode_bep44_value(V1_INFOHASH)
        assert len(encoded) == 51

    def test_is_valid_bencode_structure(self) -> None:
        encoded = encode_bep44_value(V2_INFOHASH)
        assert encoded.startswith(b"d")
        assert encoded.endswith(b"e")
        assert b"4:mfst" in encoded

    def test_oversized_value_raises(self) -> None:
        # Construct a value that would exceed the cap
        huge = "a" * (BEP44_MAX_VALUE_BYTES + 100)
        with pytest.raises(ValueError, match="exceeds"):
            encode_bep44_value(huge)


class TestDecode:
    def test_missing_mfst_key_raises(self) -> None:
        # Valid bencode dict but wrong key
        bad = b"d4:nope5:valuee"
        with pytest.raises(ValueError, match="mfst"):
            decode_bep44_value(bad)

    def test_not_a_dict_raises(self) -> None:
        with pytest.raises(ValueError):
            decode_bep44_value(b"3:foo")

    def test_returns_str(self) -> None:
        result = decode_bep44_value(encode_bep44_value(V2_INFOHASH))
        assert isinstance(result, str)
