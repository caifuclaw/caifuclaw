from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from sqlalchemy import asc, select

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.credential_manager import get_credential_manager  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import LogisticsAuthorization, Order  # noqa: E402
from app.wanbang import (  # noqa: E402
    WANBANG_CARRIER_CODE,
    WANBANG_SANDBOX_HOST,
    WanbangClient,
    build_wanbang_parcel_payload,
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _data(response: dict) -> dict:
    data = response.get("Data") if isinstance(response, dict) else {}
    return data if isinstance(data, dict) else {}


def _tracking_from_parcel(data: dict) -> str:
    tracking_result = data.get("TrackingNoProcessResult") if isinstance(data.get("TrackingNoProcessResult"), dict) else {}
    return _clean(
        data.get("FinalTrackingNumber")
        or data.get("TrackingNumber")
        or data.get("RealTrackingNumber")
        or tracking_result.get("Code")
    )


def _status_summary(data: dict) -> dict:
    tracking_result = data.get("TrackingNoProcessResult") if isinstance(data.get("TrackingNoProcessResult"), dict) else {}
    return {
        "reference_id": _clean(data.get("ReferenceId")),
        "process_code": _clean(data.get("ProcessCode")),
        "status": _clean(data.get("Status")),
        "tracking_number": _tracking_from_parcel(data),
        "tracking_result_code": _clean(tracking_result.get("Code")),
        "tracking_result_message": _clean(tracking_result.get("Message")),
    }


def _error_summary(exc: Exception) -> dict:
    return {"type": type(exc).__name__, "message": str(exc)}


async def _get_trackpoints(client: WanbangClient, tracking_number: str) -> dict:
    return await client._request_json(
        "GET",
        f"/api/trackPoints?trackingNumber={quote(tracking_number)}",
        operation="wanbang_trackpoints_query",
    )


def _sample_payload(reference_id: str, args: argparse.Namespace) -> dict:
    return {
        "ReferenceId": reference_id,
        "ShippingAddress": {
            "Contacter": args.recipient_name,
            "Company": "",
            "Street1": args.recipient_street,
            "Street2": "",
            "Street3": "",
            "City": args.recipient_city,
            "Province": "",
            "CountryCode": args.recipient_country,
            "Postcode": args.recipient_postcode,
            "Tel": args.recipient_phone,
            "Email": args.recipient_email,
            "TaxId": "",
        },
        "WeightInKg": args.weight_kg,
        "ItemDetails": [
            {
                "GoodsId": "SBX-SKU-1",
                "GoodsTitle": "Sandbox item",
                "DeclaredNameEn": "Sandbox item",
                "DeclaredNameCn": "test goods",
                "Quantity": 1,
                "DeclaredValue": {"Code": args.currency, "Value": args.declared_value},
                "ExportDeclaredValue": {"Code": args.currency, "Value": args.declared_value},
                "WeightInKg": args.weight_kg,
                "HSCode": args.hs_code,
            }
        ],
        "TotalValue": {"Code": args.currency, "Value": args.declared_value},
        "TotalVolume": {"Length": 10, "Width": 10, "Height": 5, "Unit": "CM"},
        "WithBatteryType": "NOBattery",
        "WarehouseCode": args.warehouse_code,
        "ShippingMethod": args.shipping_method,
        "ItemType": "SPX",
        "TradeType": "B2C",
        "AutoConfirm": args.auto_confirm,
        "AllowRemoteArea": True,
    }


def _recipient_address(args: argparse.Namespace) -> dict:
    return {
        "name": args.recipient_name,
        "company": "",
        "street": args.recipient_street,
        "street2": "",
        "street3": "",
        "city": args.recipient_city,
        "state": "",
        "countryCode": args.recipient_country,
        "postcode": args.recipient_postcode,
        "phone": args.recipient_phone,
        "email": args.recipient_email,
        "taxId": "",
    }


def _has_required_shipping_address(raw_payload: dict) -> bool:
    delivery = raw_payload.get("delivery") if isinstance(raw_payload.get("delivery"), dict) else {}
    address = delivery.get("address") if isinstance(delivery.get("address"), dict) else {}
    shipping = raw_payload.get("shipping") if isinstance(raw_payload.get("shipping"), dict) else {}
    receiver = shipping.get("receiver_address") if isinstance(shipping.get("receiver_address"), dict) else {}
    buyer = raw_payload.get("buyer") if isinstance(raw_payload.get("buyer"), dict) else {}
    return all(
        _clean(value)
        for value in [
            address.get("name") or address.get("company") or receiver.get("name") or buyer.get("name"),
            address.get("street") or address.get("address") or receiver.get("street1"),
            address.get("city") or receiver.get("city"),
            address.get("countryCode") or address.get("country_code") or receiver.get("country_code") or receiver.get("country"),
            address.get("zipCode") or address.get("postCode") or address.get("postcode") or receiver.get("postcode"),
        ]
    )


def _raw_payload_with_recipient_fallback(raw_payload: dict, args: argparse.Namespace) -> tuple[dict, bool]:
    if _has_required_shipping_address(raw_payload):
        return raw_payload, False
    if not args.use_sandbox_recipient_fallback:
        return raw_payload, False

    patched = dict(raw_payload)
    delivery = dict(patched.get("delivery") or {})
    address = dict(delivery.get("address") or {})
    fallback_address = _recipient_address(args)
    for key, value in fallback_address.items():
        if not _clean(address.get(key)):
            address[key] = value
    delivery["address"] = address
    patched["delivery"] = delivery
    return patched, True


def _load_auth(account_name: str | None) -> tuple[dict, dict, str]:
    db = SessionLocal()
    try:
        stmt = select(LogisticsAuthorization).where(
            LogisticsAuthorization.enabled == True,
            LogisticsAuthorization.carrier_code == WANBANG_CARRIER_CODE,
        )
        if account_name:
            stmt = stmt.where(LogisticsAuthorization.account_name == account_name)
        row = db.scalar(stmt.order_by(asc(LogisticsAuthorization.id)).limit(1))
        if row is None:
            suffix = f" account_name={account_name}" if account_name else ""
            raise RuntimeError(f"Enabled Wanbang logistics authorization not found{suffix}")
        credentials = get_credential_manager().decrypt_credentials(row.encrypted_credentials) if row.encrypted_credentials else {}
        settings = {**dict(row.config_json or {}), **dict(row.settings_json or {})}
        return credentials, settings, row.account_name
    finally:
        db.close()


def _payload_from_order(order_id: int, args: argparse.Namespace) -> tuple[dict, bool]:
    db = SessionLocal()
    try:
        order = db.get(Order, order_id)
        if order is None:
            raise RuntimeError(f"Order not found: {order_id}")
        raw_payload = order.raw_payload if isinstance(order.raw_payload, dict) else {}
        patched_raw_payload, used_recipient_fallback = _raw_payload_with_recipient_fallback(raw_payload, args)
        order_for_payload = SimpleNamespace(
            id=order.id,
            raw_payload=patched_raw_payload,
            currency=order.currency,
            internal_order_no=order.internal_order_no,
            posting_number=order.posting_number,
            platform_order_id=order.platform_order_id,
            platform_order_no=order.platform_order_no,
        )
        config = {
            "warehouse_code": args.warehouse_code,
            "shipping_method": args.shipping_method,
            "default_weight_kg": str(args.weight_kg),
            "default_declared_currency": args.currency,
            "default_declared_value": str(args.declared_value),
            "default_declared_name_en": "goods",
            "default_declared_name_cn": "test goods",
            "length_cm": "10",
            "width_cm": "10",
            "height_cm": "5",
        }
        return build_wanbang_parcel_payload(db, order_for_payload, config), used_recipient_fallback
    finally:
        db.close()


async def _write_label(client: WanbangClient, number: str, number_type: str, output_dir: Path) -> dict:
    content = await client.get_label(number, parcel_number_type=number_type)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"wanbang_sandbox_{number}_{number_type}.pdf".replace("/", "_")
    label_path = output_dir / filename
    label_path.write_bytes(content)
    return {
        "query_number": number,
        "parcel_number_type": number_type,
        "file_path": str(label_path),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run Wanbang sandbox parcel create, confirm, query, and label flow.")
    parser.add_argument("--account-name", default="", help="Wanbang logistics authorization account name.")
    parser.add_argument("--customer-code", default="", help="Override Wanbang customer_code.")
    parser.add_argument("--token", default="", help="Override Wanbang token.")
    parser.add_argument("--base-url", default=f"https://{WANBANG_SANDBOX_HOST}", help="Wanbang sandbox base URL.")
    parser.add_argument("--order-id", type=int, default=0, help="Build payload from a local order. Defaults to a synthetic sandbox payload.")
    parser.add_argument("--reference-id", default="", help="ReferenceId for synthetic payload. Defaults to SBX + timestamp.")
    parser.add_argument("--warehouse-code", required=True, help="Wanbang sandbox warehouse code.")
    parser.add_argument("--shipping-method", required=True, help="Wanbang sandbox shipping method.")
    parser.add_argument("--auto-confirm", action=argparse.BooleanOptionalAction, default=True, help="Set request AutoConfirm.")
    parser.add_argument("--confirm-after-create", action=argparse.BooleanOptionalAction, default=True, help="Call confirmation endpoint after create.")
    parser.add_argument("--skip-confirm", action="store_true", help="Do not call confirmation endpoint when AutoConfirm is false.")
    parser.add_argument("--dry-run", action="store_true", help="Only print the payload; do not call Wanbang.")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "output" / "wanbang_sandbox"), help="Directory for output JSON and labels.")
    parser.add_argument(
        "--use-sandbox-recipient-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When --order-id data has no complete shipping address, use the sandbox recipient fields instead.",
    )
    parser.add_argument("--recipient-name", default="Sandbox Recipient")
    parser.add_argument("--recipient-street", default="3 Maja 225")
    parser.add_argument("--recipient-city", default="Truskaw")
    parser.add_argument("--recipient-postcode", default="05-080")
    parser.add_argument("--recipient-country", default="PL")
    parser.add_argument("--recipient-phone", default="+48123456789")
    parser.add_argument("--recipient-email", default="demo@example.invalid")
    parser.add_argument("--weight-kg", type=float, default=0.3)
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--declared-value", type=float, default=1.0)
    parser.add_argument("--hs-code", default="")
    args = parser.parse_args()

    reference_id = _clean(args.reference_id) or f"SBX{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    used_recipient_fallback = False
    if args.order_id:
        payload, used_recipient_fallback = _payload_from_order(args.order_id, args)
    else:
        payload = _sample_payload(reference_id, args)
    if args.reference_id:
        payload["ReferenceId"] = args.reference_id

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "wanbang_sandbox_request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.dry_run:
        print(json.dumps({"dry_run": True, "payload": payload}, ensure_ascii=False, indent=2))
        return 0

    credentials, settings, account_name = _load_auth(args.account_name or None)
    if args.customer_code:
        credentials["customer_code"] = args.customer_code
    if args.token:
        credentials["token"] = args.token
    settings = {**settings, "base_url": args.base_url, "allow_sandbox": True}
    client = WanbangClient(credentials, settings)

    summary = {
        "account_name": account_name,
        "base_url": client.base_url,
        "reference_id": payload.get("ReferenceId"),
        "source_order_id": args.order_id or None,
        "used_sandbox_recipient_fallback": used_recipient_fallback,
        "process_code": "",
        "tracking_number": "",
        "create": None,
        "create_error": None,
        "confirm": None,
        "confirm_error": None,
        "parcel": None,
        "parcel_error": None,
        "status": None,
        "track": None,
        "track_error": None,
        "labels": [],
        "label_errors": [],
    }

    try:
        create_response = await client.create_parcel(payload)
    except Exception as exc:
        summary["create_error"] = _error_summary(exc)
        (output_dir / "wanbang_sandbox_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    summary["create"] = create_response
    process_code = _clean(_data(create_response).get("ProcessCode"))
    summary["process_code"] = process_code
    if not process_code:
        summary["create_error"] = {"type": "MissingProcessCode", "message": f"Wanbang sandbox create response missing ProcessCode: {create_response}"}
        (output_dir / "wanbang_sandbox_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    if args.confirm_after_create and not args.skip_confirm:
        try:
            summary["confirm"] = await client.confirm_parcel(process_code)
        except Exception as exc:
            summary["confirm_error"] = _error_summary(exc)

    try:
        parcel_response = await client.get_parcel(process_code)
        parcel_data = _data(parcel_response)
        summary["parcel"] = parcel_response
        summary["status"] = _status_summary(parcel_data)
        summary["tracking_number"] = _tracking_from_parcel(parcel_data)
    except Exception as exc:
        summary["parcel_error"] = _error_summary(exc)

    track_candidates = [
        _clean(summary["tracking_number"]),
        process_code,
        _clean(payload.get("ReferenceId")),
    ]
    seen_track_candidates: set[str] = set()
    for track_number in track_candidates:
        if not track_number or track_number in seen_track_candidates:
            continue
        seen_track_candidates.add(track_number)
        try:
            track_response = await _get_trackpoints(client, track_number)
            summary["track"] = {"query_number": track_number, "response": track_response}
            break
        except Exception as exc:
            summary["track_error"] = {"query_number": track_number, **_error_summary(exc)}

    labels: list[dict] = []
    label_errors: list[dict] = []
    for number, number_type in [(process_code, "ProcessCode"), (_clean(payload.get("ReferenceId")), "ReferenceId")]:
        if not number:
            continue
        try:
            labels.append(await _write_label(client, number, number_type, output_dir))
        except Exception as exc:
            label_errors.append({"number": number, "parcel_number_type": number_type, "error": str(exc)})

    summary["labels"] = labels
    summary["label_errors"] = label_errors
    (output_dir / "wanbang_sandbox_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["create"] and (summary["status"] or summary["track"]) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
