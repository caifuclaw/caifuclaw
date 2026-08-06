from __future__ import annotations

import base64
from contextlib import ExitStack
from dataclasses import dataclass
import io
import json
import math
import mimetypes
from pathlib import Path
import re
from typing import Any

import httpx

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - optional runtime dependency
    Image = None
    ImageOps = None


SUPPORTED_FORMATS = {"png", "jpeg", "webp", "bmp"}
OUTPUT_FORMATS = {"png", "jpeg", "webp"}
QUALITY_OPTIONS = {"low", "medium", "high", "auto"}
MAX_IMAGE_PIXELS = 3840 * 2160
MAX_COMPOSITE_PIXELS = 64_000_000
AI_SPLIT_MAX_RESULTS = 20
AI_SPLIT_MIN_CONFIDENCE = 0.55
AI_SPLIT_PREVIEW_MAX_SIDE = 2048
AI_SPLIT_MAX_DETAIL_TILES = 8
AI_SPLIT_LONG_IMAGE_RATIO = 3
AI_SPLIT_ANALYSIS_MAX_WIDTH = 256


class AiImageError(RuntimeError):
    pass


class AiImageUpstreamError(AiImageError):
    pass


@dataclass(frozen=True)
class ImageApiConfig:
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class AiSplitRegion:
    left: int
    top: int
    right: int
    bottom: int
    confidence: float
    label: str = ""


def ensure_pillow() -> None:
    if Image is None or ImageOps is None:
        raise AiImageError("缺少 Pillow 依赖，无法处理图片")


def normalize_output_format(value: str) -> str:
    normalized = str(value or "png").strip().lower()
    if normalized == "jpg":
        normalized = "jpeg"
    if normalized not in OUTPUT_FORMATS:
        raise AiImageError("输出格式仅支持 png、jpeg、webp")
    return normalized


def output_suffix(output_format: str) -> str:
    return ".jpg" if normalize_output_format(output_format) == "jpeg" else f".{normalize_output_format(output_format)}"


def validate_image_file(path: Path) -> dict[str, int | str]:
    ensure_pillow()
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = str(image.format or "").lower()
    except Exception as exc:
        raise AiImageError(f"图片文件无效: {path.name}") from exc
    if image_format == "jpg":
        image_format = "jpeg"
    if image_format not in SUPPORTED_FORMATS:
        raise AiImageError("图片格式仅支持 png、jpeg、webp、bmp")
    if width < 1 or height < 1:
        raise AiImageError("图片尺寸无效")
    if width * height > MAX_COMPOSITE_PIXELS:
        raise AiImageError("单张图片像素数过大")
    return {"width": width, "height": height, "format": image_format}


def validate_size(value: str) -> str:
    size = str(value or "1024x1024").strip().lower()
    if size == "auto":
        return size
    match = re.fullmatch(r"(\d+)x(\d+)", size)
    if not match:
        raise AiImageError("图片尺寸必须是 auto 或 WIDTHxHEIGHT")
    width, height = int(match.group(1)), int(match.group(2))
    if width < 16 or height < 16 or width % 16 or height % 16:
        raise AiImageError("图片尺寸的宽高必须为 16 的倍数")
    if not 1 / 3 <= width / height <= 3:
        raise AiImageError("图片宽高比必须在 1:3 到 3:1 之间")
    if width * height > MAX_IMAGE_PIXELS:
        raise AiImageError("图片像素数不能超过 3840x2160")
    return size


def _image_api_url(base_url: str, endpoint: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise AiImageError("图片模型 base url 为空")
    if normalized.endswith("/v1") and endpoint.startswith("/v1/"):
        return f"{normalized}{endpoint[3:]}"
    return f"{normalized}{endpoint}"


def _response_error_detail(response: httpx.Response) -> str:
    text = response.text[:1200] if response.text else response.reason_phrase
    try:
        payload = response.json()
    except ValueError:
        return text
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("detail") or text)
        if isinstance(error, str):
            return error
        return str(payload.get("detail") or payload.get("message") or text)
    return text


def _extract_json_images(payload: Any) -> list[bytes]:
    items: list[Any] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            items.extend(data)
        elif data is not None:
            items.append(data)
        items.append(payload)
    images: list[bytes] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        encoded = item.get("b64_json") or item.get("image_b64")
        if not isinstance(encoded, str) or not encoded:
            continue
        try:
            images.append(base64.b64decode(encoded, validate=True))
        except ValueError as exc:
            raise AiImageUpstreamError("图片接口返回了无效的 base64 图片") from exc
    return images


