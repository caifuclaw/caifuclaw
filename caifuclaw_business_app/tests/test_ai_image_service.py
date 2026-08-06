# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import base64
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.ai_image_service import (
    AiSplitRegion,
    ImageApiConfig,
    AiImageError,
    build_ai_split_messages,
    call_image_api,
    merge_images,
    parse_ai_split_regions,
    refine_ai_split_regions,
    split_image,
)


def _write_image(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]) -> None:
    image = Image.new("RGBA", size, color)
    image.save(path, format="PNG")


def test_split_image_supports_long_and_grid_modes(tmp_path):
    source = tmp_path / "source.png"
    _write_image(source, (120, 260), (12, 96, 128, 255))

    long_outputs = split_image(
        source,
        tmp_path / "long",
        split_mode="long",
        max_height=128,
        rows=2,
        columns=2,
        output_format="png",
    )
    assert len(long_outputs) == 3
    assert [Image.open(path).size for path in long_outputs] == [(120, 128), (120, 128), (120, 4)]

    grid_outputs = split_image(
        source,
        tmp_path / "grid",
        split_mode="grid",
        max_height=100,
        rows=2,
        columns=3,
        output_format="jpeg",
        output_compression=80,
    )
    assert len(grid_outputs) == 6
    assert Image.open(grid_outputs[0]).size == (40, 130)
    assert Image.open(grid_outputs[-1]).size == (40, 130)


def test_build_ai_split_messages_embeds_preview_and_instruction(tmp_path):
    source = tmp_path / "source.png"
    _write_image(source, (240, 120), (12, 96, 128, 180))

    messages = build_ai_split_messages(source, "标题和商品图保持在同一区域")

    assert messages[0]["role"] == "system"
    assert "覆盖从开头到结尾的全部有效内容" in messages[0]["content"]
    user_content = messages[1]["content"]
    assert "标题和商品图保持在同一区域" in user_content[0]["text"]
    assert '"original_width": 240' in user_content[0]["text"]
    assert '"max_aspect_ratio"' not in user_content[0]["text"]
    assert "不负责决定裁剪尺寸或目标长宽比" in messages[0]["content"]
    assert user_content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert user_content[1]["image_url"]["detail"] == "high"


def test_build_ai_split_messages_adds_detail_tiles_for_long_images(tmp_path):
    source = tmp_path / "long.png"
    _write_image(source, (400, 2400), (12, 96, 128, 255))

    messages = build_ai_split_messages(source)

    user_content = messages[1]["content"]
    image_parts = [item for item in user_content if item["type"] == "image_url"]
    tile_descriptions = [item["text"] for item in user_content if item["type"] == "text"][1:]
    assert 2 < len(image_parts) <= 9
    assert any('"top": 0' in text for text in tile_descriptions)
    assert any('"bottom": 2400' in text for text in tile_descriptions)
    assert all("不要把分段自身的顶部或底部当作内容边界" in text for text in tile_descriptions)


def test_parse_ai_split_regions_filters_low_confidence_full_canvas_and_duplicates():
    model_text = """```json
    {
      "regions": [
        {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000, "confidence": 0.99},
        {"x1": 0, "y1": 0, "x2": 1000, "y2": 480, "confidence": 0.96, "label": "上图"},
        {"x1": 0, "y1": 500, "x2": 1000, "y2": 1000, "confidence": 92, "label": "下图"},
        {"x1": 5, "y1": 5, "x2": 995, "y2": 475, "confidence": 0.80},
        {"x1": 100, "y1": 100, "x2": 200, "y2": 200, "confidence": 0.20}
      ]
    }
    ```"""

    regions = parse_ai_split_regions(model_text, image_width=1000, image_height=800)

    assert regions == [
        AiSplitRegion(0, 0, 1000, 384, 0.96, "上图"),
        AiSplitRegion(0, 400, 1000, 800, 0.92, "下图"),
    ]


def test_parse_ai_split_regions_requires_two_reliable_regions():
    with pytest.raises(AiImageError, match="至少两张"):
        parse_ai_split_regions(
            '{"regions":[{"x1":0,"y1":0,"x2":1000,"y2":500,"confidence":0.9}]}',
            image_width=600,
            image_height=800,
        )


