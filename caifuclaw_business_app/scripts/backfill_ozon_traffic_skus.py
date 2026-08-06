# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BUSINESS_ROOT = ROOT / "caifuclaw_business_app"
if str(BUSINESS_ROOT) not in sys.path:
    sys.path.insert(0, str(BUSINESS_ROOT))

from app.credential_manager import get_credential_manager  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import PlatformAccount, TrafficMetric  # noqa: E402
from connector_runtime.app.adapters.ozon import OzonConnector  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replace numeric Ozon traffic SKU dimensions with seller offer_id values."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database. Defaults to dry-run.")
    return parser.parse_args()


def _record_key(row: TrafficMetric, seller_sku: str) -> str:
    dimensions = [
        row.platform,
        row.account_id,
        row.source,
        row.grain,
        row.stat_date.isoformat(),
        row.period_start.isoformat(),
        row.period_end.isoformat(),
        row.region,
        row.entity_type,
        row.entity_id,
        seller_sku,
    ]
    return hashlib.sha256("\x1f".join(dimensions).encode("utf-8")).hexdigest()


def main() -> int:
    args = parse_args()
    total_rows = 0
    total_skus = 0
    unresolved_skus = 0

    with SessionLocal() as db:
        accounts = db.scalars(
            select(PlatformAccount).where(PlatformAccount.platform == "ozon").order_by(PlatformAccount.id)
        ).all()
        for account in accounts:
            skus = list(
                db.scalars(
                    select(TrafficMetric.sku)
                    .where(
                        TrafficMetric.platform_account_id == account.id,
                        TrafficMetric.sku.op("~")(r"^[0-9]+$"),
                    )
                    .distinct()
                    .order_by(TrafficMetric.sku)
                ).all()
            )
            if not skus or not account.encrypted_credentials:
                continue

            credentials = get_credential_manager().decrypt_credentials(account.encrypted_credentials)
            settings = dict(account.settings or {})
            settings.setdefault("base_url", "https://api-seller.ozon.ru")
            settings["account_id"] = account.account_id
            connector = OzonConnector(credentials, settings)
            offer_ids = asyncio.run(connector.fetch_offer_ids_by_sku(skus))
            total_skus += len(skus)
            unresolved_skus += len(set(skus) - set(offer_ids))

            metric_filter = (
                TrafficMetric.platform_account_id == account.id,
                TrafficMetric.sku.in_(offer_ids),
            )
            if not args.apply:
                row_count = int(
                    db.scalar(select(func.count()).select_from(TrafficMetric).where(*metric_filter)) or 0
                )
                total_rows += row_count
                print(
                    f"{account.display_name or account.account_id}: "
                    f"resolved {len(offer_ids)}/{len(skus)} Ozon SKUs, rows {row_count}"
                )
                continue

            rows = db.scalars(
                select(TrafficMetric).where(*metric_filter)
            ).all()
            for row in rows:
                ozon_sku = row.sku
                seller_sku = offer_ids[ozon_sku]
                raw_data = dict(row.raw_data or {})
                raw_data["ozon_sku"] = ozon_sku
                raw_data["offer_id"] = seller_sku
                row.raw_data = raw_data
                row.sku = seller_sku
                row.record_key = _record_key(row, seller_sku)
                row.updated_at = datetime.now(UTC).replace(tzinfo=None)
            total_rows += len(rows)
            print(
                f"{account.display_name or account.account_id}: "
                f"resolved {len(offer_ids)}/{len(skus)} Ozon SKUs, rows {len(rows)}"
            )

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode = "updated" if args.apply else "would_update"
    print(f"{mode} {total_rows} rows from {total_skus - unresolved_skus}/{total_skus} resolved Ozon SKUs")
    if unresolved_skus:
        print(f"unresolved Ozon SKUs: {unresolved_skus}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
