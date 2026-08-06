"""Fallback Ozon tracking sync for postings stuck in awaiting_registration.

This script intentionally lives outside the main sync engine. It only applies
after the normal Ozon status refresh has waited long enough and Ozon still
returns no tracking number, but the official package-label PDF is available and
contains the posting number.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import asc, or_, select

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.connectors.base import NormalizedOrder, ShipmentResult  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.label_storage import is_real_label_pdf  # noqa: E402
from app.models import Order  # noqa: E402
from app.sync_engine import (  # noqa: E402
    apply_ozon_tracking_fallback_from_label,
    _connector_for_account,
)


OZON_PLATFORM = "ozon"
DEFAULT_STATUS = "待处理"
FALLBACK_STATUS = "awaiting_registration"
FALLBACK_SUBSTATUS = "posting_awaiting_registration"
DEFAULT_MIN_WAIT_MINUTES = 30


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
    stmt = (
        select(Order)
        .where(Order.platform == OZON_PLATFORM, Order.biz_status.in_(_status_values(args)))
        .where(or_(Order.shipment_tracking_number.is_(None), Order.shipment_tracking_number == ""))
    )

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


def _order_snapshot(row: Order, *, reason: str = "", action: str = "") -> dict[str, Any]:
    raw_payload = row.raw_payload or {}
    return {
        "id": row.id,
        "account_id": row.account_id or "",
        "shop_name": row.shop_name or "",
        "platform_order_no": row.platform_order_no or "",
        "posting_number": row.posting_number or "",
        "platform_status": row.platform_status or "",
        "platform_substatus": raw_payload.get("substatus") or "",
        "biz_status": row.biz_status or "",
        "local_status": row.local_status or "",
        "tracking_number": row.shipment_tracking_number or "",
        "logistics_last_synced_at": row.logistics_last_synced_at.isoformat() if row.logistics_last_synced_at else None,
        "error_message": row.error_message or "",
        "reason": reason,
        "action": action,
    }


def _label_text_contains_posting(content: bytes, posting_number: str) -> bool:
    posting_number = _clean(posting_number)
    if not posting_number:
        return False
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages[:3])
    except Exception:
        return False
    return posting_number in text


def _wait_window_elapsed(row: Order, min_wait_minutes: int, *, now: datetime) -> tuple[bool, str]:
    if min_wait_minutes <= 0:
        return True, ""
    last_synced_at = row.logistics_last_synced_at
    if last_synced_at is None:
        return False, "not_previously_refreshed"
    if last_synced_at.tzinfo is not None:
        last_synced_at = last_synced_at.astimezone(timezone.utc).replace(tzinfo=None)
    now_naive = now.astimezone(timezone.utc).replace(tzinfo=None)
    elapsed = now_naive - last_synced_at
    if elapsed < timedelta(minutes=min_wait_minutes):
        return False, f"wait_not_elapsed:{int(elapsed.total_seconds())}s"
    return True, ""


def _live_update_is_fallback_candidate(update) -> tuple[bool, str]:
    if not update:
        return False, "status_not_returned"
    raw_payload = update.raw_payload if isinstance(update.raw_payload, dict) else {}
    status = _clean(update.platform_status or raw_payload.get("status")).lower()
    substatus = _clean(raw_payload.get("substatus")).lower()
    tracking_number = _clean(update.shipment_tracking_number or raw_payload.get("tracking_number"))
    if status != FALLBACK_STATUS:
        return False, f"status_not_fallback:{status or '-'}"
    if substatus != FALLBACK_SUBSTATUS:
        return False, f"substatus_not_fallback:{substatus or '-'}"
    if tracking_number:
        return False, "tracking_already_available"
    return True, ""


def _normalized_order_from_row(row: Order, raw_payload: dict) -> NormalizedOrder:
    return NormalizedOrder(
        platform_order_id=row.platform_order_id,
        platform_order_no=row.platform_order_no or "",
        posting_number=row.posting_number or "",
        platform_status=row.platform_status or raw_payload.get("status") or "",
        raw_payload=raw_payload or row.raw_payload or {},
        fulfillment_type=row.fulfillment_type or "FBS",
        is_overseas_warehouse=bool(row.is_overseas_warehouse),
    )


async def _evaluate_and_apply_row(
    db,
    row: Order,
    connector,
    update,
    *,
    args: argparse.Namespace,
    started_at: datetime,
) -> dict[str, Any]:
    wait_ok, wait_reason = _wait_window_elapsed(row, int(args.min_wait_minutes or 0), now=started_at)
    if not wait_ok:
        return _order_snapshot(row, reason=wait_reason, action="skipped")

    live_ok, live_reason = _live_update_is_fallback_candidate(update)
    if not live_ok:
        return _order_snapshot(row, reason=live_reason, action="skipped")

    raw_payload = update.raw_payload if isinstance(update.raw_payload, dict) else {}
    posting_number = _clean(row.posting_number or raw_payload.get("posting_number") or update.posting_number)
    if not posting_number:
        return _order_snapshot(row, reason="missing_posting_number", action="skipped")

    shipment_result = ShipmentResult(
        platform_shipment_id=posting_number,
        tracking_number=posting_number,
        carrier="Ozon",
        status=FALLBACK_STATUS,
        raw_payload={"fallback_tracking": True, "posting_number": posting_number},
    )
    normalized = _normalized_order_from_row(row, raw_payload)

    try:
        label_result = await connector.fetch_label(shipment_result, normalized)
    except Exception as exc:
        return _order_snapshot(row, reason=f"label_fetch_failed:{str(exc)[:240]}", action="skipped")

    label_content = label_result.content
    if not is_real_label_pdf(label_content):
        return _order_snapshot(row, reason="label_not_real_pdf", action="skipped")
    if args.verify_label_text and not _label_text_contains_posting(label_content, posting_number):
        return _order_snapshot(row, reason="label_text_missing_posting", action="skipped")

    if args.dry_run:
        snapshot = _order_snapshot(row, reason="eligible", action="would_apply")
        snapshot["fallback_tracking_number"] = posting_number
        snapshot["label_bytes"] = len(label_content)
        return snapshot

    applied = await apply_ozon_tracking_fallback_from_label(
        db,
        row,
        connector,
        update,
        started_at=started_at,
    )
    if not applied.get("applied"):
        return _order_snapshot(row, reason=str(applied.get("reason") or "fallback_apply_failed"), action="skipped")
    snapshot = _order_snapshot(row, reason="applied", action="applied")
    snapshot.update(applied)
    return snapshot


def _compact_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = _clean(row.get("reason")) or "-"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _build_summary(
    *,
    args: argparse.Namespace,
    started_at: datetime,
    selected_count: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    applied = [row for row in rows if row.get("action") == "applied"]
    would_apply = [row for row in rows if row.get("action") == "would_apply"]
    preview_limit = max(0, int(args.show_orders or 0))
    return {
        "ok": True,
        "mode": "dry_run" if args.dry_run else "apply",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "platform": OZON_PLATFORM,
            "status": _status_values(args),
            "account_id": _split_values(args.account_id),
            "shop": _split_values(args.shop),
            "order": _split_values(args.order),
            "limit": int(args.limit or 0),
            "min_wait_minutes": int(args.min_wait_minutes or 0),
            "verify_label_text": bool(args.verify_label_text),
        },
        "selected_orders": selected_count,
        "applied_orders": len(applied),
        "would_apply_orders": len(would_apply),
        "skipped_orders": len([row for row in rows if row.get("action") == "skipped"]),
        "reason_counts": _compact_counts(rows),
        "orders": rows[:preview_limit],
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
        selected_rows = db.scalars(_order_query(args)).all()
        if args.limit and args.limit > 0:
            selected_rows = selected_rows[: args.limit]
        if not selected_rows:
            summary = _build_summary(args=args, started_at=started_at, selected_count=0, rows=[])
            _write_summary(args.summary_json, summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        rows_by_account: dict[str, list[Order]] = {}
        for row in selected_rows:
            rows_by_account.setdefault(row.account_id, []).append(row)

        results: list[dict[str, Any]] = []
        for account_id, account_rows in rows_by_account.items():
            connector = _connector_for_account(db, OZON_PLATFORM, account_id, None)
            posting_numbers = [row.posting_number for row in account_rows if row.posting_number]
            try:
                updates = await connector.fetch_order_status_updates(posting_numbers)
            except Exception as exc:
                for row in account_rows:
                    results.append(_order_snapshot(row, reason=f"status_refresh_failed:{str(exc)[:240]}", action="skipped"))
                continue

            updates_by_posting = {update.posting_number: update for update in updates}
            for row in account_rows:
                result = await _evaluate_and_apply_row(
                    db,
                    row,
                    connector,
                    updates_by_posting.get(row.posting_number),
                    args=args,
                    started_at=started_at,
                )
                results.append(result)

        if not args.dry_run:
            db.commit()
        summary = _build_summary(args=args, started_at=started_at, selected_count=len(selected_rows), rows=results)
        _write_summary(args.summary_json, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fallback Ozon tracking sync for awaiting_registration postings.")
    parser.add_argument("--status", default=DEFAULT_STATUS, help="Local biz_status filter. Comma-separated. Defaults to 待处理.")
    parser.add_argument("--account-id", action="append", default=[], help="Ozon shop account id. Can be repeated or comma-separated.")
    parser.add_argument("--shop", action="append", default=[], help="Shop id/name filter. Can be repeated or comma-separated.")
    parser.add_argument(
        "--order",
        action="append",
        default=[],
        help="Order id, platform_order_id, platform_order_no, or posting_number. Can be repeated or comma-separated.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum selected orders. 0 means no limit.")
    parser.add_argument(
        "--min-wait-minutes",
        type=int,
        default=DEFAULT_MIN_WAIT_MINUTES,
        help="Require the normal logistics refresh to have waited this long since last synced. Defaults to 30.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Verify candidates and labels but do not write the database.")
    parser.add_argument(
        "--no-verify-label-text",
        dest="verify_label_text",
        action="store_false",
        help="Do not require the PDF text to contain the posting number.",
    )
    parser.set_defaults(verify_label_text=True)
    parser.add_argument("--summary-json", default="", help="Optional path to write the summary JSON.")
    parser.add_argument("--show-orders", type=int, default=80, help="Maximum orders shown in summary output.")
    return parser.parse_args(argv)


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