def _extract_stream_images(body: bytes) -> list[bytes]:
    events: list[dict[str, Any]] = []
    block: list[str] = []

    def flush() -> None:
        if not block:
            return
        raw = "\n".join(line[5:].lstrip() for line in block if line.startswith("data:")).strip()
        block.clear()
        if not raw or raw == "[DONE]":
            return
        try:
            decoded = json.loads(raw)
        except ValueError:
            return
        if isinstance(decoded, dict):
            events.append(decoded)

    for line in body.decode("utf-8", errors="replace").splitlines():
        if line.strip():
            block.append(line)
        else:
            flush()
    flush()

    images: list[bytes] = []
    for event in events:
        kind = str(event.get("type") or "")
        if "error" in kind or event.get("error"):
            raise AiImageUpstreamError("图片接口流式响应失败")
        data = event.get("data") if isinstance(event.get("data"), dict) else event
        encoded = data.get("b64_json") if isinstance(data, dict) else None
        if isinstance(encoded, str) and encoded and "partial" not in kind:
            try:
                images.append(base64.b64decode(encoded, validate=True))
            except ValueError as exc:
                raise AiImageUpstreamError("图片接口返回了无效的 base64 图片") from exc
    return images


def call_image_api(
    config: ImageApiConfig,
    *,
    operation: str,
    prompt: str,
    source_paths: list[Path],
    mask_path: Path | None,
    size: str,
    quality: str,
    count: int,
    output_format: str,
    output_compression: int | None,
) -> list[bytes]:
    normalized_operation = str(operation or "").strip().lower()
    if normalized_operation not in {"generate", "edit"}:
        raise AiImageError("AI 图片操作仅支持 generate 或 edit")
    if not str(prompt or "").strip():
        raise AiImageError("请输入图片提示词")
    if len(prompt.strip()) > 5000:
        raise AiImageError("图片提示词不能超过 5000 个字符")
    if normalized_operation == "edit" and not source_paths:
        raise AiImageError("图片修改至少需要上传一张图片")
    if not 1 <= int(count) <= 4:
        raise AiImageError("一次最多生成 4 张图片")
    normalized_size = validate_size(size)
    normalized_quality = str(quality or "medium").strip().lower()
    if normalized_quality not in QUALITY_OPTIONS:
        raise AiImageError("图片质量仅支持 low、medium、high、auto")
    normalized_format = normalize_output_format(output_format)
    if output_compression is not None:
        if normalized_format not in {"jpeg", "webp"}:
            raise AiImageError("压缩质量仅适用于 jpeg 或 webp")
        if not 0 <= int(output_compression) <= 100:
            raise AiImageError("压缩质量必须在 0 到 100 之间")

    endpoint = "/v1/images/generations" if normalized_operation == "generate" else "/v1/images/edits"
    url = _image_api_url(config.base_url, endpoint)
    headers = {"Authorization": f"Bearer {config.api_key}"}
    payload: dict[str, Any] = {
        "model": config.model,
        "prompt": prompt.strip(),
        "size": normalized_size,
        "quality": normalized_quality,
        "n": int(count),
        "output_format": normalized_format,
        "stream": False,
    }
    if output_compression is not None:
        payload["output_compression"] = int(output_compression)

    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=15)) as client:
            if normalized_operation == "generate":
                response = client.post(url, headers={**headers, "Content-Type": "application/json"}, json=payload)
            else:
                with ExitStack() as stack:
                    files: list[tuple[str, tuple[str, Any, str]]] = []
                    for source_path in source_paths:
                        handle = stack.enter_context(source_path.open("rb"))
                        content_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
                        files.append(("image[]", (source_path.name, handle, content_type)))
                    if mask_path is not None:
                        handle = stack.enter_context(mask_path.open("rb"))
                        content_type = mimetypes.guess_type(mask_path.name)[0] or "image/png"
                        files.append(("mask", (mask_path.name, handle, content_type)))
                    response = client.post(url, headers=headers, data={key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in payload.items()}, files=files)
    except httpx.HTTPError as exc:
        raise AiImageUpstreamError(f"图片模型连接失败: {exc}") from exc

    if response.status_code >= 400:
        request_id = response.headers.get("x-request-id") or response.headers.get("x-openrouter-request-id")
        suffix = f" (request id: {request_id})" if request_id else ""
        raise AiImageUpstreamError(f"图片模型接口返回错误: {_response_error_detail(response)}{suffix}")

    content_type = response.headers.get("content-type", "").lower()
    if "text/event-stream" in content_type:
        images = _extract_stream_images(response.content)
    else:
        try:
            response_payload = response.json()
        except ValueError as exc:
            raise AiImageUpstreamError("图片模型返回内容不是 JSON") from exc
        images = _extract_json_images(response_payload)
    if not images:
        raise AiImageUpstreamError("图片模型返回内容中没有可用图片")
    return images[: int(count)]


