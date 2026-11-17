"""Slot planner.

Finds publish times inside each network's posting windows, respecting a daily
quota per network and a minimum gap between *any* two posts (so you never
dump three clips in the same ten minutes). Times are timezone-aware.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config import Config, NetworkRule
from ..models import Network


def _parse_window(w: str) -> tuple[time, time]:
    a, b = w.split("-")
    return time.fromisoformat(a), time.fromisoformat(b)


class SlotPlanner:
    def __init__(self, cfg: Config, now: datetime | None = None, step_minutes: int = 15):
        self.cfg = cfg
        self.tz = ZoneInfo(cfg.timezone)
        self.now = (now or datetime.now(self.tz)).astimezone(self.tz)
        self.gap = timedelta(minutes=cfg.min_gap_minutes)
        self.step = timedelta(minutes=step_minutes)
        self._taken: list[datetime] = []
        self._per_day: dict[tuple[Network, date], int] = defaultdict(int)

    def preload(self, network: Network, slots: list[datetime]) -> None:
        for s in slots:
            s = s.astimezone(self.tz)
            self._taken.append(s)
            self._per_day[(network, s.date())] += 1

    def _free(self, t: datetime) -> bool:
        return all(abs(t - other) >= self.gap for other in self._taken)

    def _candidates(self, rule: NetworkRule, day: date):
        for w in rule.windows:
            start, end = _parse_window(w)
            t = datetime.combine(day, start, self.tz)
            stop = datetime.combine(day, end, self.tz)
            while t <= stop:
                yield t
                t += self.step

    def next_slot(self, network: Network) -> datetime | None:
        rule = self.cfg.networks.get(network)
        if not rule or not rule.enabled:
            return None
        for offset in range(self.cfg.horizon_days):
            day = (self.now + timedelta(days=offset)).date()
            if self._per_day[(network, day)] >= rule.posts_per_day:
                continue
            for t in self._candidates(rule, day):
                if t > self.now + timedelta(minutes=10) and self._free(t):
                    self._taken.append(t)
                    self._per_day[(network, day)] += 1
                    return t
        return None
