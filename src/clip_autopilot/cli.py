from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import __version__
from .captions import build_captioner
from .config import Config
from .pipeline import Pipeline
from .processing import render
from .publishers import DryRunPublisher, MetricoolPublisher
from .sources import build_source
from .state import StateStore


def _uploader(base_url: str | None):
    """Metricool needs a public URL. Point MEDIA_BASE_URL at a bucket/CDN synced to out/."""

    def upload(path: Path) -> str:
        if not base_url:
            return path.resolve().as_uri()
        return f"{base_url.rstrip('/')}/{path.name}"

    return upload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="clip-autopilot", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="discover, render, caption and schedule clips")
    run.add_argument("-c", "--config", default="config.yaml")
    run.add_argument("--dry-run", action="store_true", help="plan everything, post nothing")
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("-v", "--verbose", action="store_true")

    plan = sub.add_parser("validate", help="validate a config file")
    plan.add_argument("-c", "--config", default="config.yaml")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    cfg = Config.load(args.config)
    if args.cmd == "validate":
        enabled = [n.value for n, r in cfg.networks.items() if r.enabled]
        print(f"ok: source={cfg.source.kind} networks={','.join(enabled)} tz={cfg.timezone}")
        return 0

    publisher = DryRunPublisher() if args.dry_run else MetricoolPublisher()
    state = StateStore(":memory:" if args.dry_run else cfg.state_db)
    pipe = Pipeline(
        cfg,
        source=build_source(cfg.source),
        captioner=build_captioner(cfg.captions),
        publisher=publisher,
        state=state,
        render=lambda src: render(src, cfg.processing, dry_run=args.dry_run),
        upload=_uploader(os.environ.get("MEDIA_BASE_URL")),
    )
    report = pipe.run(limit=args.limit)
    print(report.summary())
    for post in report.scheduled:
        print(f"  {post.publish_at:%a %d %b %H:%M}  {post.network.value:<10} {post.clip_id}")
    for name, why in report.errors:
        print(f"  ERROR {name}: {why}", file=sys.stderr)
    return 1 if report.errors and not report.scheduled else 0


if __name__ == "__main__":
    raise SystemExit(main())
