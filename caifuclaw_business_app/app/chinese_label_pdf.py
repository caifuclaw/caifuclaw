from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


LABEL_WIDTH_MM = 100
LABEL_HEIGHT_MM = 20
LABEL_WIDTH = LABEL_WIDTH_MM * mm
LABEL_HEIGHT = LABEL_HEIGHT_MM * mm
FALLBACK_FONT_NAME = "STSong-Light"
PROJECT_FONT_NAME = "NotoSansSC-Label"
PROJECT_FONT_PATH = Path(__file__).resolve().parent / "assets" / "fonts" / "NotoSansSC-Medium.ttf"
SYSTEM_FONT_CANDIDATES = (
    ("STHeitiMedium-Label", Path("/System/Library/Fonts/STHeiti Medium.ttc"), 0),
    ("HiraginoSansGB-Label", Path("/System/Library/Fonts/Hiragino Sans GB.ttc"), 0),
    ("ArialUnicode-Label", Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"), 0),
    ("NotoSansCJKsc-Label", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), 0),
    ("NotoSansCJKsc-Label", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"), 0),
    ("NotoSansCJKsc-Label", Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"), 0),
    ("SourceHanSansSC-Label", Path("/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf"), 0),
    ("MicrosoftYaHei-Label", Path("C:/Windows/Fonts/msyh.ttc"), 0),
    ("SimHei-Label", Path("C:/Windows/Fonts/simhei.ttf"), 0),
)
FONT_NAME = PROJECT_FONT_NAME
FONT_SIZE_PT = 10.5
LINE_HEIGHT_PT = 10.5
MIN_PRODUCT_FONT_SIZE_PT = 7.0
PRODUCT_FONT_SIZE_STEP_PT = 0.25
TRUNCATION_MARKER = "..."
TRACKING_CHARS_PER_LINE = 10
HORIZONTAL_PADDING = 4 * mm
COLUMN_GAP = 2 * mm
TRACKING_COLUMN_WIDTH = 24 * mm
DEADLINE_COLUMN_WIDTH = 22 * mm
_ACTIVE_FONT_NAME: str | None = None
LABEL_LOCAL_TIME_OFFSET = timedelta(hours=8)
LABEL_LOCAL_TIMEZONE = timezone(LABEL_LOCAL_TIME_OFFSET)


@dataclass(frozen=True)
class ChineseLabelRow:
    tracking_number: str
    deadline: datetime | date | str | None
    product_name: str


@dataclass(frozen=True)
class LabelTextBlock:
    lines: list[str]
    font_size: float
    line_height: float


def resolve_chinese_label_deadline(
    *,
    platform: str | None,
    payment_at: datetime | date | None,
    platform_created_at: datetime | date | None,
    imported_at: datetime | date | None,
    fallback: datetime | date | str | None,
) -> datetime | date | str | None:
    if str(platform or "").strip().lower() not in {"mercado", "mercadolibre"}:
        return fallback

    base_time = payment_at or platform_created_at or imported_at
    if base_time is None:
        return fallback
    if isinstance(base_time, datetime):
        if base_time.tzinfo is not None:
            base_date = base_time.astimezone(LABEL_LOCAL_TIMEZONE).date()
        else:
            base_date = (base_time + LABEL_LOCAL_TIME_OFFSET).date()
    else:
        base_date = base_time
    return base_date + timedelta(days=3)


def _register_ttf_font(name: str, path: Path, subfont_index: int = 0) -> str | None:
    if not path.exists():
        return None
    try:
        pdfmetrics.getFont(name)
    except KeyError:
        try:
            pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=subfont_index))
        except Exception:
            return None
    return name


def register_chinese_label_font() -> str:
    global _ACTIVE_FONT_NAME
    if _ACTIVE_FONT_NAME:
        return _ACTIVE_FONT_NAME

    project_font = _register_ttf_font(PROJECT_FONT_NAME, PROJECT_FONT_PATH)
    if project_font:
        _ACTIVE_FONT_NAME = project_font
        return _ACTIVE_FONT_NAME

    for name, path, subfont_index in SYSTEM_FONT_CANDIDATES:
        registered = _register_ttf_font(name, path, subfont_index)
        if registered:
            _ACTIVE_FONT_NAME = registered
            return _ACTIVE_FONT_NAME

    try:
        pdfmetrics.getFont(FALLBACK_FONT_NAME)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(FALLBACK_FONT_NAME))
    _ACTIVE_FONT_NAME = FALLBACK_FONT_NAME
    return _ACTIVE_FONT_NAME