def write_api_images(images: list[bytes], output_dir: Path, *, output_format: str) -> list[Path]:
    if not images:
        raise AiImageError("没有可保存的图片结果")
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = output_suffix(output_format)
    paths: list[Path] = []
    for index, content in enumerate(images, start=1):
        path = output_dir / f"image-{index}{suffix}"
        path.write_bytes(content)
        validate_image_file(path)
        paths.append(path)
    return paths


def _save_image(image: Any, output_path: Path, output_format: str, output_compression: int | None = None) -> None:
    normalized_format = normalize_output_format(output_format)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if normalized_format == "jpeg":
        if image.mode != "RGB":
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        save_kwargs: dict[str, Any] = {
            "format": "JPEG",
            "quality": 92 if output_compression is None else output_compression,
            "optimize": True,
        }
    elif normalized_format == "webp":
        save_kwargs = {
            "format": "WEBP",
            "quality": 92 if output_compression is None else output_compression,
            "method": 6,
        }
    else:
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA")
        save_kwargs = {"format": "PNG", "optimize": True}
    image.save(output_path, **save_kwargs)
    validate_image_file(output_path)


def _encode_ai_split_preview(image: Any) -> str:
    preview = image.copy()
    preview.thumbnail(
        (AI_SPLIT_PREVIEW_MAX_SIDE, AI_SPLIT_PREVIEW_MAX_SIDE),
        Image.Resampling.LANCZOS,
    )
    rgba = preview.convert("RGBA")
    rgb = Image.new("RGB", rgba.size, "white")
    rgb.paste(rgba, mask=rgba.getchannel("A"))
    output = io.BytesIO()
    rgb.save(output, format="JPEG", quality=88, optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii")


def _ai_split_detail_tile_boxes(image_width: int, image_height: int) -> list[tuple[int, int, int, int]]:
    long_side = max(image_width, image_height)
    short_side = min(image_width, image_height)
    if long_side <= AI_SPLIT_PREVIEW_MAX_SIDE or long_side / max(1, short_side) < 3:
        return []

    desired_length = max(768, round(short_side * 1.75))
    tile_count = min(AI_SPLIT_MAX_DETAIL_TILES, max(2, math.ceil(long_side / desired_length)))
    overlap = min(128, max(32, round(long_side / tile_count * 0.05)))
    boxes: list[tuple[int, int, int, int]] = []
    for index in range(tile_count):
        core_start = round(index * long_side / tile_count)
        core_end = round((index + 1) * long_side / tile_count)
        start = max(0, core_start - (overlap if index else 0))
        end = min(long_side, core_end + (overlap if index + 1 < tile_count else 0))
        boxes.append((0, start, image_width, end) if image_height >= image_width else (start, 0, end, image_height))
    return boxes


def _ai_split_tile_boundary_instruction(
    index: int,
    box: tuple[int, int, int, int],
) -> dict[str, Any]:
    return {
        "detail_tile": index,
        "source_box_pixels": {
            "left": box[0],
            "top": box[1],
            "right": box[2],
            "bottom": box[3],
        },
        "inspection": "识别此分段内的自然内容边界和安全留白；不要把分段自身的顶部或底部当作内容边界",
    }


def build_ai_split_messages(
    source_path: Path,
    instruction: str = "",
) -> list[dict[str, Any]]:
    ensure_pillow()
    metadata = validate_image_file(source_path)
    instruction_text = str(instruction or "").strip()
    if len(instruction_text) > 1000:
        raise AiImageError("智能拆分要求不能超过 1000 个字符")

    with Image.open(source_path) as opened:
        encoded = _encode_ai_split_preview(opened)
        detail_tiles = [
            (box, _encode_ai_split_preview(opened.crop(box)))
            for box in _ai_split_detail_tile_boxes(*opened.size)
        ]

    request_payload = {
        "original_width": int(metadata["width"]),
        "original_height": int(metadata["height"]),
        "coordinate_scale": 1000,
        "max_regions": AI_SPLIT_MAX_RESULTS,
        "split_policy": "natural_content_blocks_only",
        "instruction": instruction_text,
    }
    system_prompt = """你是电商拼接图和商品详情长图的内容结构识别器。你只负责识别完整、不可再分的自然内容块，不负责决定裁剪尺寸或目标长宽比。
只返回 JSON，不要返回 Markdown 或解释。

规则：
1. 坐标使用 0 到 1000 的归一化整数，基于整张画布。
2. 第一张图片是整图预览；如后续提供 detail_tile，它们是同一原图的高清分段。逐张检查分段内的主体、文字和自然留白，分段元数据给出其原图像素范围。不要沿 detail_tile 自身边缘拆分，最终仍须返回整张画布的全局坐标。
3. 对普通拼图，每个顶层完整子图是一个内容块；不要把子图内部的商品、文字、卡片或装饰继续拆开。
4. 对纵向或横向商品详情长图，根据明显留白、背景或场景切换识别完整模块。单品、组合展示、正面、侧面、背面、细节和说明区通常是彼此独立的内容块。
5. 边界必须位于两个完整内容块之间。严禁把上一块的尾部和下一块的头部放入同一区域，也不得从主体、文字或卡片中间切开。
6. 完整内容边界是唯一的拆分依据。不要把任何数值当作裁剪宽高或目标长宽比，不要为了让各区域尺寸接近而改变自然边界。各区域尺寸可以明显不同。
7. 标题、说明或标签如果明显属于某张内容图，应与对应内容保持在同一区域；独立的说明板块则单独返回。
8. 区域数量自动决定。区域应覆盖从开头到结尾的全部有效内容，只允许跳过纯空白外边距，不得遗漏底部内容。相邻区域不得重复或高度重叠，并按从上到下、从左到右返回。
9. instruction 是用户的可选补充要求。在不违背完整覆盖和自然边界的前提下执行。
10. 不要返回覆盖整张画布的单一区域，不要返回重复区域。只有确认图片本身不是组合图或详情长图时才返回空 regions。
11. confidence 使用 0 到 1，最多返回 max_regions 个区域。

返回格式：
{"regions":[{"x1":0,"y1":0,"x2":1000,"y2":500,"confidence":0.95,"label":"可选名称"}]}"""
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": json.dumps(request_payload, ensure_ascii=False)},
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{encoded}",
                "detail": "high",
            },
        },
    ]
    for index, (box, tile_encoded) in enumerate(detail_tiles, start=1):
        user_content.extend(
            [
                {
                    "type": "text",
                    "text": json.dumps(_ai_split_tile_boundary_instruction(index, box), ensure_ascii=False),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{tile_encoded}",
                        "detail": "high",
                    },
                },
            ]
        )
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_content,
        },
    ]


