from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select, text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.database import SessionLocal, engine  # noqa: E402
from app.models import Order, generate_internal_order_no  # noqa: E402


def _clean(value: object) -> str:
    return str(value or "").strip()


def _ensure_column_exists() -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS internal_order_no VARCHAR(32)"))
        conn.execute(text("ALTER TABLE IF EXISTS orders ALTER COLUMN internal_order_no TYPE VARCHAR(32)"))


def _ensure_unique_index() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_internal_order_no ON orders(internal_order_no)"))


def _new_internal_order_no(seen_values: set[str]) -> str:
    value = generate_internal_order_no()
    while value in seen_values:
        value = generate_internal_order_no()
    seen_values.add(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing or duplicate orders.internal_order_no values.")
    parser.add_argument("--dry-run", action="store_true", help="Print the rows that would be updated without writing changes.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to update; 0 means no limit.")
    parser.add_argument("--platform", default="", help="Optional platform filter, for example allegro.")
    args = parser.parse_args()

    _ensure_column_exists()

    db = SessionLocal()
    try:
        stmt = select(Order.id, Order.platform, Order.internal_order_no).order_by(Order.id.asc())
        if args.platform:
            stmt = stmt.where(Order.platform == args.platform)
        rows = db.execute(stmt).all()

        seen_values: set[str] = set()
        updates: list[tuple[int, str, str, str]] = []
        duplicate_count = 0
        missing_count = 0
        for order_id, platform, current_value in rows:
            current = _clean(current_value)
            if current and current not in seen_values:
                seen_values.add(current)
                continue
            if current:
                duplicate_count += 1
            else:
                missing_count += 1
            replacement = _new_internal_order_no(seen_values)
            updates.append((int(order_id), _clean(platform), current, replacement))
            if args.limit and len(updates) >= args.limit:
                break

        print(
            f"orders scanned={len(rows)} missing={missing_count} duplicates={duplicate_count} "
            f"updates={len(updates)} dry_run={args.dry_run}"
        )
        for order_id, platform, old_value, new_value in updates[:20]:
            print(f"order_id={order_id} platform={platform or '-'} old={old_value or '-'} new={new_value}")
        if len(updates) > 20:
            print(f"... {len(updates) - 20} more rows")

        if args.dry_run or not updates:
            return 0

        for order_id, _, _, new_value in updates:
            db.execute(
                text("UPDATE orders SET internal_order_no = :internal_order_no WHERE id = :order_id"),
                {"internal_order_no": new_value, "order_id": order_id},
            )
        db.commit()
        if args.limit or args.platform:
            print("skipped unique index creation because this was a partial backfill")
        else:
            _ensure_unique_index()
        print(f"updated {len(updates)} orders.internal_order_no values")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
