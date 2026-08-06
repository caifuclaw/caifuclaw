# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""Keep a small anonymized platform catalog sample in the configured database.

The command is intentionally dry-run by default.  Use ``--apply`` only when
the target database and the requested retention limit have been verified.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caifuclaw_business_app.app.database import SessionLocal
from caifuclaw_business_app.app.platform_product_catalog import (
    CATALOG_MAIN_IMAGE_DIR_NAME,
    PlatformProductCatalogItem,
)
from caifuclaw_business_app.app.settings import get_settings


def _utcnow_naive() -> datetime:
    """Return a UTC timestamp compatible with the existing naive DB columns."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30, help="Number of catalog rows to retain (default: 30).")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the deletion and anonymization. Without this flag the command only reports the plan.",
    )
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="Keep the catalog image cache. By default all catalog images are removed after sanitization.",
    )
    return parser


def _catalog_image_dir() -> Path:
    label_root = get_settings().label_storage_path.resolve()
    image_dir = (label_root / CATALOG_MAIN_IMAGE_DIR_NAME).resolve()
    if image_dir.parent != label_root:
        raise RuntimeError(f"Refusing to clean an unexpected image path: {image_dir}")
    return image_dir


def _clear_catalog_images() -> int:
    image_dir = _catalog_image_dir()
    if not image_dir.is_dir():
        return 0
    removed = 0
    for path in image_dir.iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed += 1
        elif path.is_dir():
            shutil.rmtree(path)
            removed += 1
    return removed


def _synthetic_values(sequence: int) -> dict[str, object]:
    """Return deterministic demo values without retaining source identifiers."""

    price = Decimal("19.99") + Decimal(sequence)
    cost = (price * Decimal("0.45")).quantize(Decimal("0.01"))
    return {
        "platform_product_id": f"SANITIZED-PRODUCT-{sequence:04d}",
        "platform_sku": f"SANITIZED-SKU-{sequence:04d}",
        "product_name": f"Sanitized Demo Product {sequence:04d}",
        "listing_status": "active",
        "warehouse_code": f"SANITIZED-WH-{sequence:02d}",
        "warehouse_name": "Sanitized Demo Warehouse",
        "fulfillment_type": "standard",
        "logistics_type": "standard",
        "available_stock": 10 + (sequence % 20),
        "reserved_stock": sequence % 3,
        "price_amount": price,
        "price_currency": "CNY",
        "exchange_rate": Decimal("1"),
        "exchange_rate_date": _utcnow_naive().date(),
        "current_price_cny": price,
        "cost_cny": cost,
        "commission_rate": Decimal("0.10"),
        "shipping_fee_cny": Decimal("5.00"),
        "target_margin_rate": Decimal("0.20"),
        "current_profit_cny": Decimal("0"),
        "current_margin_rate": Decimal("0"),
        "suggested_price_cny": price,
        "calculation_status": "missing_mapping",
        "calculation_message": "Sanitized demo record",
    }


def sanitize_catalog(*, limit: int, apply: bool, keep_images: bool) -> dict[str, int | bool]:
    if limit < 1:
        raise ValueError("--limit must be at least 1")

    with SessionLocal() as db:
        total = int(db.scalar(select(func.count(PlatformProductCatalogItem.id))) or 0)
        keep_rows = db.scalars(
            select(PlatformProductCatalogItem)
            .order_by(PlatformProductCatalogItem.id.asc())
            .limit(limit)
        ).all()
        keep_ids = [row.id for row in keep_rows]
        planned_delete = max(total - len(keep_ids), 0)
        result: dict[str, int | bool] = {
            "before": total,
            "retained": len(keep_ids),
            "deleted": planned_delete,
            "images_removed": 0,
            "applied": apply,
        }
        if not apply:
            return result

        if keep_ids:
            db.execute(
                delete(PlatformProductCatalogItem).where(~PlatformProductCatalogItem.id.in_(keep_ids))
            )
        else:
            db.execute(delete(PlatformProductCatalogItem))

        now = _utcnow_naive()
        for sequence, row in enumerate(keep_rows, start=1):
            row.product_id = None
            row.pricing_rule_id = None
            row.raw_payload = {}
            row.last_synced_at = None
            row.last_seen_at = None
            row.calculated_at = None
            row.mapped_at = None
            row.mapped_by = ""
            row.is_active = True
            row.created_at = now
            row.updated_at = now
            for field, value in _synthetic_values(sequence).items():
                setattr(row, field, value)

        db.commit()
        result["after"] = int(db.scalar(select(func.count(PlatformProductCatalogItem.id))) or 0)

    if not keep_images:
        result["images_removed"] = _clear_catalog_images()
    return result


def main() -> int:
    args = _parser().parse_args()
    result = sanitize_catalog(limit=args.limit, apply=args.apply, keep_images=args.keep_images)
    print(", ".join(f"{key}={value}" for key, value in result.items()))
    if not args.apply:
        print("Dry run only. Re-run with --apply to commit the change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
