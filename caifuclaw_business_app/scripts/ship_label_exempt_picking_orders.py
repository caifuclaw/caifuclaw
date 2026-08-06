# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Order  # noqa: E402
from app.order_operation_logs import ORDER_LOG_SYSTEM_SOURCE, SYSTEM_OPERATOR, add_order_operation_logs  # noqa: E402
from app.order_types import order_is_logistics_label_exempt, order_is_overseas_warehouse  # noqa: E402
from app.product_models import PurchaseOrder, PurchaseOrderItem, PurchaseOrderLog, PurchaseOrderSource  # noqa: E402


ORDER_STATUS_PICKING = "配货中"
ORDER_STATUS_SHIPPED = "已发货"
LOCAL_STATUS_SHIPPED = "shipped"
OPERATION_TYPE = "label_exempt_picking_cleanup"
OPERATION_ATTRIBUTE = "历史配货中数据处理"


@dataclass
class CandidateSummary:
    order_id: int
    platform: str
    shop_name: str
    order_no: str
    reason: str
    purchase_source_ids: list[int] = field(default_factory=list)
    purchase_order_ids: list[int] = field(default_factory=list)


@dataclass
class CleanupResult:
    apply: bool
    candidates: list[CandidateSummary]
    purchase_source_count: int
    affected_purchase_order_ids: list[int]
    removed_source_ids: list[int] = field(default_factory=list)
    removed_item_ids: list[int] = field(default_factory=list)
    deleted_purchase_order_ids: list[int] = field(default_factory=list)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)