def test_split_image_crops_ai_regions_from_original(tmp_path):
    source = tmp_path / "source.png"
    image = Image.new("RGBA", (120, 200), (220, 40, 40, 255))
    image.paste((40, 80, 220, 255), (0, 100, 120, 200))
    image.save(source, format="PNG")
    regions = [
        AiSplitRegion(0, 0, 120, 100, 0.95, "top"),
        AiSplitRegion(0, 100, 120, 200, 0.94, "bottom"),
    ]

    outputs = split_image(
        source,
        tmp_path / "ai",
        split_mode="ai",
        max_height=100,
        rows=1,
        columns=1,
        output_format="png",
        regions=regions,
    )

    assert [Image.open(path).size for path in outputs] == [(120, 100), (120, 100)]
    assert Image.open(outputs[0]).getpixel((10, 10)) == (220, 40, 40, 255)
    assert Image.open(outputs[1]).getpixel((10, 10)) == (40, 80, 220, 255)


def test_split_image_preserves_ai_region_dimensions(tmp_path):
    source = tmp_path / "source-wide.png"
    image = Image.new("RGBA", (500, 200), (220, 40, 40, 255))
    image.paste((40, 80, 220, 255), (0, 120, 500, 200))
    image.save(source, format="PNG")
    regions = [
        AiSplitRegion(0, 0, 500, 100, 0.95, "wide"),
        AiSplitRegion(0, 120, 500, 200, 0.94, "footer"),
    ]

    outputs = split_image(
        source,
        tmp_path / "ai-natural",
        split_mode="ai",
        max_height=100,
        rows=1,
        columns=1,
        output_format="png",
        regions=regions,
    )

    sizes = [Image.open(path).size for path in outputs]
    assert sizes == [(500, 100), (500, 80)]


def test_refine_ai_split_regions_snaps_long_image_cuts_to_wide_blank_bands(tmp_path):
    source = tmp_path / "long-detail.png"
    image = Image.new("RGBA", (200, 1200), (255, 255, 255, 255))
    image.paste((40, 120, 220, 255), (10, 20, 190, 270))
    image.paste((220, 80, 40, 255), (10, 380, 190, 690))
    image.paste((60, 170, 90, 255), (10, 810, 190, 1120))
    image.save(source, format="PNG")
    regions = [
        AiSplitRegion(0, 0, 200, 430, 0.95, "top"),
        AiSplitRegion(0, 430, 200, 850, 0.94, "middle"),
        AiSplitRegion(0, 850, 200, 1200, 0.93, "bottom"),
    ]

    refined = refine_ai_split_regions(source, regions)

    assert len(refined) == 3
    assert refined[0].top == 0
    assert 270 <= refined[0].bottom < 380
    assert refined[1].top == refined[0].bottom
    assert 690 <= refined[1].bottom < 810
    assert refined[2].top == refined[1].bottom
    assert refined[2].bottom == 1200


def test_refine_ai_split_regions_does_not_change_non_long_layout(tmp_path):
    source = tmp_path / "collage.png"
    _write_image(source, (600, 400), (12, 96, 128, 255))
    regions = [
        AiSplitRegion(0, 0, 300, 400, 0.95, "left"),
        AiSplitRegion(300, 0, 600, 400, 0.94, "right"),
    ]

    assert refine_ai_split_regions(source, regions) == regions


def test_refine_ai_split_regions_merges_when_a_long_image_cut_has_no_safe_band(tmp_path):
    source = tmp_path / "long-detail-textured.png"
    image = Image.new("RGBA", (200, 1200), (255, 255, 255, 255))
    for left in range(0, 200, 4):
        color = (20, 20, 20, 255) if left % 8 == 0 else (230, 230, 230, 255)
        image.paste(color, (left, 0, left + 4, 700))
        image.paste(color, (left, 800, left + 4, 1200))
    image.save(source, format="PNG")
    regions = [
        AiSplitRegion(0, 0, 200, 400, 0.95, "top"),
        AiSplitRegion(0, 400, 200, 750, 0.94, "middle"),
        AiSplitRegion(0, 750, 200, 1200, 0.93, "bottom"),
    ]

    refined = refine_ai_split_regions(source, regions)

    assert len(refined) == 2
    assert refined[0].label == "top / middle"
    assert refined[0].top == 0
    assert 700 <= refined[0].bottom <= 800
    assert refined[1].top == refined[0].bottom
    assert refined[1].bottom == 1200


