from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .captions import ResilientCaptioner
from .config import Config
from .models import Clip, ScheduledPost
from .publishers import Publisher
from .scheduling import SlotPlanner
from .sources import ClipSource
from .state import StateStore

log = logging.getLogger(__name__)

Renderer = Callable[[Path], Path]
Uploader = Callable[[Path], str]


@dataclass
class RunReport:
    scheduled: list[ScheduledPost] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (f"scheduled={len(self.scheduled)} skipped={len(self.skipped)} "
                f"errors={len(self.errors)}")


class Pipeline:
    def __init__(self, cfg: Config, source: ClipSource, captioner: ResilientCaptioner,
                 publisher: Publisher, state: StateStore, render: Renderer,
                 upload: Uploader, now: datetime | None = None):
        self.cfg = cfg
        self.source = source
        self.captioner = captioner
        self.publisher = publisher
        self.state = state
        self.render = render
        self.upload = upload
        self.planner = SlotPlanner(cfg, now=now)
        since = self.planner.now - timedelta(days=1)
        for net in cfg.networks:
            self.planner.preload(net, self.state.booked_slots(net, since))

    def _process(self, clip: Clip, report: RunReport) -> None:
        pending = [n for n, r in self.cfg.networks.items()
                   if r.enabled and not self.state.already_posted(clip.content_hash, n)]
        if not pending:
            report.skipped.append((clip.name, "already scheduled everywhere"))
            return

        rendered = self.render(clip.path)
        media_url = self.upload(rendered)
        caption = self.captioner.generate(clip, self.cfg.captions)

        for net in pending:
            slot = self.planner.next_slot(net)
            if slot is None:
                report.skipped.append((clip.name, f"no free slot on {net.value}"))
                continue
            rule = self.cfg.networks[net]
            post = ScheduledPost(clip_id=clip.id, network=net, publish_at=slot,
                                 text=caption.render(net, rule.max_caption), media_path=rendered)
            post.external_id = self.publisher.schedule(post, media_url)
            self.state.record(clip.content_hash, post)
            report.scheduled.append(post)
            log.info("scheduled %s on %s at %s", clip.name, net.value, slot.isoformat())

    def run(self, limit: int | None = None) -> RunReport:
        report = RunReport()
        for i, clip in enumerate(self.source.discover()):
            if limit is not None and i >= limit:
                break
            try:
                self._process(clip, report)
            except Exception as exc:  # one bad clip must never kill the run
                log.exception("failed on %s", clip.name)
                report.errors.append((clip.name, str(exc)))
        return report
