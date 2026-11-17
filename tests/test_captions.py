from pathlib import Path

import httpx
import pytest
import respx

from clip_autopilot.captions import (
    AnthropicProvider,
    ResilientCaptioner,
    TemplateProvider,
    parse_caption,
)
from clip_autopilot.config import CaptionConfig
from clip_autopilot.models import Clip, Network

CLIP = Clip(id="abc", name="wz_quad_wipe.mp4", path=Path("x.mp4"), content_hash="h",
            game="Warzone", tags=["quad", "wipe"])


def test_parse_caption_handles_fences_and_cleans_tags():
    raw = (
        'Sure!\n```json\n{"hook":"Quad wipe","body":"no words",'
        '"hashtags":["#WarZone","cod!","cod"]}\n```'
    )
    cap = parse_caption(raw, max_tags=5)
    assert cap.hook == "Quad wipe"
    assert cap.hashtags == ["warzone", "cod"]


def test_parse_caption_rejects_garbage():
    with pytest.raises(ValueError):
        parse_caption("no json here", 5)


@respx.mock
def test_anthropic_provider_success():
    respx.post(AnthropicProvider.URL).mock(return_value=httpx.Response(200, json={
        "content": [{"type": "text", "text": '{"hook":"h","body":"b","hashtags":["fps"]}'}]}))
    cap = AnthropicProvider(api_key="k").generate(CLIP, CaptionConfig())
    assert cap.hook == "h" and cap.hashtags == ["fps"]


@respx.mock
def test_resilient_falls_back_on_api_error():
    respx.post(AnthropicProvider.URL).mock(return_value=httpx.Response(529))
    cap_r = ResilientCaptioner(AnthropicProvider(api_key="k"), TemplateProvider(seed=1))
    cap = cap_r.generate(CLIP, CaptionConfig(max_hashtags=4))
    assert cap_r.failures == 1
    assert "warzone" in cap.hashtags and len(cap.hashtags) <= 4


def test_render_truncates_and_hides_tags_on_youtube():
    cap = TemplateProvider(seed=0).generate(CLIP, CaptionConfig())
    assert "#" not in cap.render(Network.YOUTUBE)
    assert len(cap.render(Network.X, max_len=40)) == 40
