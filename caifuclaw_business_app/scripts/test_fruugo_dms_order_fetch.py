from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import asc, or_, select

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.connector_client import ConnectorRuntimeClient  # noqa: E402
from app.credential_manager import get_credential_manager  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import PlatformAccount  # noqa: E402
from app.settings import get_settings  # noqa: E402


DEFAULT_PLATFORM = "dmsmatrix"
DEFAULT_ACCOUNT_ID = "dms0001"
DEFAULT_DISPLAY_NAME = "Fruugo-DMS"


def _clean(value: object) -> str:
    return str(value or "").strip()


def _parse_since(args: argparse.Namespace) -> datetime | None:
    if args.full_refresh or (not args.since and args.since_hours <= 0):
        return None
    if args.since:
        value = args.since.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=args.since_hours)


def _mask_credentials(credentials: dict[str, Any]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in sorted(credentials.items()):
        text = _clean(value)
        if not text:
            masked[key] = ""
        elif len(text) <= 8:
            masked[key] = "***"
        else:
            masked[key] = f"{text[:4]}...{text[-4:]}"
    return masked


def _order_summary(order) -> dict[str, Any]:
    raw = order.raw_payload if isinstance(order.raw_payload, dict) else {}
    products = raw.get("products") if isinstance(raw.get("products"), list) else []
    return {
        "platform_order_id": order.platform_order_id,
        "platform_order_no": order.platform_order_no,
        "posting_number": order.posting_number,
        "platform_status": order.platform_status,
        "fulfillment_type": order.fulfillment_type,
        "is_overseas_warehouse": order.is_overseas_warehouse,
        "created_at": _clean(raw.get("created_at") or raw.get("order_date")),
        "payment_at": _clean(raw.get("payment_at")),
        "country_code": _clean(raw.get("country_code")),
        "currency_code": _clean(raw.get("currency_code")),
        "order_amount": _clean(raw.get("order_amount")),
        "shipment_id": _clean(raw.get("shipment_id")),
        "tracking_number": _clean(raw.get("shipment_tracking_number") or raw.get("tracking_number")),
        "product_count": len(products),
        "first_sku": _clean((products[0] or {}).get("sku")) if products else "",
    }


def _safe_settings(settings: dict[str, Any]) -> dict[str, Any]:
    hidden_keys = {"headers", "api_key", "access_token", "client_secret", "token", "secret"}
    safe: dict[str, Any] = {}
    for key, value in sorted(settings.items()):
        if key.lower() in hidden_keys:
            safe[key] = "***"
        else:
            safe[key] = value
    return safe


def _load_account(args: argparse.Namespace) -> tuple[PlatformAccount, dict[str, Any], dict[str, Any]]:
    db = SessionLocal()
    try:
        platform = _clean(args.platform).lower()
        account_id = _clean(args.account_id)
        display_name = _clean(args.display_name)

        stmt = select(PlatformAccount).where(PlatformAccount.enabled == True)
        if account_id:
            stmt = stmt.where(PlatformAccount.account_id == account_id)
        if platform:
            stmt = stmt.where(PlatformAccount.platform == platform)
        if display_name:
            stmt = stmt.where(
                or_(
                    PlatformAccount.display_name == display_name,
                    PlatformAccount.display_name.ilike(f"%{display_name}%"),
                )
            )

        row = db.scalar(stmt.order_by(asc(PlatformAccount.id)).limit(1))
        if row is None:
            raise RuntimeError(
                "Fruugo-DMS account not found. "
                f"platform={platform or '*'}, account_id={account_id or '*'}, display_name={display_name or '*'}"
            )
        if not row.encrypted_credentials:
            raise RuntimeError(f"Account has no encrypted credentials: {row.platform}/{row.account_id}")

        credentials = get_credential_manager().decrypt_credentials(row.encrypted_credentials)
        settings = dict(row.settings or {})
        return row, credentials, settings
    finally:
        db.close()


def _apply_overrides(settings: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    merged = dict(settings)
    if args.base_url:
        merged["base_url"] = args.base_url.strip()
    if args.orders_path:
        merged["orders_path"] = args.orders_path.strip()
    if args.orders_method:
        merged["orders_method"] = args.orders_method.strip().upper()
    if args.order_status:
        merged["order_status"] = args.order_status.strip()
    if args.updated_since_param:
        merged["updated_since_param"] = args.updated_since_param.strip()
    merged["page_size"] = args.limit
    if args.paginate:
        merged["orders_paginate"] = True
        merged["max_pages"] = args.max_pages
    return merged


def _result_path(output_dir: Path, filename: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / filename


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trigger Fruugo-DMS (DMSMatrix) order fetch through the connector runtime."
    )
    parser.add_argument("--platform", default=DEFAULT_PLATFORM, help="Platform code. Defaults to dmsmatrix.")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="Shop account id. Defaults to dms0001.")
    parser.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME, help="Shop display name filter.")
    parser.add_argument("--runtime-url", default="", help="Connector runtime URL. Defaults to app settings.")
    parser.add_argument("--base-url", default="", help="Override DMSMatrix base_url for this test run.")
    parser.add_argument("--orders-path", default="", help="Override orders_path for this test run.")
    parser.add_argument("--orders-method", choices=["GET", "POST", "get", "post"], default="", help="Override orders_method.")
    parser.add_argument("--order-status", default="", help="Optional platform order status filter.")
    parser.add_argument("--updated-since-param", default="", help="Override updated-since query parameter name.")
    parser.add_argument("--limit", type=int, default=20, help="Page size sent to the connector.")
    parser.add_argument("--paginate", action="store_true", help="Enable connector pagination.")
    parser.add_argument("--max-pages", type=int, default=1, help="Informational max pages for this test run.")
    parser.add_argument("--since-hours", type=int, default=0, help="Fetch orders updated within the last N hours. Defaults to full refresh.")
    parser.add_argument("--since", default="", help="Explicit since timestamp, for example 2026-06-30T00:00:00Z.")
    parser.add_argument("--full-refresh", action="store_true", help="Do not send an updated_since timestamp.")
    parser.add_argument("--write-normalized", action="store_true", help="Write normalized order payloads to output JSON.")
    parser.add_argument("--write-raw", action="store_true", help="Alias of --write-normalized.")
    parser.add_argument("--require-orders", action="store_true", help="Return exit code 2 when the API succeeds but returns no orders.")
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "output" / "fruugo_dms_order_fetch"),
        help="Directory for result JSON files.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    since = _parse_since(args)
    row, credentials, account_settings = _load_account(args)
    settings = _apply_overrides(account_settings, args)
    settings["account_id"] = row.account_id

    runtime_settings = get_settings()
    runtime_url = _clean(args.runtime_url) or runtime_settings.connector_runtime_url
    client = ConnectorRuntimeClient(
        runtime_url=runtime_url,
        platform=row.platform,
        credentials=credentials,
        settings=settings,
        account_id=row.account_id,
        internal_service_token=runtime_settings.internal_service_token,
    )

    started_at = datetime.now(UTC)
    summary: dict[str, Any] = {
        "ok": False,
        "started_at": started_at.isoformat(),
        "finished_at": "",
        "runtime_url": runtime_url,
        "shop": {
            "platform": row.platform,
            "account_id": row.account_id,
            "display_name": row.display_name,
            "enabled": row.enabled,
        },
        "credentials_keys": sorted(credentials.keys()),
        "credentials_masked": _mask_credentials(credentials),
        "settings": _safe_settings(settings),
        "effective_request": {
            "base_url": settings.get("base_url") or "https://api.dmsmatrix.net/apis",
            "orders_path": settings.get("orders_path") or "/Order/getOrders",
            "orders_method": settings.get("orders_method") or "POST",
            "updated_since_param": settings.get("updated_since_param") or "OrderDateFrom",
            "page_size_param": settings.get("page_size_param") or "PerPage",
            "page_size": settings.get("page_size") or 50,
        },
        "since": since.isoformat() if since else None,
        "order_count": 0,
        "orders": [],
        "error": None,
    }

    try:
        orders = await client.fetch_unprocessed_orders(since=since)
        summary["ok"] = True
        summary["order_count"] = len(orders)
        summary["orders"] = [_order_summary(order) for order in orders]
        if args.write_normalized or args.write_raw:
            normalized = [asdict(order) for order in orders]
            normalized_path = _result_path(output_dir, "fruugo_dms_normalized_orders.json")
            normalized_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
            summary["normalized_orders_path"] = str(normalized_path)
    except Exception as exc:
        summary["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary_path = _result_path(output_dir, "fruugo_dms_order_fetch_summary.json")
        summary["summary_path"] = str(summary_path)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["ok"]:
        return 1
    if args.require_orders and int(summary["order_count"]) <= 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
