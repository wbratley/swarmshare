from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import libtorrent as lt


def create_torrent_from_file(
    file_path: Path,
    save_dir: Path,
) -> tuple[str, str | None, str, Path]:
    """Create a hybrid v1+v2 BitTorrent torrent from a file.

    Returns (infohash_v2_hex, infohash_v1_hex_or_none, magnet_uri, torrent_file_path).
    Raises RuntimeError if libtorrent cannot produce a v2 infohash.
    """
    file_path = file_path.resolve()
    save_dir.mkdir(parents=True, exist_ok=True)

    fs = lt.file_storage()
    lt.add_files(fs, str(file_path))

    # Default flags = 0 → hybrid torrent (both SHA-1 v1 and SHA-256 v2 piece tree)
    ct = lt.create_torrent(fs)
    lt.set_piece_hashes(ct, str(file_path.parent))

    torrent_entry = ct.generate()
    ti = lt.torrent_info(torrent_entry)

    ih = ti.info_hashes()
    if not ih.has_v2():
        raise RuntimeError(
            "libtorrent did not produce a v2 infohash; ensure you are using libtorrent >= 2.0"
        )

    infohash_v2: str = ih.v2.to_bytes().hex()
    infohash_v1: str | None = ih.v1.to_bytes().hex() if ih.has_v1() else None

    magnet: str = lt.make_magnet_uri(ti)

    torrent_path = save_dir / f"{infohash_v2}.torrent"
    torrent_path.write_bytes(lt.bencode(torrent_entry))

    return infohash_v2, infohash_v1, magnet, torrent_path


def create_torrent_from_bytes(
    name: str,
    data: bytes,
    save_dir: Path,
) -> tuple[str, str | None, str, Path]:
    """Create a torrent from in-memory bytes (e.g. manifest.json)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_file = Path(tmp) / name
        tmp_file.write_bytes(data)
        return create_torrent_from_file(tmp_file, save_dir)


def file_sha256(path: Path) -> str:
    """Return the lowercase hex SHA-256 of a file's raw content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
