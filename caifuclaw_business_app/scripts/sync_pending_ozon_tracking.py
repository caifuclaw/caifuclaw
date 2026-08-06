# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""Trigger the existing logistics sync for local pending Ozon orders."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import asc, or_, select

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.label_tracking import clean_tracking_number  # noqa: E402
from app.models import Order  # noqa: E402
from app.sync_engine import (  # noqa: E402
    _order_tracking_number_for_refresh,
    refresh_order_logistics_for_rows,
    submit_platform_shipments_and_refresh_logistics,
)


OZON_PLATFORM = "ozon"
DEFAULT_STATUS = "待处理"


def _clean(value: object) -> str:
    return str(value or "").strip()


def _split_values(values: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for item in str(value or "").split(","):
            text = item.strip()
            if text and text not in result:
                result.append(text)
    return result


def _status_values(args: argparse.Namespace) -> list[str]:
    return _split_values([args.status]) or [DEFAULT_STATUS]


def _order_identifiers(args: argparse.Namespace) -> tuple[list[int], list[str]]:
    values = _split_values(args.order)
    numeric_ids: list[int] = []
    text_ids: list[str] = []
    for value in values:
        try:
            numeric_ids.append(int(value))
        except ValueError:
            pass
        text_ids.append(value)
    return numeric_ids, text_ids


def _order_query(args: argparse.Namespace):
    stmt = select(Order).where(Order.platform == OZON_PLATFORM, Order.biz_status.in_(_status_values(args)))

    account_ids = _split_values(args.account_id)
    if account_ids:
        stmt = stmt.where(Order.account_id.in_(account_ids))

    shop_names = _split_values(args.shop)
    if shop_names:
        shop_conditions = []
        for shop in shop_names:
            shop_conditions.extend(
                [
                    Order.shop_id == shop,
                    Order.shop_name == shop,
                    Order.shop_name.ilike(f"%{shop}%"),
                ]
            )
        stmt = stmt.where(or_(*shop_conditions))

    numeric_ids, text_ids = _order_identifiers(args)
    if numeric_ids or text_ids:
        identity_conditions = []
        if numeric_ids:
            identity_conditions.append(Order.id.in_(numeric_ids))
        if text_ids:
            identity_conditions.extend(
                [
                    Order.platform_order_id.in_(text_ids),
                    Order.platform_order_no.in_(text_ids),
                    Order.posting_number.in_(text_ids),
                ]
            )
        stmt = stmt.where(or_(*identity_conditions))

    return stmt.order_by(asc(Order.payment_at).nulls_last(), asc(Order.id))


def _safe_tracking_number(db, row: Order) -> str:
    try:
        return _order_tracking_number_for_refresh(db, row)
    except Exception:
        return clean_tracking_number(
            getattr(row, "shipment_tracking_number", ""),
            getattr(row, "raw_payload", None) or {},
            getattr(row, "platform", None),
        )


def _order_snapshot(db, row: Order) -> dict[str, Any]:
    return {
        "id": row.id,
        "account_id": row.account_id or "",
        "shop_name": row.shop_name or "",
        "platform_order_no": row.platform_order_no or "",
        "posting_number": row.posting_number or "",
        "platform_status": row.platform_status or "",
        "biz_status": row.biz_status or "",
        "local_status": row.local_status or "",
        "tracking_number": _safe_tracking_number(db, row),
        "error_message": row.error_message or "",
    }


def _rows_for_sync(db, rows: list[Order], *, include_tracked: bool, limit: int) -> list[Order]:
    selected = list(rows) if include_tracked else [row for row in rows if not _safe_tracking_number(db, row)]
    if limit > 0:
        selected = selected[:limit]
    return selected


def _reload_rows(db, order_ids: list[int]) -> list[Order]:
    if not order_ids:
        return []
    rows = db.scalars(select(Order).where(Order.id.in_(order_ids))).all()
    row_map = {row.id: row for row in rows}
    return [row_map[order_id] for order_id in order_ids if order_id in row_map]


def _compact_stats(stats: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(stats or {})
    order_results = result.pop("order_results", None)
    if isinstance(order_results, dict):
        result["order_result_count"] = len(order_results)
    return result


def _tracking_change_count(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> int:
    before_map = {row["id"]: _clean(row.get("tracking_number")) for row in before}
    return len(
        [
            row
            for row in after
            if _clean(row.get("tracking_number")) and _clean(row.get("tracking_number")) != before_map.get(row["id"], "")
        ]
    )


def _build_summary(
    *,
    args: argparse.Namespace,
    started_at: datetime,
    mode: str,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    trigger_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preview_limit = max(0, int(args.show_orders or 0))
    return {
        "ok": True,
        "mode": mode,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "platform": OZON_PLATFORM,
            "status": _status_values(args),
            "account_id": _split_values(args.account_id),
            "shop": _split_values(args.shop),
            "order": _split_values(args.order),
            "include_tracked": bool(args.include_tracked),
            "limit": int(args.limit or 0),
        },
        "selected_orders": len(before),
        "tracking_before": len([row for row in before if row.get("tracking_number")]),
        "tracking_after": len([row for row in after if row.get("tracking_number")]),
        "tracking_updated_orders": _tracking_change_count(before, after),
        "trigger_stats": _compact_stats(trigger_stats),
        "orders": after[:preview_limit],
    }


def _write_summary(path_value: str, summary: dict[str, Any]) -> None:
    path_text = _clean(path_value)
    if not path_text:
        return
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["summary_path"] = str(path)


async def run(args: argparse.Namespace) -> int:
    started_at = datetime.now(timezone.utc)
    with SessionLocal() as db:
        rows = db.scalars(_order_query(args)).all()
        selected_rows = _rows_for_sync(db, rows, include_tracked=args.include_tracked, limit=int(args.limit or 0))
        before = [_order_snapshot(db, row) for row in selected_rows]

        if args.dry_run or not selected_rows:
            mode = "dry_run" if args.dry_run else "trigger"
            summary = _build_summary(args=args, started_at=started_at, mode=mode, before=before, after=before)
            _write_summary(args.summary_json, summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        eligible_statuses = set(_status_values(args))
        if args.refresh_only:
            trigger_stats = await refresh_order_logistics_for_rows(
                db,
                selected_rows,
                eligible_statuses=eligible_statuses,
                preserve_biz_status=True,
            )
            mode = "refresh_only"
        else:
            trigger_stats = await submit_platform_shipments_and_refresh_logistics(
                db,
                selected_rows,
                eligible_statuses=eligible_statuses,
                preserve_biz_status_on_refresh=True,
            )
            mode = "trigger"

        db.expire_all()
        after_rows = _reload_rows(db, [row["id"] for row in before])
        after = [_order_snapshot(db, row) for row in after_rows]
        summary = _build_summary(
            args=args,
            started_at=started_at,
            mode=mode,
            before=before,
            after=after,
            trigger_stats=trigger_stats,
        )
        _write_summary(args.summary_json, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trigger the existing Ozon logistics sync for local 待处理 orders."
    )
    parser.add_argument("--status", default=DEFAULT_STATUS, help="Local biz_status filter. Comma-separated. Defaults to 待处理.")
    parser.add_argument("--account-id", action="append", default=[], help="Ozon shop account id. Can be repeated or comma-separated.")
    parser.add_argument("--shop", action="append", default=[], help="Shop id/name filter. Can be repeated or comma-separated.")
    parser.add_argument(
        "--order",
        action="append",
        default=[],
        help="Order id, platform_order_id, platform_order_no, or posting_number. Can be repeated or comma-separated.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum selected orders after tracking filter. 0 means no limit.")
    parser.add_argument("--include-tracked", action="store_true", help="Also trigger orders that already have a valid tracking number.")
    parser.add_argument("--refresh-only", action="store_true", help="Only trigger status/tracking refresh; do not trigger shipment submission.")
    parser.add_argument("--dry-run", action="store_true", help="Preview selected local orders only; do not call Ozon or write the database.")
    parser.add_argument("--summary-json", default="", help="Optional path to write the summary JSON.")
    parser.add_argument("--show-orders", type=int, default=50, help="Maximum orders shown in summary output.")
    return parser.parse_args(argv)


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
