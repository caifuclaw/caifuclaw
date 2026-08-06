# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Order  # noqa: E402
from app.order_types import wildberries_payload_country_code  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Wildberries Beijing cross-border orders from stale RU country data to CN."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database. Defaults to dry-run.")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of matching rows to process.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    updated: list[tuple[int, str, str | None, str | None]] = []
    inspected = 0

    with SessionLocal() as db:
        rows = db.scalars(select(Order).where(Order.platform == "wildberries").order_by(Order.id)).all()
        for row in rows:
            raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
            if wildberries_payload_country_code(raw_payload) != "CN":
                continue
            if (
                row.country_code == "CN"
                and row.country_name_cn == "中国"
                and raw_payload.get("country_code") == "CN"
            ):
                continue

            inspected += 1
            if args.limit and inspected > args.limit:
                break

            updated.append((row.id, row.posting_number or row.platform_order_id or "", row.country_code, row.country_name_cn))
            if not args.apply:
                continue

            raw_payload = dict(raw_payload)
            raw_payload["country_code"] = "CN"
            row.raw_payload = raw_payload
            row.country_code = "CN"
            row.country_name_cn = "中国"
            row.updated_at = datetime.utcnow()

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode = "updated" if args.apply else "would_update"
    print(f"{mode} {len(updated)} wildberries orders")
    for order_id, posting_number, old_code, old_name in updated:
        print(f"{order_id}\t{posting_number}\t{old_code or ''}\t{old_name or ''}\tCN\t中国")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
