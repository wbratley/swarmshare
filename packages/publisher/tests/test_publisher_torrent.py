from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from meshplay_publisher.torrent import (
    create_torrent_from_bytes,
    create_torrent_from_file,
    file_sha256,
)


@pytest.fixture
def small_video(tmp_path: Path) -> Path:
    """Create a small fake video file (100 KB of random-ish bytes)."""
    path = tmp_path / "test.mp4"
    # Deterministic content: repeated pattern to keep tests fast
    path.write_bytes(bytes(range(256)) * 400)
    return path


class TestCreateTorrentFromFile:
    def test_returns_four_tuple(self, small_video: Path, tmp_path: Path) -> None:
        result = create_torrent_from_file(small_video, tmp_path / "torrents")
        assert len(result) == 4

    def test_infohash_v2_is_64_hex(self, small_video: Path, tmp_path: Path) -> None:
        v2, *_ = create_torrent_from_file(small_video, tmp_path / "torrents")
        assert len(v2) == 64
        assert all(c in "0123456789abcdef" for c in v2)

    def test_infohash_v1_is_40_hex_or_none(self, small_video: Path, tmp_path: Path) -> None:
        _, v1, *_ = create_torrent_from_file(small_video, tmp_path / "torrents")
        if v1 is not None:
            assert len(v1) == 40
            assert all(c in "0123456789abcdef" for c in v1)

    def test_magnet_contains_infohash(self, small_video: Path, tmp_path: Path) -> None:
        v2, v1, magnet, _ = create_torrent_from_file(small_video, tmp_path / "torrents")
        # magnet should reference at least one of the infohashes
        assert v2 in magnet or (v1 is not None and v1 in magnet)

    def test_torrent_file_created(self, small_video: Path, tmp_path: Path) -> None:
        v2, _, _, torrent_path = create_torrent_from_file(small_video, tmp_path / "torrents")
        assert torrent_path.exists()
        assert torrent_path.suffix == ".torrent"

    def test_torrent_filename_contains_infohash(self, small_video: Path, tmp_path: Path) -> None:
        v2, _, _, torrent_path = create_torrent_from_file(small_video, tmp_path / "torrents")
        assert v2 in torrent_path.name

    def test_deterministic_same_file(self, small_video: Path, tmp_path: Path) -> None:
        v2_a, v1_a, _, _ = create_torrent_from_file(small_video, tmp_path / "a")
        v2_b, v1_b, _, _ = create_torrent_from_file(small_video, tmp_path / "b")
        assert v2_a == v2_b
        assert v1_a == v1_b

    def test_different_files_different_infohash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.mp4"
        f2 = tmp_path / "b.mp4"
        f1.write_bytes(b"content_a" * 1000)
        f2.write_bytes(b"content_b" * 1000)
        v2_a, *_ = create_torrent_from_file(f1, tmp_path / "ta")
        v2_b, *_ = create_torrent_from_file(f2, tmp_path / "tb")
        assert v2_a != v2_b

    def test_save_dir_created_if_missing(self, small_video: Path, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "deep" / "torrents"
        assert not target.exists()
        create_torrent_from_file(small_video, target)
        assert target.exists()


class TestCreateTorrentFromBytes:
    def test_roundtrip(self, tmp_path: Path) -> None:
        data = b'{"mfst": "test"}' * 100
        v2, v1, magnet, path = create_torrent_from_bytes("manifest.json", data, tmp_path)
        assert len(v2) == 64
        assert path.exists()

    def test_different_data_different_infohash(self, tmp_path: Path) -> None:
        v2_a, *_ = create_torrent_from_bytes("f.json", b"data_a" * 100, tmp_path / "a")
        v2_b, *_ = create_torrent_from_bytes("f.json", b"data_b" * 100, tmp_path / "b")
        assert v2_a != v2_b


class TestFileSha256:
    def test_matches_hashlib(self, small_video: Path) -> None:
        expected = hashlib.sha256(small_video.read_bytes()).hexdigest()
        assert file_sha256(small_video) == expected

    def test_is_64_hex(self, small_video: Path) -> None:
        result = file_sha256(small_video)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)
