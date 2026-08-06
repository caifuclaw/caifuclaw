# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""Trigger Fruugo-DMS order sync through the normal order pipeline."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import PlatformAccount, SyncSetting  # noqa: E402
from app.sync_engine import _connector_for_account, sync_account  # noqa: E402
from app.sync_runtime import JOB_TYPE_CATCHUP_ORDERS, JOB_TYPE_SYNC_ORDERS  # noqa: E402


DEFAULT_PLATFORM = "dmsmatrix"
DEFAULT_ACCOUNT_ID = "dms0001"
DEFAULT_DISPLAY_NAME = "Fruugo-DMS"


def _clean(value: object) -> str:
    return str(value or "").strip()


def _parse_since(args: argparse.Namespace) -> datetime | None:
    if args.full_refresh:
        return None
    if args.since:
        parsed = datetime.fromisoformat(args.since.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.replace(microsecond=0)
    if args.since_hours > 0:
        return (datetime.now(timezone.utc) - timedelta(hours=args.since_hours)).replace(tzinfo=None, microsecond=0)
    return None


def _account_query(args: argparse.Namespace):
    platform = _clean(args.platform).lower()
    account_id = _clean(args.account_id)
    display_name = _clean(args.display_name)

    stmt = select(PlatformAccount).where(PlatformAccount.enabled == True)
    if platform:
        stmt = stmt.where(PlatformAccount.platform == platform)
    if account_id:
        stmt = stmt.where(PlatformAccount.account_id == account_id)
    if display_name:
        stmt = stmt.where(
            or_(
                PlatformAccount.display_name == display_name,
                PlatformAccount.display_name.ilike(f"%{display_name}%"),
            )
        )
    return stmt.order_by(PlatformAccount.id).limit(1)


def _config_for_account(account: PlatformAccount) -> dict[str, Any]:
    return {
        "platform": account.platform,
        "account_id": account.account_id,
        "display_name": account.display_name,
        "enabled": account.enabled,
        "auth_type": account.credential_type or account.auth_type,
        "settings": dict(account.settings or {}),
    }


def _order_preview(order) -> dict[str, Any]:
    raw = order.raw_payload if isinstance(order.raw_payload, dict) else {}
    products = raw.get("products") if isinstance(raw.get("products"), list) else []
    return {
        "platform_order_id": order.platform_order_id,
        "platform_order_no": order.platform_order_no,
        "posting_number": order.posting_number,
        "platform_status": order.platform_status,
        "fulfillment_type": order.fulfillment_type,
        "created_at": _clean(raw.get("created_at") or raw.get("order_date") or raw.get("date_created")),
        "payment_at": _clean(raw.get("payment_at") or raw.get("paid_at")),
        "country_code": _clean(raw.get("country_code")),
        "currency_code": _clean(raw.get("currency_code") or raw.get("currency")),
        "order_amount": _clean(raw.get("order_amount") or raw.get("total_amount") or raw.get("amount")),
        "product_count": len(products),
        "first_sku": _clean((products[0] or {}).get("sku")) if products else "",
    }


def _mask_settings(settings: dict[str, Any]) -> dict[str, Any]:
    hidden = {"headers", "api_key", "access_token", "client_secret", "token", "secret", "password"}
    masked: dict[str, Any] = {}
    for key, value in sorted(settings.items()):
        masked[key] = "***" if key.lower() in hidden else value
    return masked


def _has_connector_overrides(args: argparse.Namespace) -> bool:
    return any(
        _clean(value)
        for value in (
            args.runtime_url,
            args.base_url,
            args.orders_path,
            args.orders_method,
            args.updated_since_param,
            args.page_size_param,
            args.order_status,
        )
    )


def _apply_connector_overrides(connector, args: argparse.Namespace, *, page_size: int) -> None:
    if _clean(args.runtime_url):
        connector.runtime_url = _clean(args.runtime_url).rstrip("/")
    if not hasattr(connector, "settings") or not isinstance(connector.settings, dict):
        return
    connector.settings["page_size"] = page_size
    if _clean(args.base_url):
        connector.settings["base_url"] = _clean(args.base_url).rstrip("/")
    if _clean(args.orders_path):
        connector.settings["orders_path"] = _clean(args.orders_path)
    if _clean(args.orders_method):
        connector.settings["orders_method"] = _clean(args.orders_method).upper()
    if _clean(args.updated_since_param):
        connector.settings["updated_since_param"] = _clean(args.updated_since_param)
    if _clean(args.page_size_param):
        connector.settings["page_size_param"] = _clean(args.page_size_param)
    if _clean(args.order_status):
        connector.settings["order_status"] = _clean(args.order_status)


async def _dry_run_fetch(
    db,
    account: PlatformAccount,
    args: argparse.Namespace,
    since: datetime | None,
    *,
    limit: int,
    write_normalized: bool,
    output_dir: Path,
) -> dict[str, Any]:
    if not account.encrypted_credentials:
        raise RuntimeError(f"Account has no encrypted credentials: {account.platform}/{account.account_id}")

    local_setting = db.scalar(
        select(SyncSetting).where(
            SyncSetting.platform == account.platform,
            SyncSetting.account_id == account.account_id,
        )
    )
    connector = _connector_for_account(db, account.platform, account.account_id, local_setting)
    if hasattr(connector, "settings") and isinstance(connector.settings, dict):
        connector.settings["account_id"] = account.account_id
    if local_setting:
        connector.settings["dry_run_fulfillment"] = local_setting.dry_run_fulfillment
    _apply_connector_overrides(connector, args, page_size=limit)
    orders = await connector.fetch_unprocessed_orders(since=since)
    result = {
        "status": "dry_run",
        "orders": len(orders),
        "preview": [_order_preview(order) for order in orders[:limit]],
        "runtime_url": getattr(connector, "runtime_url", ""),
        "settings": _mask_settings(connector.settings if hasattr(connector, "settings") else {}),
    }
    if write_normalized:
        from dataclasses import asdict

        output_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = output_dir / "fruugo_dms_normalized_orders.json"
        normalized_path.write_text(
            json.dumps([asdict(order) for order in orders], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["normalized_orders_path"] = str(normalized_path)
    return result


def _write_output(output_dir: Path, summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "fruugo_dms_order_sync_summary.json"
    summary["summary_path"] = str(path)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger Fruugo-DMS order sync and save orders into the local database.")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM, help="Platform code. Defaults to dmsmatrix.")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="Shop account id. Defaults to dms0001.")
    parser.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME, help="Shop display name filter. Defaults to Fruugo-DMS.")
    parser.add_argument("--full-refresh", action="store_true", help="Fetch without an incremental since timestamp.")
    parser.add_argument("--since", default="", help="Override since timestamp, for example 2026-07-01T00:00:00Z.")
    parser.add_argument("--since-hours", type=int, default=0, help="Fetch orders updated within the last N hours.")
    parser.add_argument("--catchup", action="store_true", help="Record this run as a catchup order job.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print connector results only; do not write orders.")
    parser.add_argument("--preview-limit", type=int, default=20, help="Maximum orders included in dry-run preview.")
    parser.add_argument("--write-normalized", action="store_true", help="Write full dry-run normalized orders to JSON.")
    parser.add_argument("--runtime-url", default="", help="Dry-run only: override connector runtime URL.")
    parser.add_argument("--base-url", default="", help="Dry-run only: override DMSMatrix API base URL.")
    parser.add_argument("--orders-path", default="", help="Dry-run only: override orders endpoint path.")
    parser.add_argument("--orders-method", choices=["GET", "POST", "get", "post"], default="", help="Dry-run only: override orders method.")
    parser.add_argument("--updated-since-param", default="", help="Dry-run only: override updated-since parameter name.")
    parser.add_argument("--page-size-param", default="", help="Dry-run only: override page-size parameter name.")
    parser.add_argument("--order-status", default="", help="Dry-run only: optional platform order status filter.")
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "output" / "fruugo_dms_order_sync"),
        help="Directory for summary JSON output.",
    )
    args = parser.parse_args()
    if not args.dry_run and _has_connector_overrides(args):
        raise SystemExit("Connector override options are supported only with --dry-run. Update the shop settings for real sync runs.")

    since = _parse_since(args)
    output_dir = Path(args.output_dir)
    started_at = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "ok": False,
        "started_at": started_at.isoformat(),
        "finished_at": "",
        "mode": "dry_run" if args.dry_run else "sync",
        "since": since.isoformat() if since else None,
        "full_refresh": bool(args.full_refresh),
        "result": {},
        "error": None,
    }

    with SessionLocal() as db:
        account = db.scalar(_account_query(args))
        if account is None:
            summary["error"] = (
                "Fruugo-DMS account not found: "
                f"platform={_clean(args.platform) or '*'}, "
                f"account_id={_clean(args.account_id) or '*'}, "
                f"display_name={_clean(args.display_name) or '*'}"
            )
            _write_output(Path(args.output_dir), summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 1

        summary["shop"] = {
            "platform": account.platform,
            "account_id": account.account_id,
            "display_name": account.display_name,
            "enabled": account.enabled,
        }

        try:
            if args.dry_run:
                summary["result"] = await _dry_run_fetch(
                    db,
                    account,
                    args,
                    since,
                    limit=max(1, args.preview_limit),
                    write_normalized=args.write_normalized,
                    output_dir=output_dir,
                )
            else:
                config = _config_for_account(account)
                summary["result"] = await sync_account(
                    db,
                    config,
                    full_refresh=args.full_refresh,
                    job_type=JOB_TYPE_CATCHUP_ORDERS if args.catchup else JOB_TYPE_SYNC_ORDERS,
                    since_override=since,
                )
            summary["ok"] = True
            return_code = 0
        except Exception as exc:  # noqa: BLE001
            summary["error"] = {"type": type(exc).__name__, "message": str(exc)}
            return_code = 1
        finally:
            summary["finished_at"] = datetime.now(timezone.utc).isoformat()
            _write_output(output_dir, summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))

    return return_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
