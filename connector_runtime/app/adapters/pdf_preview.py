from io import BytesIO

from reportlab.lib.pagesizes import A6
from reportlab.pdfgen import canvas


def build_preview_pdf(title: str, lines: list[str]) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A6)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(24, 370, title[:34])
    pdf.setFont("Helvetica", 9)
    y = 342
    for line in lines[:12]:
        pdf.drawString(24, y, line[:48])
        y -= 16
    pdf.drawString(24, 42, "Dry-run label. Not for shipping.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
