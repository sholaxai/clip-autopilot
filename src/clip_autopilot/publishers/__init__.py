"""Publishers. Metricool is the default; a dry-run publisher logs instead."""

from __future__ import annotations

import logging
import os
import time
from typing import Protocol

import httpx

from ..models import Network, ScheduledPost

log = logging.getLogger(__name__)


class Publisher(Protocol):
    def schedule(self, post: ScheduledPost, media_url: str) -> str: ...


class DryRunPublisher:
    def __init__(self):
        self.calls: list[ScheduledPost] = []

    def schedule(self, post: ScheduledPost, media_url: str) -> str:
        self.calls.append(post)
        log.info("[dry-run] %s @ %s: %s", post.network, post.publish_at, post.text[:60])
        return f"dry-{len(self.calls)}"


class MetricoolPublisher:
    BASE = "https://app.metricool.com/api"

    def __init__(self, user_id: str | None = None, blog_id: str | None = None,
                 token: str | None = None, client: httpx.Client | None = None,
                 max_retries: int = 3, backoff: float = 1.5):
        self.user_id = user_id or os.environ["METRICOOL_USER_ID"]
        self.blog_id = blog_id or os.environ["METRICOOL_BLOG_ID"]
        self.token = token or os.environ["METRICOOL_TOKEN"]
        self.client = client or httpx.Client(timeout=30)
        self.max_retries = max_retries
        self.backoff = backoff

    def _payload(self, post: ScheduledPost, media_url: str) -> dict:
        body: dict = {
            "publicationDate": {"dateTime": post.publish_at.strftime("%Y-%m-%dT%H:%M:%S"),
                                "timezone": str(post.publish_at.tzinfo)},
            "text": post.text,
            "providers": [{"network": post.network.value}],
            "media": [media_url],
            "autoPublish": True,
        }
        if post.network is Network.YOUTUBE:
            body["youtubeData"] = {"title": post.text.split("\n")[0][:100], "type": "SHORT",
                                   "privacy": "PUBLIC"}
        if post.network is Network.INSTAGRAM:
            body["instagramData"] = {"type": "REEL", "showReelOnFeed": True}
        if post.network is Network.TIKTOK:
            body["tiktokData"] = {"privacyOption": "PUBLIC_TO_EVERYONE"}
        return body

    def schedule(self, post: ScheduledPost, media_url: str) -> str:
        params = {"userId": self.user_id, "blogId": self.blog_id}
        headers = {"X-Mc-Auth": self.token}
        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.client.post(f"{self.BASE}/v2/scheduler/posts", params=params,
                                     headers=headers, json=self._payload(post, media_url))
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                r.raise_for_status()
                return str(r.json().get("data", {}).get("id", ""))
            except httpx.HTTPError:
                if attempt == self.max_retries:
                    raise
                time.sleep(self.backoff ** attempt)
        raise RuntimeError("unreachable")
