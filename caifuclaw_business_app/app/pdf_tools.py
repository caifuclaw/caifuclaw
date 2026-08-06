# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import io

from .print_options import (
    PRINT_ORIENTATION_AUTO,
    PRINT_ORIENTATION_LANDSCAPE,
    PRINT_ORIENTATION_PORTRAIT,
    normalize_print_orientation,
)

POINTS_PER_MM = 72.0 / 25.4


def _effective_page_size(page) -> tuple[float, float]:
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    rotation = int(page.get("/Rotate", 0) or 0) % 180
    if rotation == 90:
        return height, width
    return width, height


def _target_size_points(
    target_size_mm: tuple[float, float] | None,
    orientation: str,
    source_width: float,
    source_height: float,
) -> tuple[float, float] | None:
    if not target_size_mm:
        return None
    long_side, short_side = max(target_size_mm), min(target_size_mm)
    if orientation == PRINT_ORIENTATION_PORTRAIT:
        width_mm, height_mm = short_side, long_side
    elif orientation == PRINT_ORIENTATION_LANDSCAPE:
        width_mm, height_mm = long_side, short_side
    elif source_height > source_width:
        width_mm, height_mm = short_side, long_side
    else:
        width_mm, height_mm = long_side, short_side
    return width_mm * POINTS_PER_MM, height_mm * POINTS_PER_MM


def _resize_page_to_target(page, target_width: float, target_height: float):
    from pypdf import PageObject, Transformation

    source_width = float(page.mediabox.width)
    source_height = float(page.mediabox.height)
    scale = min(target_width / source_width, target_height / source_height)
    offset_x = (target_width - source_width * scale) / 2
    offset_y = (target_height - source_height * scale) / 2
    target_page = PageObject.create_blank_page(width=target_width, height=target_height)
    target_page.merge_transformed_page(
        page,
        Transformation().scale(scale).translate(tx=offset_x, ty=offset_y),
    )
    return target_page


def orient_pdf_bytes(
    pdf_bytes: bytes,
    page_orientation: str | None,
    target_size_mm: tuple[float, float] | None = None,
) -> bytes:
    orientation = normalize_print_orientation(page_orientation)
    if orientation == PRINT_ORIENTATION_AUTO and not target_size_mm:
        return pdf_bytes

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    changed = False
    for page in reader.pages:
        width, height = _effective_page_size(page)
        should_rotate = (
            (orientation == PRINT_ORIENTATION_LANDSCAPE and height > width)
            or (orientation == PRINT_ORIENTATION_PORTRAIT and width > height)
        )
        if should_rotate:
            page.rotate(90)
            if hasattr(page, "transfer_rotation_to_content"):
                page.transfer_rotation_to_content()
            changed = True
            width, height = _effective_page_size(page)
        target_size = _target_size_points(target_size_mm, orientation, width, height)
        if target_size:
            page = _resize_page_to_target(page, *target_size)
            changed = True
        writer.add_page(page)

    if not changed:
        return pdf_bytes

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def merge_pdf_parts(parts: list[bytes]) -> bytes:
    if len(parts) == 1:
        return parts[0]

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for part in parts:
        reader = PdfReader(io.BytesIO(part))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
