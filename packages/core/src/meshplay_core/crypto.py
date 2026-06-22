from __future__ import annotations

from typing import TYPE_CHECKING

import nacl.exceptions
import nacl.signing

if TYPE_CHECKING:
    from meshplay_core.manifest import Manifest


def generate_keypair() -> tuple[bytes, bytes]:
    """Return (seed_32, pubkey_32) as raw bytes."""
    sk = nacl.signing.SigningKey.generate()
    seed: bytes = bytes(sk)
    pubkey: bytes = bytes(sk.verify_key)
    return seed, pubkey


def pubkey_from_seed(seed: bytes) -> bytes:
    """Derive the 32-byte public key from a 32-byte seed."""
    return bytes(nacl.signing.SigningKey(seed).verify_key)


def signing_key_bytes_for_libtorrent(seed: bytes) -> bytes:
    """Return the 64-byte expanded key that libtorrent's dht_put_mutable_item() expects.

    Libtorrent's ed25519 implementation (src/ed25519/sign.cpp) treats the 64-byte key as:
      bytes[0:32] = private scalar = SHA-512(seed)[0:32] with RFC 8032 clamping
      bytes[32:64] = nonce prefix   = SHA-512(seed)[32:64]

    This differs from PyNaCl / libsodium which store (seed || pubkey).
    """
    import hashlib

    expanded = bytearray(hashlib.sha512(seed).digest())
    expanded[0] &= 248  # clear cofactor bits
    expanded[31] &= 63  # clear high bits
    expanded[31] |= 64  # set canonical high bit
    return bytes(expanded)


def sign_manifest(manifest: Manifest, seed: bytes) -> Manifest:
    """Return a new Manifest with the signature field populated."""
    sk = nacl.signing.SigningKey(seed)
    sig: bytes = sk.sign(manifest.canonical_bytes()).signature
    return manifest.model_copy(update={"signature": sig.hex()})


def verify_manifest(manifest: Manifest) -> bool:
    """Return True if the manifest's embedded signature is valid.

    Returns False (rather than raising) on any failure so callers can treat
    an invalid manifest as untrusted content without crashing.
    """
    if manifest.signature is None:
        return False
    try:
        pubkey_bytes = bytes.fromhex(manifest.channel.pubkey)
        sig_bytes = bytes.fromhex(manifest.signature)
        vk = nacl.signing.VerifyKey(pubkey_bytes)
        vk.verify(manifest.canonical_bytes(), sig_bytes)
        return True
    except (nacl.exceptions.BadSignatureError, Exception):
        return False
