#!/usr/bin/env python3
"""Deprecated Joom warehouse shipping command.

FBJ orders are now exported to Excel and must not be marked shipped locally.
Use ``export_joom_fbj_orders.py`` instead.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.bsi_sdms import BSI_CARRIER_CODE  # noqa: E402
from app.logistics_rules import (  # noqa: E402
    load_enabled_logistics_rules,
    order_matches_logistics_carrier_rule,
)
from app.models import Order  # noqa: E402
from app.order_operation_logs import (  # noqa: E402
    ORDER_LOG_SYSTEM_SOURCE,
    SYSTEM_OPERATOR,
    add_order_operation_logs,
)
from app.order_types import (  # noqa: E402
    order_is_joom_bsi_draft,
    order_is_joom_fbj_warehouse,
    order_is_joom_overseas_warehouse,
)


JOOM_PLATFORMS = ("joom", "joom_logistics", "joomlogistics")
ORDER_STATUS_PENDING = "待处理"
ORDER_STATUS_SHIPPED = "已发货"
LOCAL_STATUS_SHIPPED = "shipped"
OPERATION_TYPE = "sync_logistics"
OPERATION_ATTRIBUTE = "同步物流信息"


@dataclass(frozen=True)
class CandidateSummary:
    order_id: int
    platform: str
    order_no: str
    status_before: str


@dataclass
class ProcessingResult:
    apply: bool
    candidates: list[CandidateSummary]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _order_display_number(row: Order) -> str:
    return row.platform_order_no or row.posting_number or row.platform_order_id or str(row.id)


def load_candidate_rows(
    db: Session,
    *,
    order_ids: Iterable[int] | None = None,
    limit: int = 0,
) -> list[Order]:
    rules = load_enabled_logistics_rules(db)
    stmt = (
        select(Order)
        .where(
            Order.platform.in_(JOOM_PLATFORMS),
            Order.biz_status == ORDER_STATUS_PENDING,
        )
        .order_by(Order.payment_at.asc().nulls_last(), Order.id.asc())
    )
    unique_order_ids = list(dict.fromkeys(int(order_id) for order_id in (order_ids or []) if int(order_id) > 0))
    if unique_order_ids:
        stmt = stmt.where(Order.id.in_(unique_order_ids))
    rows = [
        row
        for row in db.scalars(stmt).all()
        if order_is_joom_overseas_warehouse(row)
        and not order_matches_logistics_carrier_rule(row, rules, BSI_CARRIER_CODE)
        and not order_is_joom_bsi_draft(row)
        and not order_is_joom_fbj_warehouse(row)
    ]
    return rows[:limit] if limit > 0 else rows


def process_pending_joom_overseas_orders(
    db: Session,
    *,
    apply: bool = False,
    order_ids: Iterable[int] | None = None,
    limit: int = 0,
) -> ProcessingResult:
    rows = load_candidate_rows(db, order_ids=order_ids, limit=limit)
    result = ProcessingResult(
        apply=apply,
        candidates=[
            CandidateSummary(
                order_id=row.id,
                platform=row.platform or "",
                order_no=_order_display_number(row),
                status_before=row.biz_status or "",
            )
            for row in rows
        ],
    )
    if not apply or not rows:
        return result

    now = _utc_now()
    for row in rows:
        row.biz_status = ORDER_STATUS_SHIPPED
        row.local_status = LOCAL_STATUS_SHIPPED
        if row.label_printed_at is None:
            row.label_printed_at = now
        if row.shipped_at is None:
            row.shipped_at = now
        if row.marked_shipped_at is None:
            row.marked_shipped_at = now
        row.updated_at = now

    add_order_operation_logs(
        db,
        rows,
        operation_type=OPERATION_TYPE,
        operation_attribute=OPERATION_ATTRIBUTE,
        description=lambda order: (
            f"脚本处理：订单 {_order_display_number(order)} 为Joom海外仓订单，无需同步物流、面单和采购，"
            f"状态：{ORDER_STATUS_PENDING} -> {ORDER_STATUS_SHIPPED}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        event_key=lambda order: f"ship_pending_joom_overseas_orders:{order.id}",
        extra=lambda order: {
            "skipped_reason": "joom_overseas_warehouse",
            "status_before": ORDER_STATUS_PENDING,
            "status_after": ORDER_STATUS_SHIPPED,
            "script": Path(__file__).name,
        },
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deprecated. Use export_joom_fbj_orders.py for Joom FBJ orders."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes. Defaults to dry-run.")
    parser.add_argument("--order-id", type=int, action="append", default=[], help="Optional order id filter; repeatable.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum orders to process; 0 means no limit.")
    parser.add_argument("--max-print", type=int, default=50, help="Maximum candidate rows to print.")
    return parser.parse_args()


def print_result(result: ProcessingResult, *, max_print: int) -> None:
    mode = "apply" if result.apply else "dry-run"
    verb = "updated" if result.apply else "would_update"
    print(f"mode={mode} {verb}_orders={result.candidate_count}")
    for candidate in result.candidates[: max(0, max_print)]:
        print(
            f"order_id={candidate.order_id}\tplatform={candidate.platform or '-'}\t"
            f"order={candidate.order_no or '-'}\tstatus_before={candidate.status_before or '-'}"
        )
    if len(result.candidates) > max_print:
        print(f"... {len(result.candidates) - max_print} more orders")


def main() -> int:
    args = parse_args()
    with SessionLocal() as db:
        try:
            result = process_pending_joom_overseas_orders(
                db,
                apply=args.apply,
                order_ids=args.order_id,
                limit=args.limit,
            )
            print_result(result, max_print=args.max_print)
            if args.apply:
                db.commit()
            else:
                db.rollback()
            return 0
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())
