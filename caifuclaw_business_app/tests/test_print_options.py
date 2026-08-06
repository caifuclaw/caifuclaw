# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import io

from pypdf import PdfReader, PdfWriter

from app.pdf_tools import orient_pdf_bytes
from app.print_options import label_orientation_for_platform, label_size_mm_for_platform


def _blank_pdf(width: int, height: int, rotate: int = 0) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    if rotate:
        page.rotate(rotate)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_joom_label_flattens_rotated_page_to_100x150_stock():
    source_pdf = _blank_pdf(283, 425, rotate=-90)

    normalized = orient_pdf_bytes(
        source_pdf,
        label_orientation_for_platform("joom_logistics", "auto"),
        target_size_mm=label_size_mm_for_platform("joom_logistics"),
    )

    page = PdfReader(io.BytesIO(normalized)).pages[0]
    width_mm = float(page.mediabox.width) * 25.4 / 72
    height_mm = float(page.mediabox.height) * 25.4 / 72

    assert round(width_mm) == 100
    assert round(height_mm) == 150
    assert int(page.get("/Rotate", 0) or 0) == 0