def _iso(value: object) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return None if value is None else str(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _order_display_number(row: Order) -> str:
    return row.platform_order_no or row.posting_number or row.platform_order_id or str(row.id)


def _skip_reason(row: Order) -> str:
    reasons: list[str] = []
    if order_is_overseas_warehouse(row):
        reasons.append("overseas_warehouse")
    if order_is_logistics_label_exempt(row):
        reasons.append("logistics_label_exempt")
    return ",".join(reasons) or "label_exempt"


def _is_label_exempt(row: Order) -> bool:
    return order_is_overseas_warehouse(row) or order_is_logistics_label_exempt(row)


def _source_snapshot(row: PurchaseOrderSource) -> dict:
    return {
        "id": row.id,
        "purchase_order_id": row.purchase_order_id,
        "purchase_order_item_id": row.purchase_order_item_id,
        "order_id": row.order_id,
        "order_item_id": row.order_item_id,
        "product_id": row.product_id,
        "product_name": row.product_name,
        "quantity": int(row.quantity or 0),
        "created_at": _iso(row.created_at),
    }


def _item_snapshot(row: PurchaseOrderItem) -> dict:
    return {
        "id": row.id,
        "purchase_order_id": row.purchase_order_id,
        "product_id": row.product_id,
        "product_name": row.product_name,
        "required_qty": int(row.required_qty or 0),
        "purchase_qty": int(row.purchase_qty or 0),
        "buyer_user_id": row.buyer_user_id,
        "buyer": row.buyer or "",
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _purchase_snapshot(db: Session, purchase: PurchaseOrder) -> dict:
    items = db.scalars(
        select(PurchaseOrderItem)
        .where(PurchaseOrderItem.purchase_order_id == purchase.id)
        .order_by(PurchaseOrderItem.id)
    ).all()
    sources = db.scalars(
        select(PurchaseOrderSource)
        .where(PurchaseOrderSource.purchase_order_id == purchase.id)
        .order_by(PurchaseOrderSource.id)
    ).all()
    return {
        "purchase_order": {
            "id": purchase.id,
            "purchase_no": purchase.purchase_no,
            "status": purchase.status,
            "purchase_date": _iso(purchase.purchase_date),
            "source_count": int(purchase.source_count or 0),
            "item_count": int(purchase.item_count or 0),
            "total_required_qty": int(purchase.total_required_qty or 0),
            "created_by": purchase.created_by,
            "remark": purchase.remark or "",
            "created_at": _iso(purchase.created_at),
            "updated_at": _iso(purchase.updated_at),
        },
        "items": [_item_snapshot(item) for item in items],
        "sources": [_source_snapshot(source) for source in sources],
    }


def _summarize_purchase_order(db: Session, purchase: PurchaseOrder, now: datetime) -> None:
    purchase.source_count = int(
        db.scalar(select(func.count(PurchaseOrderSource.id)).where(PurchaseOrderSource.purchase_order_id == purchase.id))
        or 0
    )
    purchase.item_count = int(
        db.scalar(select(func.count(PurchaseOrderItem.id)).where(PurchaseOrderItem.purchase_order_id == purchase.id))
        or 0
    )
    purchase.total_required_qty = int(
        db.scalar(
            select(func.coalesce(func.sum(PurchaseOrderItem.required_qty), 0)).where(
                PurchaseOrderItem.purchase_order_id == purchase.id
            )
        )
        or 0
    )
    purchase.updated_at = now


def _load_candidate_rows(
    db: Session,
    *,
    order_ids: Iterable[int] | None = None,
    platform: str = "",
    shop: str = "",
    limit: int = 0,
) -> list[Order]:
    stmt = select(Order).where(Order.biz_status == ORDER_STATUS_PICKING).order_by(Order.id)
    unique_order_ids = list(dict.fromkeys(int(order_id) for order_id in (order_ids or []) if int(order_id) > 0))
    if unique_order_ids:
        stmt = stmt.where(Order.id.in_(unique_order_ids))
    if platform:
        stmt = stmt.where(func.lower(Order.platform) == platform.strip().lower())
    if shop:
        shop_text = shop.strip()
        stmt = stmt.where((Order.shop_id == shop_text) | (Order.shop_name == shop_text))
    rows = [row for row in db.scalars(stmt).all() if _is_label_exempt(row)]
    if limit > 0:
        return rows[:limit]
    return rows


def _build_candidate_summaries(
    rows: list[Order],
    sources_by_order: dict[int, list[PurchaseOrderSource]],
) -> list[CandidateSummary]:
    summaries: list[CandidateSummary] = []
    for row in rows:
        sources = sources_by_order.get(row.id, [])
        summaries.append(
            CandidateSummary(
                order_id=row.id,
                platform=row.platform or "",
                shop_name=row.shop_name or row.shop_id or "",
                order_no=_order_display_number(row),
                reason=_skip_reason(row),
                purchase_source_ids=[source.id for source in sources],
                purchase_order_ids=sorted({source.purchase_order_id for source in sources if source.purchase_order_id}),
            )
        )
    return summaries


def process_label_exempt_picking_orders(
    db: Session,
    *,
    apply: bool = False,
    order_ids: Iterable[int] | None = None,
    platform: str = "",
    shop: str = "",
    limit: int = 0,
    delete_empty_purchase_orders: bool = False,
) -> CleanupResult:
    rows = _load_candidate_rows(db, order_ids=order_ids, platform=platform, shop=shop, limit=limit)
    row_ids = [row.id for row in rows]
    source_rows = (
        db.scalars(
            select(PurchaseOrderSource)
            .where(PurchaseOrderSource.order_id.in_(row_ids))
            .order_by(PurchaseOrderSource.purchase_order_id, PurchaseOrderSource.id)
        ).all()
        if row_ids
        else []
    )
    sources_by_order: dict[int, list[PurchaseOrderSource]] = {}
    for source in source_rows:
        sources_by_order.setdefault(source.order_id, []).append(source)

    affected_purchase_order_ids = sorted({source.purchase_order_id for source in source_rows if source.purchase_order_id})
    result = CleanupResult(
        apply=apply,
        candidates=_build_candidate_summaries(rows, sources_by_order),
        purchase_source_count=len(source_rows),
        affected_purchase_order_ids=affected_purchase_order_ids,
    )
    if not apply or not rows:
        return result

    now = _utc_now()
    reason_by_order = {row.id: _skip_reason(row) for row in rows}
    source_ids_by_order = {order_id: [source.id for source in sources] for order_id, sources in sources_by_order.items()}
    purchase_ids_by_order = {
        order_id: sorted({source.purchase_order_id for source in sources if source.purchase_order_id})
        for order_id, sources in sources_by_order.items()
    }
    before_purchase_snapshots = {
        purchase_id: _purchase_snapshot(db, purchase)
        for purchase_id in affected_purchase_order_ids
        if (purchase := db.get(PurchaseOrder, purchase_id)) is not None
    }

    for row in rows:
        row.biz_status = ORDER_STATUS_SHIPPED
        row.local_status = LOCAL_STATUS_SHIPPED
        row.label_printed_at = row.label_printed_at or now
        row.shipped_at = getattr(row, "shipped_at", None) or now
        row.marked_shipped_at = getattr(row, "marked_shipped_at", None) or now
        row.updated_at = now

    add_order_operation_logs(
        db,
        rows,
        operation_type=OPERATION_TYPE,
        operation_attribute=OPERATION_ATTRIBUTE,
        description=lambda order: (
            f"脚本处理：订单 {_order_display_number(order)} 无需平台物流/面单和采购，"
            f"状态：{ORDER_STATUS_PICKING} -> {ORDER_STATUS_SHIPPED}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        event_key=lambda order: f"{OPERATION_TYPE}:{order.id}",
        extra=lambda order: {
            "skipped_reason": reason_by_order.get(order.id, "label_exempt"),
            "status_before": ORDER_STATUS_PICKING,
            "status_after": ORDER_STATUS_SHIPPED,
            "removed_purchase_source_ids": source_ids_by_order.get(order.id, []),
            "affected_purchase_order_ids": purchase_ids_by_order.get(order.id, []),
            "script": Path(__file__).name,
        },
    )

    affected_item_ids = sorted({source.purchase_order_item_id for source in source_rows if source.purchase_order_item_id})
    for source in source_rows:
        result.removed_source_ids.append(source.id)
        db.delete(source)
    db.flush()

    for item_id in affected_item_ids:
        item = db.get(PurchaseOrderItem, item_id)
        if not item:
            continue
        remaining_required = int(
            db.scalar(
                select(func.coalesce(func.sum(PurchaseOrderSource.quantity), 0)).where(
                    PurchaseOrderSource.purchase_order_item_id == item.id
                )
            )
            or 0
        )
        if remaining_required <= 0:
            result.removed_item_ids.append(item.id)
            db.delete(item)
            continue
        item.required_qty = remaining_required
        if int(item.purchase_qty or 0) > remaining_required:
            item.purchase_qty = remaining_required
        item.updated_at = now
    db.flush()

    for purchase_id in affected_purchase_order_ids:
        purchase = db.get(PurchaseOrder, purchase_id)
        if not purchase:
            continue
        _summarize_purchase_order(db, purchase, now)
    db.flush()

    removed_order_ids_by_purchase: dict[int, list[int]] = {}
    removed_source_ids_by_purchase: dict[int, list[int]] = {}
    for source in source_rows:
        removed_order_ids_by_purchase.setdefault(source.purchase_order_id, []).append(source.order_id)
        removed_source_ids_by_purchase.setdefault(source.purchase_order_id, []).append(source.id)

    for purchase_id in affected_purchase_order_ids:
        purchase = db.get(PurchaseOrder, purchase_id)
        if not purchase:
            continue
        after_snapshot = _purchase_snapshot(db, purchase)
        log_snapshot = {
            "before": before_purchase_snapshots.get(purchase_id, {}),
            "after": after_snapshot,
            "removed_order_ids": sorted(set(removed_order_ids_by_purchase.get(purchase_id, []))),
            "removed_purchase_source_ids": removed_source_ids_by_purchase.get(purchase_id, []),
            "script": Path(__file__).name,
        }
        db.add(
            PurchaseOrderLog(
                purchase_order_id=purchase.id,
                purchase_no=purchase.purchase_no,
                action=OPERATION_TYPE,
                operator=SYSTEM_OPERATOR,
                snapshot=log_snapshot,
            )
        )
        if delete_empty_purchase_orders and int(purchase.source_count or 0) <= 0:
            result.deleted_purchase_order_ids.append(purchase.id)
            db.delete(purchase)

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ship historical picking orders that no longer need platform labels or purchase orders, "
            "and remove their purchase-order sources."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Write changes. Defaults to dry-run.")
    parser.add_argument("--order-id", type=int, action="append", default=[], help="Optional order id filter. Repeatable.")
    parser.add_argument("--platform", default="", help="Optional platform filter, for example wildberries.")
    parser.add_argument("--shop", default="", help="Optional exact shop_id or shop_name filter.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum matching orders to process; 0 means no limit.")
    parser.add_argument(
        "--delete-empty-purchase-orders",
        action="store_true",
        help="Delete purchase orders that become empty after removing these sources.",
    )
    parser.add_argument("--max-print", type=int, default=50, help="Maximum candidate rows to print.")
    return parser.parse_args()


def print_result(result: CleanupResult, *, max_print: int) -> None:
    mode = "apply" if result.apply else "dry-run"
    verb = "updated" if result.apply else "would_update"
    print(
        f"mode={mode} {verb}_orders={result.candidate_count} "
        f"purchase_sources={result.purchase_source_count} "
        f"purchase_orders={len(result.affected_purchase_order_ids)}"
    )
    if result.removed_source_ids:
        print(f"removed_purchase_sources={len(result.removed_source_ids)} removed_items={len(result.removed_item_ids)}")
    if result.deleted_purchase_order_ids:
        print(f"deleted_purchase_orders={len(result.deleted_purchase_order_ids)}")
    for candidate in result.candidates[:max(0, max_print)]:
        print(
            f"order_id={candidate.order_id}\tplatform={candidate.platform or '-'}\t"
            f"shop={candidate.shop_name or '-'}\torder={candidate.order_no or '-'}\t"
            f"reason={candidate.reason}\tpurchase_sources={','.join(map(str, candidate.purchase_source_ids)) or '-'}\t"
            f"purchase_orders={','.join(map(str, candidate.purchase_order_ids)) or '-'}"
        )
    if len(result.candidates) > max_print:
        print(f"... {len(result.candidates) - max_print} more orders")


def main() -> int:
    args = parse_args()
    with SessionLocal() as db:
        try:
            result = process_label_exempt_picking_orders(
                db,
                apply=args.apply,
                order_ids=args.order_id,
                platform=args.platform,
                shop=args.shop,
                limit=args.limit,
                delete_empty_purchase_orders=args.delete_empty_purchase_orders,
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
