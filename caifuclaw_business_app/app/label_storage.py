# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import hashlib
import io
from pathlib import Path

from .settings import get_settings


def save_label_pdf(tenant_id: str, platform: str, account_id: str, order_id: str, content: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    root = get_settings().label_storage_path
    month = __import__("datetime").datetime.utcnow().strftime("%Y%m")
    directory = root / tenant_id / platform / account_id / month
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / f"{order_id}.pdf"
    file_path.write_bytes(content)
    return str(file_path), digest


def is_real_label_pdf(content: bytes) -> bool:
    if not content or not content.startswith(b"%PDF"):
        return False

    markers = ("Ozon FBS Label Preview", "Dry-run label", "Not for shipping")
    if any(marker.encode("utf-8") in content for marker in markers):
        return False

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:2])
        if any(marker in text for marker in markers):
            return False
    except Exception:
        # Keep valid PDFs printable if text extraction fails; callers separately verify %PDF.
        return True

    return True
