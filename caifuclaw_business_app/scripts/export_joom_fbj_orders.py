#!/usr/bin/env python3
# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""Reconcile Joom FBJ orders registered in Order follow up to shipped."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.models import Order  # noqa: E402
from app.order_follow_up_export import (  # noqa: E402
    confirmed_joom_fbj_order_ids_for_follow_up_export,
    mark_joom_fbj_orders_shipped_after_follow_up_export,
)
from app.order_types import (  # noqa: E402
    JOOM_PLATFORM_CODES,
    order_is_joom_fbj_warehouse,
)


@dataclass(frozen=True)
class CandidateSummary:
    order_id: int
    order_no: str
    status_before: str
    registered_in_follow_up: bool


@dataclass(frozen=True)
class ReconcileResult:
    apply: bool
    candidates: list[CandidateSummary]
    shipped_order_ids: list[int]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def ready_to_ship_count(self) -> int:
        return sum(candidate.registered_in_follow_up for candidate in self.candidates)


def _order_no(row: Order) -> str:
    return str(row.platform_order_no or row.posting_number or row.platform_order_id or row.id)


def load_candidate_rows(
    db: Session,
    *,
    order_ids: Iterable[int] | None = None,
    limit: int = 0,
) -> list[Order]:
    stmt = (
        select(Order)
        .where(
            Order.platform.in_(JOOM_PLATFORM_CODES),
            Order.biz_status == "待处理",
        )
        .order_by(Order.payment_at.asc().nulls_last(), Order.id.asc())
    )
    requested_ids = list(dict.fromkeys(int(order_id) for order_id in (order_ids or []) if int(order_id) > 0))
    if requested_ids:
        stmt = stmt.where(Order.id.in_(requested_ids))
    rows = [row for row in db.scalars(stmt).all() if order_is_joom_fbj_warehouse(row)]
    return rows[:limit] if limit > 0 else rows


def reconcile_joom_fbj_orders(
    db: Session,
    *,
    apply: bool = False,
    order_ids: Iterable[int] | None = None,
    limit: int = 0,
) -> ReconcileResult:
    rows = load_candidate_rows(db, order_ids=order_ids, limit=limit)
    row_ids = [int(row.id) for row in rows]
    confirmed_ids = confirmed_joom_fbj_order_ids_for_follow_up_export(db, row_ids)
    candidates = [
        CandidateSummary(
            order_id=int(row.id),
            order_no=_order_no(row),
            status_before=str(row.biz_status or ""),
            registered_in_follow_up=int(row.id) in confirmed_ids,
        )
        for row in rows
    ]
    shipped_rows = (
        mark_joom_fbj_orders_shipped_after_follow_up_export(db, row_ids) if apply else []
    )
    return ReconcileResult(
        apply=apply,
        candidates=candidates,
        shipped_order_ids=[int(row.id) for row in shipped_rows],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark Joom FBJ orders shipped only after their Order follow up rows are confirmed."
    )
    parser.add_argument("--apply", action="store_true", help="Update confirmed orders. Defaults to dry-run.")
    parser.add_argument("--order-id", type=int, action="append", default=[], help="Optional order ID filter; repeatable.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum orders to reconcile; 0 means no limit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from app.database import SessionLocal

    with SessionLocal() as db:
        try:
            result = reconcile_joom_fbj_orders(
                db,
                apply=args.apply,
                order_ids=args.order_id,
                limit=args.limit,
            )
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            raise
    print(
        f"mode={'apply' if result.apply else 'dry-run'} "
        f"matched_orders={result.candidate_count} "
        f"registered_orders={result.ready_to_ship_count} "
        f"shipped_orders={len(result.shipped_order_ids)}"
    )
    for candidate in result.candidates:
        print(
            f"order_id={candidate.order_id}\torder={candidate.order_no}\t"
            f"status_before={candidate.status_before}\t"
            f"registered_in_follow_up={candidate.registered_in_follow_up}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
