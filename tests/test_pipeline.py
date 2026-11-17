from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from clip_autopilot.captions import ResilientCaptioner, TemplateProvider
from clip_autopilot.config import Config, NetworkRule
from clip_autopilot.models import Clip, Network
from clip_autopilot.pipeline import Pipeline
from clip_autopilot.publishers import DryRunPublisher
from clip_autopilot.sources import infer_metadata
from clip_autopilot.state import StateStore

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=ZoneInfo("Europe/London"))


class ListSource:
    def __init__(self, clips):
        self.clips = clips

    def discover(self):
        yield from self.clips


def make_clip(i: int, bad: bool = False) -> Clip:
    return Clip(id=f"c{i}", name="BAD" if bad else f"wz_clip_{i}.mp4", path=Path(f"{i}.mp4"),
                content_hash=f"hash{i}", game="Warzone")


def build(clips, state=None):
    cfg = Config(networks={Network.TIKTOK: NetworkRule(posts_per_day=3),
                           Network.YOUTUBE: NetworkRule(posts_per_day=1)}, min_gap_minutes=30)

    def render(p: Path) -> Path:
        if p.name == "99.mp4":
            raise RuntimeError("corrupt file")
        return p

    pub = DryRunPublisher()
    pipe = Pipeline(cfg, ListSource(clips), ResilientCaptioner(TemplateProvider(seed=3)), pub,
                    state or StateStore(), render, lambda p: f"https://cdn/{p.name}", now=NOW)
    return pipe, pub


def test_schedules_and_is_idempotent():
    state = StateStore()
    pipe, pub = build([make_clip(1), make_clip(2)], state)
    r1 = pipe.run()
    assert len(r1.scheduled) == 4
    yt_days = {p.publish_at.date() for p in r1.scheduled if p.network is Network.YOUTUBE}
    assert len(yt_days) == 2  # 1/day quota pushes the second Short to tomorrow

    pipe2, _ = build([make_clip(1), make_clip(2)], state)
    r2 = pipe2.run()
    assert r2.scheduled == [] and len(r2.skipped) == 2


def test_bad_clip_does_not_kill_run():
    pipe, _ = build([make_clip(99), make_clip(1)])
    r = pipe.run()
    assert len(r.errors) == 1 and r.scheduled


def test_infer_metadata():
    game, tags = infer_metadata("GTA6_heist-escape_01.mp4")
    assert game == "GTA 6" and tags == ["heist", "escape"]
