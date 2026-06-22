"""Minimal BEP44 value encoding for Meshplay's single-field DHT item.

The only structure published to the DHT is {"mfst": "<40 or 64-char infohash>"}.
Implementing bencode for this specific shape avoids adding libtorrent as a
dependency of meshplay-core (which must stay I/O-free and fast to test).
"""

from __future__ import annotations

BEP44_MAX_VALUE_BYTES = 1000
_MFST_KEY = b"mfst"


def encode_bep44_value(manifest_infohash_hex: str) -> bytes:
    """Bencode {"mfst": "<infohash_hex>"} and return the bytes.

    Raises ValueError if the result would exceed the BEP44 1000-byte cap.
    """
    infohash = manifest_infohash_hex.encode("ascii")
    # bencode dict: d <key-len>:<key> <val-len>:<val> e
    encoded = b"d" + _bencode_str(_MFST_KEY) + _bencode_str(infohash) + b"e"
    if len(encoded) > BEP44_MAX_VALUE_BYTES:
        raise ValueError(
            f"BEP44 value is {len(encoded)} bytes, exceeds {BEP44_MAX_VALUE_BYTES}-byte cap"
        )
    return encoded


def decode_bep44_value(raw: bytes) -> str:
    """Decode a bencoded BEP44 value and return the manifest infohash hex string.

    Raises ValueError if the structure is not {"mfst": "<string>"}.
    """
    result = _bdecode_dict(raw)
    if _MFST_KEY not in result:
        raise ValueError(f"BEP44 value missing 'mfst' key: {raw!r}")
    return result[_MFST_KEY].decode("ascii")


# ---------------------------------------------------------------------------
# Minimal bencode helpers — only what's needed for this module
# ---------------------------------------------------------------------------


def _bencode_str(s: bytes) -> bytes:
    return str(len(s)).encode("ascii") + b":" + s


def _bdecode_dict(data: bytes) -> dict[bytes, bytes]:
    if not data.startswith(b"d") or not data.endswith(b"e"):
        raise ValueError(f"Expected bencoded dict, got: {data!r}")
    result: dict[bytes, bytes] = {}
    pos = 1  # skip leading 'd'
    while pos < len(data) - 1:  # stop before trailing 'e'
        key, pos = _bdecode_str(data, pos)
        val, pos = _bdecode_str(data, pos)
        result[key] = val
    return result


def _bdecode_str(data: bytes, pos: int) -> tuple[bytes, int]:
    colon = data.index(b":", pos)
    length = int(data[pos:colon])
    start = colon + 1
    end = start + length
    if end > len(data):
        raise ValueError("Bencoded string extends past end of data")
    return data[start:end], end
