"""Caption generation with pluggable LLM providers and a deterministic fallback."""

from __future__ import annotations

import json
import os
import random
import re
from typing import Protocol

import httpx

from ..config import CaptionConfig
from ..models import Caption, Clip

SYSTEM = (
    "You write captions for short-form gaming clips. Return ONLY JSON: "
    '{"hook": str (max 70 chars), "body": str (max 160 chars), "hashtags": [str]}. '
    "No emojis spam, no clickbait lies, never invent kills or stats that are not given."
)

BASE_TAGS = {
    "Warzone": ["warzone", "callofduty", "cod"],
    "MW4": ["mw4", "callofduty", "cod"],
    "GTA 6": ["gta6", "gta", "rockstar"],
}


class CaptionProvider(Protocol):
    def generate(self, clip: Clip, cfg: CaptionConfig) -> Caption: ...


def _prompt(clip: Clip, cfg: CaptionConfig) -> str:
    return (
        f"Game: {clip.game or 'unknown'}\n"
        f"Clip filename tags: {', '.join(clip.tags) or 'none'}\n"
        f"Voice: {cfg.voice}\n"
        f"Max hashtags: {cfg.max_hashtags}"
    )


def parse_caption(raw: str, max_tags: int) -> Caption:
    """Tolerates code fences / prose around the JSON the model returns."""
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("no JSON object in model output")
    data = json.loads(match.group(0))
    tags = [re.sub(r"[^a-z0-9_]", "", t.lower().lstrip("#")) for t in data.get("hashtags", [])]
    tags = list(dict.fromkeys(t for t in tags if t))[:max_tags]
    return Caption(hook=data["hook"].strip()[:70], body=data.get("body", "").strip()[:160],
                   hashtags=tags)


class AnthropicProvider:
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, client: httpx.Client | None = None, api_key: str | None = None):
        self.client = client or httpx.Client(timeout=30)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def generate(self, clip: Clip, cfg: CaptionConfig) -> Caption:
        r = self.client.post(
            self.URL,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json={"model": cfg.model, "max_tokens": 300, "system": SYSTEM,
                  "messages": [{"role": "user", "content": _prompt(clip, cfg)}]},
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json()["content"])
        return parse_caption(text, cfg.max_hashtags)


class OpenAIProvider:
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, client: httpx.Client | None = None, api_key: str | None = None):
        self.client = client or httpx.Client(timeout=30)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def generate(self, clip: Clip, cfg: CaptionConfig) -> Caption:
        r = self.client.post(
            self.URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": cfg.model, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": _prompt(clip, cfg)}]},
        )
        r.raise_for_status()
        return parse_caption(r.json()["choices"][0]["message"]["content"], cfg.max_hashtags)


class TemplateProvider:
    """Offline fallback so the pipeline never stalls on an API outage."""

    HOOKS = [
        "Did not expect that to work 😭",
        "Watch till the end",
        "This lobby was NOT ready",
        "Clean or lucky? You decide",
    ]

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def generate(self, clip: Clip, cfg: CaptionConfig) -> Caption:
        tags = BASE_TAGS.get(clip.game or "", ["gaming"]) + clip.tags
        body = f"{clip.game} clip" if clip.game else "New clip"
        if clip.tags:
            body += " · " + " ".join(clip.tags[:3])
        return Caption(hook=self.rng.choice(self.HOOKS), body=body,
                       hashtags=list(dict.fromkeys(tags))[: cfg.max_hashtags])


class ResilientCaptioner:
    """Primary provider with automatic fallback; merges in base game hashtags."""

    def __init__(self, primary: CaptionProvider, fallback: CaptionProvider | None = None):
        self.primary = primary
        self.fallback = fallback or TemplateProvider()
        self.failures = 0

    def generate(self, clip: Clip, cfg: CaptionConfig) -> Caption:
        try:
            cap = self.primary.generate(clip, cfg)
        except (httpx.HTTPError, ValueError, KeyError) :
            self.failures += 1
            cap = self.fallback.generate(clip, cfg)
        base = BASE_TAGS.get(clip.game or "", [])
        cap.hashtags = list(dict.fromkeys(cap.hashtags + base))[: cfg.max_hashtags]
        return cap


def build_captioner(cfg: CaptionConfig) -> ResilientCaptioner:
    primary: CaptionProvider
    if cfg.provider == "anthropic":
        primary = AnthropicProvider()
    elif cfg.provider == "openai":
        primary = OpenAIProvider()
    else:
        primary = TemplateProvider()
    return ResilientCaptioner(primary)
