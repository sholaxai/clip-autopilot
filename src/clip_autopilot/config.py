from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from .models import Network


class SourceConfig(BaseModel):
    kind: Literal["local", "gdrive"] = "local"
    path: Path | None = None
    folder_id: str | None = None
    extensions: list[str] = Field(default_factory=lambda: [".mp4", ".mov", ".mkv"])


class ProcessingConfig(BaseModel):
    target_width: int = 1080
    target_height: int = 1920
    max_duration: float = 59.0
    loudness_lufs: float = -14.0
    blur_background: bool = True
    output_dir: Path = Path("out")


class CaptionConfig(BaseModel):
    provider: Literal["anthropic", "openai", "template"] = "anthropic"
    model: str = "claude-sonnet-4-5"
    voice: str = "confident, funny, short sentences, UK slang ok, no cringe"
    max_hashtags: int = 5


class NetworkRule(BaseModel):
    enabled: bool = True
    posts_per_day: int = 1
    windows: list[str] = Field(default_factory=lambda: ["18:00-21:00"])
    max_caption: int | None = None

    @field_validator("windows")
    @classmethod
    def _check_windows(cls, v: list[str]) -> list[str]:
        for w in v:
            start, end = w.split("-")
            if start >= end:
                raise ValueError(f"window {w!r} must start before it ends")
        return v


class Config(BaseModel):
    timezone: str = "Europe/London"
    min_gap_minutes: int = 90
    horizon_days: int = 7
    source: SourceConfig = SourceConfig()
    processing: ProcessingConfig = ProcessingConfig()
    captions: CaptionConfig = CaptionConfig()
    networks: dict[Network, NetworkRule] = Field(
        default_factory=lambda: {Network.TIKTOK: NetworkRule(), Network.YOUTUBE: NetworkRule()}
    )
    state_db: Path = Path(".clip-autopilot.db")

    @classmethod
    def load(cls, path: str | Path) -> Config:
        raw = yaml.safe_load(Path(path).read_text()) or {}
        return cls.model_validate(_expand_env(raw))


def _expand_env(value):
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value
