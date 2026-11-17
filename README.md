# clip-autopilot

![ci](https://github.com/sholaxai/clip-autopilot/actions/workflows/ci.yml/badge.svg)

Drop gameplay clips in a folder and get them reframed, captioned and scheduled across TikTok, YouTube Shorts, Instagram Reels and X with no manual editing.

```
Google Drive / local folder
        │  discover + content-hash dedupe
        ▼
   ffmpeg reframe ──► 9:16, blurred fill for landscape, -14 LUFS, ≤59s
        │
        ▼
   LLM captioner ──► Claude / OpenAI → strict JSON → template fallback
        │
        ▼
   slot planner  ──► per-network windows, daily quotas, global min gap, tz-aware
        │
        ▼
   Metricool API ──► retries + backoff, state written to SQLite (idempotent reruns)
```

## Features

- **Smart reframing:** landscape gameplay is centred over a blurred, darkened copy of itself rather than cropped, so HUD and killfeed stay visible. Rotation metadata from phone recordings is handled.
- **Loudness normalisation** to platform targets with `loudnorm`. Clips without audio stay silent.
- **Caption generation** through Anthropic or OpenAI with a strict JSON contract. If a provider errors or returns junk, it falls back to a deterministic template so a run never stalls.
- **Game detection from filenames:** `wz_quad-wipe.mp4` becomes Warzone with tags `quad` and `wipe`, and game-specific hashtags are merged in automatically.
- **Constraint-based scheduler:** posting windows per network, a daily quota, and a minimum gap between *any* two posts across all networks. Already-booked slots are reloaded from state.
- **Idempotent:** content-hash × network is the primary key, so rerunning never double-posts.
- **Fault isolation:** a corrupt clip is reported and skipped and the rest of the run carries on.
- Runs from the CLI, Docker, or a scheduled GitHub Action.

## Quick start

```bash
pip install -e ".[dev]"
cp config.example.yaml config.yaml && cp .env.example .env   # fill these in
clip-autopilot validate -c config.yaml
clip-autopilot run -c config.yaml --dry-run       # plan without posting
clip-autopilot run -c config.yaml                 # go live
```

Docker:

```bash
docker build -t clip-autopilot .
docker run --env-file .env -v $PWD:/config clip-autopilot
```

## Layout

| Module | Job |
|---|---|
| `sources/` | Local folder + Google Drive REST source, filename metadata inference |
| `processing/` | ffprobe parsing, filtergraph builder, render |
| `captions/` | Provider protocol, Anthropic/OpenAI/template providers, resilient wrapper |
| `scheduling/` | `SlotPlanner`, a greedy constraint solver over time windows |
| `publishers/` | Metricool client with retry/backoff, dry-run publisher |
| `state.py` | SQLite store for dedupe and booked slots |
| `pipeline.py` | Orchestration and run report |

## Tests

```bash
pytest -q        # includes an end-to-end ffmpeg render if ffmpeg is installed
ruff check .
```

## License

MIT
