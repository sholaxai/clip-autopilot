from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from clip_autopilot.config import Config, NetworkRule
from clip_autopilot.models import Network
from clip_autopilot.scheduling import SlotPlanner

TZ = ZoneInfo("Europe/London")


def cfg(**kw) -> Config:
    return Config(
        min_gap_minutes=kw.get("gap", 60),
        networks={
            Network.TIKTOK: NetworkRule(posts_per_day=2, windows=["18:00-21:00"]),
            Network.YOUTUBE: NetworkRule(posts_per_day=1, windows=["18:00-21:00"]),
        },
    )


def test_first_slot_is_window_start():
    now = datetime(2026, 11, 17, 9, 0, tzinfo=TZ)
    p = SlotPlanner(cfg(), now=now)
    assert p.next_slot(Network.TIKTOK) == datetime(2026, 11, 17, 18, 0, tzinfo=TZ)


def test_min_gap_enforced_across_networks():
    now = datetime(2026, 11, 17, 9, 0, tzinfo=TZ)
    p = SlotPlanner(cfg(gap=60), now=now)
    a = p.next_slot(Network.TIKTOK)
    b = p.next_slot(Network.YOUTUBE)
    c = p.next_slot(Network.TIKTOK)
    slots = sorted([a, b, c])
    assert all(y - x >= timedelta(minutes=60) for x, y in zip(slots, slots[1:], strict=False))


def test_daily_quota_rolls_to_next_day():
    now = datetime(2026, 11, 17, 9, 0, tzinfo=TZ)
    p = SlotPlanner(cfg(), now=now)
    p.next_slot(Network.YOUTUBE)
    nxt = p.next_slot(Network.YOUTUBE)
    assert nxt.date() == datetime(2026, 11, 18).date()


def test_past_windows_skipped():
    now = datetime(2026, 11, 17, 22, 0, tzinfo=TZ)
    p = SlotPlanner(cfg(), now=now)
    assert p.next_slot(Network.TIKTOK).date().day == 18


def test_preloaded_slots_respected():
    now = datetime(2026, 11, 17, 9, 0, tzinfo=TZ)
    p = SlotPlanner(cfg(), now=now)
    p.preload(Network.YOUTUBE, [datetime(2026, 11, 17, 18, 0, tzinfo=TZ)])
    assert p.next_slot(Network.YOUTUBE).date().day == 18
    assert p.next_slot(Network.TIKTOK) == datetime(2026, 11, 17, 19, 0, tzinfo=TZ)


def test_disabled_network_returns_none():
    c = cfg()
    c.networks[Network.TIKTOK].enabled = False
    assert SlotPlanner(c).next_slot(Network.TIKTOK) is None
