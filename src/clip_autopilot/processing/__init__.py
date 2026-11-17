"""ffmpeg-based reframing: any input -> 9:16, loudness-normalised, trimmed."""

from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from ..config import ProcessingConfig
from ..models import MediaInfo


class FFmpegError(RuntimeError):
    pass


def probe(path: Path) -> MediaInfo:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
           str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise FFmpegError(out.stderr.strip())
    return parse_probe(json.loads(out.stdout))


def parse_probe(data: dict) -> MediaInfo:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError("no video stream")
    rotation = _rotation(video)
    w, h = int(video["width"]), int(video["height"])
    if rotation in (90, 270):
        w, h = h, w
    fps = float(Fraction(video.get("avg_frame_rate") or "0/1")) if video.get(
        "avg_frame_rate", "0/0") != "0/0" else 0.0
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return MediaInfo(width=w, height=h, duration=duration, fps=fps, has_audio=has_audio)


def _rotation(stream: dict) -> int:
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            return abs(int(sd["rotation"])) % 360
    return abs(int(stream.get("tags", {}).get("rotate", 0))) % 360


def build_filtergraph(info: MediaInfo, cfg: ProcessingConfig) -> str:
    """Vertical output. Landscape gameplay gets a blurred fill behind a centred frame."""
    W, H = cfg.target_width, cfg.target_height
    if info.is_vertical or not cfg.blur_background:
        return (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1[v]")
    return (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.08[bgb];"
        f"[fg]scale={W}:-2[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
    )


def build_command(src: Path, dst: Path, info: MediaInfo, cfg: ProcessingConfig) -> list[str]:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    cmd += ["-filter_complex", build_filtergraph(info, cfg), "-map", "[v]"]
    if info.has_audio:
        cmd += ["-map", "0:a:0", "-af", f"loudnorm=I={cfg.loudness_lufs}:TP=-1.5:LRA=11",
                "-c:a", "aac", "-b:a", "160k"]
    else:
        cmd += ["-an"]
    if info.duration > cfg.max_duration:
        cmd += ["-t", f"{cfg.max_duration:.2f}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(dst)]
    return cmd


def render(src: Path, cfg: ProcessingConfig, dry_run: bool = False) -> Path:
    if not shutil.which("ffmpeg"):
        raise FFmpegError("ffmpeg not found on PATH")
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    dst = cfg.output_dir / f"{src.stem}_vertical.mp4"
    info = probe(src)
    cmd = build_command(src, dst, info, cfg)
    if dry_run:
        return dst
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise FFmpegError(res.stderr.strip())
    return dst