def test_refine_ai_split_regions_uses_full_width_scene_change_without_blank_band(tmp_path):
    source = tmp_path / "long-detail-scenes.png"
    image = Image.new("RGBA", (200, 800), (200, 40, 40, 255))
    image.paste((40, 60, 210, 255), (0, 400, 200, 800))
    image.save(source, format="PNG")
    regions = [
        AiSplitRegion(0, 0, 200, 430, 0.95, "red scene"),
        AiSplitRegion(0, 430, 200, 800, 0.94, "blue scene"),
    ]

    refined = refine_ai_split_regions(source, regions)

    assert [(region.top, region.bottom) for region in refined] == [(0, 400), (400, 800)]


def test_merge_images_supports_grid_and_horizontal_layouts(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    third = tmp_path / "third.png"
    _write_image(first, (100, 80), (200, 40, 40, 255))
    _write_image(second, (60, 120), (40, 160, 80, 255))
    _write_image(third, (90, 90), (40, 80, 190, 255))

    grid_output = merge_images(
        [first, second, third],
        tmp_path / "merged-grid.png",
        layout="grid",
        columns=2,
        cell_width=100,
        cell_height=120,
        gap=10,
        background="#ffffff",
        fit_mode="contain",
        output_format="png",
    )
    assert Image.open(grid_output).size == (210, 250)

    horizontal_output = merge_images(
        [first, second],
        tmp_path / "merged-horizontal.jpg",
        layout="horizontal",
        columns=2,
        cell_width=100,
        cell_height=120,
        gap=0,
        background="#000000",
        fit_mode="cover",
        output_format="jpeg",
        output_compression=85,
    )
    assert Image.open(horizontal_output).size == (200, 120)


def test_call_image_api_sends_generation_payload_and_decodes_images(monkeypatch, tmp_path):
    source = tmp_path / "response.png"
    _write_image(source, (16, 16), (10, 20, 30, 255))
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    captured = {}

    class StubClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"data": [{"b64_json": encoded}]},
            )

    monkeypatch.setattr("app.ai_image_service.httpx.Client", lambda **_kwargs: StubClient())
    images = call_image_api(
        ImageApiConfig("https://openrouter.icu/v1", "secret", "gpt-image-2"),
        operation="generate",
        prompt="A product photo",
        source_paths=[],
        mask_path=None,
        size="1024x1024",
        quality="medium",
        count=1,
        output_format="png",
        output_compression=None,
    )

    assert captured["url"] == "https://openrouter.icu/v1/images/generations"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer secret"
    assert captured["kwargs"]["json"]["model"] == "gpt-image-2"
    assert captured["kwargs"]["json"]["stream"] is False
    assert images == [source.read_bytes()]


def test_call_image_api_requires_sources_for_edit(tmp_path):
    with pytest.raises(AiImageError, match="至少需要上传一张"):
        call_image_api(
            ImageApiConfig("https://example.test", "secret", "gpt-image-2"),
            operation="edit",
            prompt="Change the background",
            source_paths=[],
            mask_path=None,
            size="1024x1024",
            quality="medium",
            count=1,
            output_format="png",
            output_compression=None,
        )


def test_call_image_api_sends_multiple_images_and_mask_for_edit(monkeypatch, tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    mask = tmp_path / "mask.png"
    response_image = tmp_path / "response.png"
    _write_image(first, (16, 16), (10, 20, 30, 255))
    _write_image(second, (16, 16), (40, 50, 60, 255))
    _write_image(mask, (16, 16), (255, 255, 255, 0))
    _write_image(response_image, (16, 16), (70, 80, 90, 255))
    encoded = base64.b64encode(response_image.read_bytes()).decode("ascii")
    captured = {}

    class StubClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            captured["url"] = url
            captured["data"] = kwargs["data"]
            captured["files"] = [(field, value[0]) for field, value in kwargs["files"]]
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"data": [{"b64_json": encoded}]},
            )

    monkeypatch.setattr("app.ai_image_service.httpx.Client", lambda **_kwargs: StubClient())
    images = call_image_api(
        ImageApiConfig("https://openrouter.icu", "secret", "gpt-image-2"),
        operation="edit",
        prompt="Change the background",
        source_paths=[first, second],
        mask_path=mask,
        size="1024x1024",
        quality="high",
        count=1,
        output_format="png",
        output_compression=None,
    )

    assert captured["url"] == "https://openrouter.icu/v1/images/edits"
    assert captured["data"]["stream"] == "false"
    assert captured["files"] == [
        ("image[]", "first.png"),
        ("image[]", "second.png"),
        ("mask", "mask.png"),
    ]
    assert images == [response_image.read_bytes()]
