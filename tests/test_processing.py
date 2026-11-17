import shutil
import subprocess
from pathlib import Path

import pytest

from clip_autopilot.config import ProcessingConfig
from clip_autopilot.models import MediaInfo
from clip_autopilot.processing import build_command, parse_probe, probe, render

LANDSCAPE = MediaInfo(width=1920, height=1080, duration=75, fps=60, has_audio=True)
VERTICAL = MediaInfo(width=1080, height=1920, duration=20, fps=30, has_audio=False)


def test_parse_probe_handles_rotation():
    data = {"streams": [{"codec_type": "video", "width": 1920, "height": 1080,
                         "avg_frame_rate": "60/1", "side_data_list": [{"rotation": -90}]}],
            "format": {"duration": "12.5"}}
    info = parse_probe(data)
    assert (info.width, info.height, info.fps) == (1080, 1920, 60.0)
    assert info.is_vertical and not info.has_audio


def test_landscape_gets_blur_fill_trim_and_loudnorm():
    cmd = " ".join(build_command(Path("a.mp4"), Path("b.mp4"), LANDSCAPE, ProcessingConfig()))
    assert "boxblur" in cmd and "overlay" in cmd
    assert "loudnorm=I=-14.0" in cmd
    assert "-t 59.00" in cmd


def test_vertical_is_cropped_and_silent():
    cmd = build_command(Path("a.mp4"), Path("b.mp4"), VERTICAL, ProcessingConfig())
    assert "-an" in cmd and "-t" not in cmd
    assert "boxblur" not in " ".join(cmd)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_end_to_end_render(tmp_path):
    src = tmp_path / "wz_test.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=640x360:rate=30:duration=2", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-shortest", str(src)], check=True)
    cfg = ProcessingConfig(target_width=270, target_height=480, output_dir=tmp_path / "out")
    out = render(src, cfg)
    info = probe(out)
    assert (info.width, info.height) == (270, 480) and info.has_audio
