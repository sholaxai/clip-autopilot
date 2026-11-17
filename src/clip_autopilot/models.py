from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class Network(StrEnum):
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    X = "twitter"
    FACEBOOK = "facebook"


class Clip(BaseModel):
    """A raw clip discovered by a source."""

    id: str
    name: str
    path: Path
    content_hash: str
    game: str | None = None
    tags: list[str] = Field(default_factory=list)


class MediaInfo(BaseModel):
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def is_vertical(self) -> bool:
        return self.aspect <= 0.6


class Caption(BaseModel):
    hook: str
    body: str
    hashtags: list[str] = Field(default_factory=list)

    def render(self, network: Network, max_len: int | None = None) -> str:
        tags = " ".join(f"#{t.lstrip('#')}" for t in self.hashtags)
        text = f"{self.hook}\n\n{self.body}".strip()
        if network is not Network.YOUTUBE and tags:
            text = f"{text}\n\n{tags}"
        if max_len and len(text) > max_len:
            text = text[: max_len - 1].rstrip() + "…"
        return text


class ScheduledPost(BaseModel):
    clip_id: str
    network: Network
    publish_at: datetime
    text: str
    media_path: Path
    external_id: str | None = None