def format_label_deadline(value: datetime | date | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.date().isoformat()
    except ValueError:
        match = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
        return match.group(1) if match else raw[:10]


def split_tracking_number(value: str) -> list[str]:
    text = "".join(str(value or "").strip().split())
    if not text:
        return [""]
    return [text[index : index + TRACKING_CHARS_PER_LINE] for index in range(0, len(text), TRACKING_CHARS_PER_LINE)]


def _string_width(text: str, font_size: float = FONT_SIZE_PT) -> float:
    return pdfmetrics.stringWidth(text, register_chinese_label_font(), font_size)


def wrap_text_by_width(text: str, max_width: float, font_size: float = FONT_SIZE_PT) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return [""]

    lines: list[str] = []
    current = ""
    for char in raw:
        candidate = current + char
        if current and _string_width(candidate, font_size) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _line_height_for_font_size(font_size: float) -> float:
    return font_size


def _text_block_height(line_count: int, font_size: float, line_height: float | None = None) -> float:
    lines = max(1, line_count)
    font_name = register_chinese_label_font()
    ascent = pdfmetrics.getAscent(font_name, font_size)
    descent = pdfmetrics.getDescent(font_name, font_size)
    return (ascent - descent) + ((lines - 1) * (line_height or _line_height_for_font_size(font_size)))


def _max_lines_for_height(font_size: float, max_height: float) -> int:
    line_height = _line_height_for_font_size(font_size)
    single_line_height = _text_block_height(1, font_size, line_height)
    if single_line_height >= max_height:
        return 1
    return max(1, int((max_height - single_line_height) // line_height) + 1)


def _fit_tail_with_marker(text: str, max_width: float, font_size: float) -> str:
    marker_width = _string_width(TRUNCATION_MARKER, font_size)
    if marker_width >= max_width:
        return TRUNCATION_MARKER

    tail = ""
    for char in reversed(text):
        candidate = char + tail
        if _string_width(candidate, font_size) + marker_width > max_width:
            break
        tail = candidate
    return f"{TRUNCATION_MARKER}{tail}" if tail else TRUNCATION_MARKER


def _truncate_lines_preserving_tail(lines: list[str], max_width: float, font_size: float, max_lines: int) -> list[str]:
    if len(lines) <= max_lines:
        return lines

    if max_lines <= 1:
        return [_fit_tail_with_marker("".join(lines), max_width, font_size)]

    head = lines[: max_lines - 1]
    hidden_tail = "".join(lines[max_lines - 1 :])
    return [*head, _fit_tail_with_marker(hidden_tail, max_width, font_size)]


def _product_text_block(text: str, max_width: float) -> LabelTextBlock:
    font_size = FONT_SIZE_PT
    while font_size >= MIN_PRODUCT_FONT_SIZE_PT:
        font_size = round(font_size, 2)
        line_height = _line_height_for_font_size(font_size)
        lines = wrap_text_by_width(text, max_width, font_size)
        if _text_block_height(len(lines), font_size, line_height) <= LABEL_HEIGHT:
            return LabelTextBlock(lines=lines, font_size=font_size, line_height=line_height)
        font_size -= PRODUCT_FONT_SIZE_STEP_PT

    font_size = MIN_PRODUCT_FONT_SIZE_PT
    line_height = _line_height_for_font_size(font_size)
    max_lines = _max_lines_for_height(font_size, LABEL_HEIGHT)
    lines = wrap_text_by_width(text, max_width, font_size)
    return LabelTextBlock(
        lines=_truncate_lines_preserving_tail(lines, max_width, font_size, max_lines),
        font_size=font_size,
        line_height=line_height,
    )


def _draw_lines(
    pdf: canvas.Canvas,
    lines: list[str],
    x: float,
    y: float,
    font_size: float = FONT_SIZE_PT,
    line_height: float = LINE_HEIGHT_PT,
) -> None:
    pdf.setFont(register_chinese_label_font(), font_size)
    current_y = y
    for line in lines:
        pdf.drawString(x, current_y, line)
        current_y -= line_height


def _label_block_start_y(line_count: int) -> float:
    lines = max(1, line_count)
    font_name = register_chinese_label_font()
    ascent = pdfmetrics.getAscent(font_name, FONT_SIZE_PT)
    descent = pdfmetrics.getDescent(font_name, FONT_SIZE_PT)
    return (LABEL_HEIGHT / 2) - ((ascent + descent - ((lines - 1) * LINE_HEIGHT_PT)) / 2)


def _top_aligned_block_start_y(group_top: float, font_size: float) -> float:
    ascent = pdfmetrics.getAscent(register_chinese_label_font(), font_size)
    return LABEL_HEIGHT - group_top - ascent


def generate_chinese_label_pdf(rows: list[ChineseLabelRow]) -> bytes:
    register_chinese_label_font()
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
    pdf.setTitle("Chinese Labels")

    product_column_x = HORIZONTAL_PADDING + TRACKING_COLUMN_WIDTH + COLUMN_GAP + DEADLINE_COLUMN_WIDTH + COLUMN_GAP
    product_column_width = LABEL_WIDTH - HORIZONTAL_PADDING - product_column_x
    deadline_column_x = HORIZONTAL_PADDING + TRACKING_COLUMN_WIDTH + COLUMN_GAP

    for row in rows:
        tracking_lines = split_tracking_number(row.tracking_number)
        deadline_lines = [format_label_deadline(row.deadline)]
        product_block = _product_text_block(row.product_name, product_column_width)
        max_block_height = max(
            _text_block_height(len(tracking_lines), FONT_SIZE_PT, LINE_HEIGHT_PT),
            _text_block_height(len(deadline_lines), FONT_SIZE_PT, LINE_HEIGHT_PT),
            _text_block_height(len(product_block.lines), product_block.font_size, product_block.line_height),
        )
        group_top = max(0, (LABEL_HEIGHT - max_block_height) / 2)

        _draw_lines(pdf, tracking_lines, HORIZONTAL_PADDING, _top_aligned_block_start_y(group_top, FONT_SIZE_PT))
        _draw_lines(pdf, deadline_lines, deadline_column_x, _top_aligned_block_start_y(group_top, FONT_SIZE_PT))
        _draw_lines(
            pdf,
            product_block.lines,
            product_column_x,
            _top_aligned_block_start_y(group_top, product_block.font_size),
            product_block.font_size,
            product_block.line_height,
        )
        pdf.showPage()

    pdf.save()
    return out.getvalue()
