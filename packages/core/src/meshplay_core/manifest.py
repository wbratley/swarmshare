from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

_HEX40 = r"^[0-9a-f]{40}$"
_HEX64 = r"^[0-9a-f]{64}$"
_HEX128 = r"^[0-9a-f]{128}$"


class ChannelInfo(BaseModel):
    pubkey: str = Field(pattern=_HEX64)
    name: str
    description: str = ""


class VideoEntry(BaseModel):
    id: UUID
    title: str
    infohash_v2: str = Field(pattern=_HEX64)
    infohash_v1: str | None = Field(default=None, pattern=_HEX40)
    sha256: str = Field(pattern=_HEX64)
    magnet: str
    published_at: datetime
    duration_seconds: int | None = None
    size_bytes: int | None = None
    mime_type: str = "video/mp4"

    @field_validator("published_at", mode="after")
    @classmethod
    def must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("published_at must be timezone-aware (UTC)")
        return v.astimezone(UTC)


class Manifest(BaseModel):
    version: int = 1
    channel: ChannelInfo
    seq: int = Field(ge=0)
    videos: list[VideoEntry] = Field(default_factory=list)
    signature: str | None = Field(default=None, pattern=_HEX128)

    @model_validator(mode="after")
    def pubkey_matches_channel(self) -> Manifest:
        return self

    def canonical_bytes(self) -> bytes:
        """Deterministic UTF-8 JSON of the manifest, excluding the signature field.

        seq is included so that a lower-seq manifest cannot be substituted for a
        higher-seq one without invalidating the signature (anti-replay).
        """
        data = self.model_dump(mode="json", exclude={"signature"})
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