def _extract_ai_split_payload(model_text: str) -> dict[str, Any]:
    text = str(model_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except ValueError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise AiImageError("视觉模型未返回有效的拆分坐标")
        try:
            payload = json.loads(text[start:end + 1])
        except ValueError as exc:
            raise AiImageError("视觉模型返回的拆分坐标不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise AiImageError("视觉模型返回的拆分结果格式无效")
    return payload


def _ai_split_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


def _ai_split_iou(first: AiSplitRegion, second: AiSplitRegion) -> float:
    intersection_width = max(0, min(first.right, second.right) - max(first.left, second.left))
    intersection_height = max(0, min(first.bottom, second.bottom) - max(first.top, second.top))
    intersection = intersection_width * intersection_height
    if not intersection:
        return 0.0
    first_area = (first.right - first.left) * (first.bottom - first.top)
    second_area = (second.right - second.left) * (second.bottom - second.top)
    return intersection / max(1, first_area + second_area - intersection)


def _ai_split_quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * max(0.0, min(1.0, fraction)))
    return ordered[index]


def _ai_split_row_metrics(image: Any) -> tuple[list[float], list[float]]:
    rgba = image.convert("RGBA")
    rgb = Image.new("RGB", rgba.size, "white")
    rgb.paste(rgba, mask=rgba.getchannel("A"))
    analysis_width = min(rgb.width, AI_SPLIT_ANALYSIS_MAX_WIDTH)
    if analysis_width != rgb.width:
        rgb = rgb.resize((analysis_width, rgb.height), Image.Resampling.LANCZOS)
    gray = ImageOps.grayscale(rgb)
    width, height = gray.size
    inset = min(max(1, round(width * 0.04)), max(1, width // 4))
    left, right = inset, max(inset + 1, width - inset)
    row_width = right - left
    pixels = gray.tobytes()
    color_pixels = rgb.tobytes()
    scores: list[float] = []
    scene_scores: list[float] = []
    previous: bytes | None = None
    previous_color: bytes | None = None
    for y in range(height):
        offset = y * width
        row = pixels[offset + left:offset + right]
        color_offset = (offset + left) * 3
        color_row = color_pixels[color_offset:color_offset + row_width * 3]
        if not row:
            scores.append(0.0)
            scene_scores.append(0.0)
            continue
        row_min, row_max = min(row), max(row)
        horizontal = (
            sum(abs(row[index] - row[index - 1]) for index in range(1, row_width))
            / max(1, row_width - 1)
        )
        differences = (
            [abs(row[index] - previous[index]) for index in range(row_width)]
            if previous is not None
            else []
        )
        vertical = sum(differences) / row_width if differences else 0.0
        color_differences = (
            [
                (
                    abs(color_row[index] - previous_color[index])
                    + abs(color_row[index + 1] - previous_color[index + 1])
                    + abs(color_row[index + 2] - previous_color[index + 2])
                )
                / 3
                for index in range(0, len(color_row), 3)
            ]
            if previous_color is not None
            else []
        )
        changed_fraction = (
            sum(difference >= 24 for difference in color_differences) / row_width
            if color_differences
            else 0.0
        )
        scores.append(horizontal * 0.55 + vertical * 0.30 + (row_max - row_min) * 0.15)
        color_change = sum(color_differences) / row_width if color_differences else 0.0
        scene_scores.append(color_change if changed_fraction >= 0.78 else 0.0)
        previous = row
        previous_color = color_row
    return scores, scene_scores


def _ai_split_smoothed_scores(scores: list[float], radius: int) -> list[float]:
    if not scores:
        return []
    radius = max(1, int(radius))
    prefix = [0.0]
    for score in scores:
        prefix.append(prefix[-1] + score)
    result: list[float] = []
    for index in range(len(scores)):
        start = max(0, index - radius)
        end = min(len(scores), index + radius + 1)
        result.append((prefix[end] - prefix[start]) / max(1, end - start))
    return result


def _ai_split_safe_boundary(
    smoothed_scores: list[float],
    proposal: int,
    *,
    image_width: int,
    lower: int,
    upper: int,
) -> int | None:
    if upper <= lower:
        return None
    global_low = _ai_split_quantile(smoothed_scores, 0.20)
    global_mid = _ai_split_quantile(smoothed_scores, 0.50)
    safe_threshold = min(8.0, global_low + max(0.35, (global_mid - global_low) * 0.28))
    minimum_band = max(10, round(image_width * 0.03))
    runs: list[tuple[int, int, float]] = []
    run_start: int | None = None
    for y in range(lower, upper + 1):
        is_safe = smoothed_scores[y] <= safe_threshold
        if is_safe and run_start is None:
            run_start = y
        if run_start is not None and (not is_safe or y == upper):
            run_end = y if is_safe and y == upper else y - 1
            if run_end - run_start + 1 >= minimum_band:
                run_score = min(smoothed_scores[run_start:run_end + 1])
                runs.append((run_start, run_end, run_score))
            run_start = None
    if not runs:
        return None

    score_span = max(0.35, global_mid - global_low)

    def rank(run: tuple[int, int, float]) -> tuple[float, int]:
        start, end, score = run
        nearest = min(max(proposal, start), end)
        distance = abs(nearest - proposal)
        normalized_score = max(0.0, score - global_low) / score_span
        band_length = min(end - start + 1, round(image_width * 0.25))
        return distance - band_length + normalized_score * image_width * 0.08, distance

    start, end, _score = min(runs, key=rank)
    return round((start + end) / 2)


def _ai_split_scene_boundary(
    scene_scores: list[float],
    proposal: int,
    *,
    lower: int,
    upper: int,
) -> int | None:
    if upper <= lower:
        return None
    peak = max(range(lower, upper + 1), key=scene_scores.__getitem__)
    peak_score = scene_scores[peak]
    local_scores = scene_scores[lower:upper + 1]
    local_mid = _ai_split_quantile(local_scores, 0.50)
    if peak_score < max(8.0, local_mid * 2.5):
        return None
    return peak


def _ai_split_is_vertical_long_layout(
    image_width: int,
    image_height: int,
    regions: list[AiSplitRegion],
) -> bool:
    if image_height / max(1, image_width) < AI_SPLIT_LONG_IMAGE_RATIO or len(regions) < 2:
        return False
    ordered = sorted(regions, key=lambda item: (item.top, item.left))
    edge_tolerance = max(24, round(image_height * 0.04))
    if ordered[0].top > edge_tolerance or ordered[-1].bottom < image_height - edge_tolerance:
        return False
    if sum(region.right - region.left >= image_width * 0.5 for region in ordered) < math.ceil(len(ordered) * 0.8):
        return False
    for previous, current in zip(ordered, ordered[1:]):
        overlap = max(0, previous.bottom - current.top)
        if overlap > min(previous.bottom - previous.top, current.bottom - current.top) * 0.2:
            return False
    return True


def refine_ai_split_regions(source_path: Path, regions: list[AiSplitRegion]) -> list[AiSplitRegion]:
    """Snap long-detail boundaries to low-content bands and merge unsafe cuts."""
    ensure_pillow()
    if len(regions) < 2:
        return regions
    with Image.open(source_path) as opened:
        image = opened.convert("RGBA")
    image_width, image_height = image.size
    ordered = sorted(regions, key=lambda item: (item.top, item.left, item.bottom, item.right))
    if not _ai_split_is_vertical_long_layout(image_width, image_height, ordered):
        return ordered

    scores, scene_scores = _ai_split_row_metrics(image)
    band_radius = max(3, round(image_width * 0.008))
    smoothed = _ai_split_smoothed_scores(scores, band_radius)
    search_radius = min(max(96, round(image_width * 0.35)), max(96, round(image_height * 0.08)))
    minimum_region_height = max(32, round(image_width * 0.08))
    safe_boundaries: list[int | None] = []
    previous_boundary = 0
    for index, (previous, current) in enumerate(zip(ordered, ordered[1:])):
        proposal = round((previous.bottom + current.top) / 2)
        next_proposal = (
            round((current.bottom + ordered[index + 2].top) / 2)
            if index + 2 < len(ordered)
            else image_height
        )
        lower = max(previous_boundary + minimum_region_height, proposal - search_radius)
        upper = min(
            next_proposal - minimum_region_height,
            proposal + search_radius,
            image_height - minimum_region_height,
        )
        close_scene_radius = max(32, round(image_width * 0.12))
        boundary = _ai_split_scene_boundary(
            scene_scores,
            proposal,
            lower=max(lower, proposal - close_scene_radius),
            upper=min(upper, proposal + close_scene_radius),
        )
        if boundary is None:
            boundary = _ai_split_safe_boundary(
                smoothed,
                proposal,
                image_width=image_width,
                lower=lower,
                upper=upper,
            )
        if boundary is None:
            boundary = _ai_split_scene_boundary(
                scene_scores,
                proposal,
                lower=lower,
                upper=upper,
            )
        safe_boundaries.append(boundary)
        if boundary is not None:
            previous_boundary = boundary

    refined: list[AiSplitRegion] = []
    group_start = 0
    group_regions: list[AiSplitRegion] = []
    for index, region in enumerate(ordered):
        group_regions.append(region)
        boundary = safe_boundaries[index] if index < len(safe_boundaries) else image_height
        if boundary is None:
            continue
        labels = [item.label for item in group_regions if item.label]
        refined.append(
            AiSplitRegion(
                left=min(item.left for item in group_regions),
                top=group_start,
                right=max(item.right for item in group_regions),
                bottom=boundary,
                confidence=round(min(item.confidence for item in group_regions), 4),
                label=" / ".join(labels)[:80],
            )
        )
        group_start = boundary
        group_regions = []
    if len(refined) < 2:
        raise AiImageError("未找到可靠的自然分界，请补充拆分要求或改用长图拆分")
    return refined


def parse_ai_split_regions(
    model_text: str,
    *,
    image_width: int,
    image_height: int,
    max_results: int = AI_SPLIT_MAX_RESULTS,
    min_confidence: float = AI_SPLIT_MIN_CONFIDENCE,
) -> list[AiSplitRegion]:
    if image_width < 1 or image_height < 1:
        raise AiImageError("智能拆分图片尺寸无效")
    if not 2 <= int(max_results) <= AI_SPLIT_MAX_RESULTS:
        raise AiImageError(f"智能拆分结果数量必须在 2 到 {AI_SPLIT_MAX_RESULTS} 之间")

    payload = _extract_ai_split_payload(model_text)
    raw_regions = payload.get("regions")
    if not isinstance(raw_regions, list):
        raise AiImageError("视觉模型返回内容缺少 regions")

    min_width = max(8, round(image_width * 0.01))
    min_height = max(8, round(image_height * 0.01))
    min_area = max(256, round(image_width * image_height * 0.002))
    candidates: list[AiSplitRegion] = []
    for item in raw_regions:
        if not isinstance(item, dict):
            continue
        try:
            x1 = _ai_split_number(item.get("x1"))
            y1 = _ai_split_number(item.get("y1"))
            x2 = _ai_split_number(item.get("x2"))
            y2 = _ai_split_number(item.get("y2"))
            confidence = _ai_split_number(item.get("confidence"))
        except (TypeError, ValueError):
            continue
        if 1 < confidence <= 100:
            confidence /= 100
        if confidence < float(min_confidence) or confidence > 1:
            continue
        if min(x1, y1, x2, y2) < -5 or max(x1, y1, x2, y2) > 1005:
            continue
        x1, y1 = max(0.0, x1), max(0.0, y1)
        x2, y2 = min(1000.0, x2), min(1000.0, y2)
        left = max(0, min(image_width - 1, round(x1 * image_width / 1000)))
        top = max(0, min(image_height - 1, round(y1 * image_height / 1000)))
        right = max(1, min(image_width, round(x2 * image_width / 1000)))
        bottom = max(1, min(image_height, round(y2 * image_height / 1000)))
        width, height = right - left, bottom - top
        area = width * height
        if width < min_width or height < min_height or area < min_area:
            continue
        if area >= image_width * image_height * 0.985:
            continue
        label = re.sub(r"[\x00-\x1f\x7f]+", " ", str(item.get("label") or "")).strip()[:80]
        candidates.append(
            AiSplitRegion(
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                confidence=round(confidence, 4),
                label=label,
            )
        )

    accepted: list[AiSplitRegion] = []
    for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
        if any(_ai_split_iou(candidate, existing) >= 0.85 for existing in accepted):
            continue
        accepted.append(candidate)
        if len(accepted) >= int(max_results):
            break
    if len(accepted) < 2:
        raise AiImageError("智能识别未发现至少两张明确的拼接图片，请改用长图或网格拆分")
    return sorted(accepted, key=lambda item: (item.top, item.left, item.bottom, item.right))


def split_image(
    source_path: Path,
    output_dir: Path,
    *,
    split_mode: str,
    max_height: int,
    rows: int,
    columns: int,
    output_format: str,
    output_compression: int | None = None,
    regions: list[AiSplitRegion] | None = None,
) -> list[Path]:
    ensure_pillow()
    validate_image_file(source_path)
    mode = str(split_mode or "long").strip().lower()
    if mode not in {"long", "grid", "ai"}:
        raise AiImageError("拆分方式仅支持长图、网格或智能识别")
    with Image.open(source_path) as opened:
        image = opened.convert("RGBA")
    width, height = image.size
    boxes: list[tuple[int, int, int, int]] = []
    if mode == "long":
        if not 128 <= int(max_height) <= 8192:
            raise AiImageError("长图单段高度必须在 128 到 8192 之间")
        for top in range(0, height, int(max_height)):
            boxes.append((0, top, width, min(height, top + int(max_height))))
    elif mode == "grid":
        if not 1 <= int(rows) <= 20 or not 1 <= int(columns) <= 20:
            raise AiImageError("网格行数和列数必须在 1 到 20 之间")
        if int(rows) > height or int(columns) > width:
            raise AiImageError("网格行列数不能超过图片像素尺寸")
        for row in range(int(rows)):
            for column in range(int(columns)):
                left = round(column * width / int(columns))
                right = round((column + 1) * width / int(columns))
                top = round(row * height / int(rows))
                bottom = round((row + 1) * height / int(rows))
                boxes.append((left, top, right, bottom))
    else:
        if not regions or len(regions) < 2:
            raise AiImageError("智能拆分至少需要两个有效区域")
        for region in regions[:AI_SPLIT_MAX_RESULTS]:
            if not (
                0 <= region.left < region.right <= width
                and 0 <= region.top < region.bottom <= height
            ):
                raise AiImageError("智能拆分区域超出图片范围")
            boxes.append((region.left, region.top, region.right, region.bottom))

    result: list[Path] = []
    suffix = output_suffix(output_format)
    for index, box in enumerate(boxes, start=1):
        output_path = output_dir / f"split-{index}{suffix}"
        _save_image(image.crop(box), output_path, output_format, output_compression)
        result.append(output_path)
    return result


def _parse_background(value: str) -> tuple[int, int, int, int]:
    text = str(value or "#ffffff").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", text):
        raise AiImageError("背景色必须是 #RRGGBB 或 #RRGGBBAA")
    values = tuple(int(text[index:index + 2], 16) for index in range(1, len(text), 2))
    return values if len(values) == 4 else (*values, 255)


def merge_images(
    source_paths: list[Path],
    output_path: Path,
    *,
    layout: str,
    columns: int,
    cell_width: int | None,
    cell_height: int | None,
    gap: int,
    background: str,
    fit_mode: str,
    output_format: str,
    output_compression: int | None = None,
) -> Path:
    ensure_pillow()
    if len(source_paths) < 2:
        raise AiImageError("图片合并至少需要两张图片")
    normalized_layout = str(layout or "grid").strip().lower()
    if normalized_layout not in {"horizontal", "vertical", "grid"}:
        raise AiImageError("合并布局仅支持横向、纵向或网格")
    if not 0 <= int(gap) <= 200:
        raise AiImageError("图片间距必须在 0 到 200 之间")
    normalized_fit = str(fit_mode or "contain").strip().lower()
    if normalized_fit not in {"contain", "cover"}:
        raise AiImageError("图片适配方式仅支持 contain 或 cover")
    loaded: list[Any] = []
    try:
        for path in source_paths:
            validate_image_file(path)
            with Image.open(path) as opened:
                loaded.append(opened.convert("RGBA"))
        max_width = max(image.width for image in loaded)
        max_height = max(image.height for image in loaded)
        target_width = int(cell_width or max_width)
        target_height = int(cell_height or max_height)
        if not 1 <= target_width <= 8192 or not 1 <= target_height <= 8192:
            raise AiImageError("合并单元格宽高必须在 1 到 8192 之间")
        if normalized_layout == "horizontal":
            grid_columns, grid_rows = len(loaded), 1
        elif normalized_layout == "vertical":
            grid_columns, grid_rows = 1, len(loaded)
        else:
            if not 1 <= int(columns) <= 20:
                raise AiImageError("网格列数必须在 1 到 20 之间")
            grid_columns = min(int(columns), len(loaded))
            grid_rows = math.ceil(len(loaded) / grid_columns)
        canvas_width = grid_columns * target_width + (grid_columns - 1) * int(gap)
        canvas_height = grid_rows * target_height + (grid_rows - 1) * int(gap)
        if canvas_width * canvas_height > MAX_COMPOSITE_PIXELS:
            raise AiImageError("合并后的图片像素数过大，请减小单元格尺寸或图片数量")
        canvas = Image.new("RGBA", (canvas_width, canvas_height), _parse_background(background))
        for index, image in enumerate(loaded):
            if normalized_fit == "cover":
                fitted = ImageOps.fit(image, (target_width, target_height), method=Image.Resampling.LANCZOS)
            else:
                fitted = ImageOps.contain(image, (target_width, target_height), method=Image.Resampling.LANCZOS)
            column = index % grid_columns
            row = index // grid_columns
            left = column * (target_width + int(gap)) + (target_width - fitted.width) // 2
            top = row * (target_height + int(gap)) + (target_height - fitted.height) // 2
            canvas.alpha_composite(fitted, (left, top))
        _save_image(canvas, output_path, output_format, output_compression)
        return output_path
    finally:
        for image in loaded:
            image.close()
