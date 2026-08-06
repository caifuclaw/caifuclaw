# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

PRINT_ORIENTATION_AUTO = "auto"
PRINT_ORIENTATION_PORTRAIT = "portrait"
PRINT_ORIENTATION_LANDSCAPE = "landscape"

PRINT_ORIENTATION_LABELS = {
    PRINT_ORIENTATION_AUTO: "自动",
    PRINT_ORIENTATION_PORTRAIT: "纵向",
    PRINT_ORIENTATION_LANDSCAPE: "横向",
}

PRINT_PLATFORM_CHINESE_LABEL = "chinese_label"
PRINT_PLATFORM_CHINESE_LABEL_NAME = "中文标签"

PLATFORM_LABEL_SIZE_MM = {
    # Ozon labels from the API are smaller than the 80 x 100 mm thermal stock
    # used locally, so normalize the PDF page before printing.
    "ozon": (80.0, 100.0),
    # Joom PDFs can be visually upright while still carrying -90 degree page
    # rotation metadata. Flatten them onto the 100 x 150 mm QR-488 stock before
    # CUPS media detection so the driver uses the same page origin as normal
    # labels instead of shifting content off the left edge.
    "joom_logistics": (100.0, 150.0),
    # Wildberries cross-border labels are 100 x 150 mm and should use the
    # same QR-488 portrait handling as Joom labels.
    "wildberries": (100.0, 150.0),
}

PLATFORM_LABEL_ORIENTATION = {
    # QR-586 stock is 80 mm wide and 100 mm tall, so Ozon labels must be
    # rotated into portrait before they are sent to CUPS.
    "ozon": PRINT_ORIENTATION_PORTRAIT,
    "joom_logistics": PRINT_ORIENTATION_PORTRAIT,
    "wildberries": PRINT_ORIENTATION_PORTRAIT,
}

_PRINT_ORIENTATION_ALIASES = {
    "": PRINT_ORIENTATION_AUTO,
    PRINT_ORIENTATION_AUTO: PRINT_ORIENTATION_AUTO,
    "自动": PRINT_ORIENTATION_AUTO,
    PRINT_ORIENTATION_PORTRAIT: PRINT_ORIENTATION_PORTRAIT,
    "vertical": PRINT_ORIENTATION_PORTRAIT,
    "纵向": PRINT_ORIENTATION_PORTRAIT,
    PRINT_ORIENTATION_LANDSCAPE: PRINT_ORIENTATION_LANDSCAPE,
    "horizontal": PRINT_ORIENTATION_LANDSCAPE,
    "横向": PRINT_ORIENTATION_LANDSCAPE,
}


def is_valid_print_orientation(value: str | None) -> bool:
    key = str(value or "").strip().lower()
    return key in _PRINT_ORIENTATION_ALIASES


def normalize_print_orientation(value: str | None) -> str:
    key = str(value or "").strip().lower()
    return _PRINT_ORIENTATION_ALIASES.get(key, PRINT_ORIENTATION_AUTO)


def label_size_mm_for_platform(platform: str | None) -> tuple[float, float] | None:
    return PLATFORM_LABEL_SIZE_MM.get(str(platform or "").strip().lower())


def label_orientation_for_platform(platform: str | None, configured_orientation: str | None) -> str:
    platform_key = str(platform or "").strip().lower()
    return PLATFORM_LABEL_ORIENTATION.get(platform_key, normalize_print_orientation(configured_orientation))
