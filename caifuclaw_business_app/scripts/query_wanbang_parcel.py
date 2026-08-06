# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import asc, select

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.credential_manager import get_credential_manager  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import LogisticsAuthorization  # noqa: E402
from app.wanbang import WANBANG_CARRIER_CODE, WanbangClient  # noqa: E402


def _clean(value: object) -> str:
    return str(value or "").strip()


def _data(response: dict) -> dict:
    data = response.get("Data") if isinstance(response, dict) else {}
    return data if isinstance(data, dict) else {}


def _parcel_summary(parcel: dict) -> dict:
    tracking_result = parcel.get("TrackingNoProcessResult") if isinstance(parcel.get("TrackingNoProcessResult"), dict) else {}
    return {
        "account_no": _clean(parcel.get("AccountNo")),
        "reference_id": _clean(parcel.get("ReferenceId")),
        "process_code": _clean(parcel.get("ProcessCode")),
        "index_number": _clean(parcel.get("IndexNumber")),
        "status": _clean(parcel.get("Status")),
        "final_tracking_number": _clean(parcel.get("FinalTrackingNumber")),
        "tracking_number": _clean(parcel.get("TrackingNumber")),
        "real_tracking_number": _clean(parcel.get("RealTrackingNumber")),
        "tracking_result_code": _clean(tracking_result.get("Code")),
        "tracking_result_message": _clean(tracking_result.get("Message")),
    }


def _track_summary(track_data: dict) -> dict:
    metadata = track_data.get("Metadata") if isinstance(track_data.get("Metadata"), dict) else {}
    points = track_data.get("TrackPoints") if isinstance(track_data.get("TrackPoints"), list) else []
    latest = points[-1] if points and isinstance(points[-1], dict) else {}
    return {
        "match": _clean(track_data.get("Match")),
        "tracking_number": _clean(track_data.get("TrackingNumber")),
        "status": _clean(track_data.get("Status")),
        "track_summary": _clean(track_data.get("TrackSummary")),
        "pod_ready": bool(track_data.get("PODReady")),
        "delivery_photo_ready": bool(track_data.get("DeliveryPhotoReady")),
        "metadata": {
            "track_item_id": _clean(metadata.get("TrackItemId")),
            "reference_id": _clean(metadata.get("ReferenceId")),
            "final_tracking_number": _clean(metadata.get("TrackingNumber")),
            "last_mile_carrier": _clean(metadata.get("LastMileCarrier")),
            "last_mile": _clean(metadata.get("LastMile")),
            "shipping_product_id": _clean(metadata.get("ShippingProductId")),
            "shipping_service_id": _clean(metadata.get("ShippingServiceId")),
            "origin_country_code": _clean(metadata.get("OriginCountryCode")),
            "destination_country_code": _clean(metadata.get("DestinationCountryCode")),
            "delivered_on": _clean(metadata.get("DeliveredOn")),
        },
        "latest_track_point": {
            "time": _clean(latest.get("Time")),
            "status": _clean(latest.get("Status")),
            "status_type": _clean(latest.get("StatusType")),
            "location": _clean(latest.get("Location")),
            "content": _clean(latest.get("Content")),
        },
        "track_point_count": len(points),
    }


def _load_client(account_name: str | None) -> tuple[WanbangClient, str]:
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
        return WanbangClient(credentials, settings), row.account_name
    finally:
        db.close()


def _override_base_url(client: WanbangClient, base_url: str | None) -> None:
    value = _clean(base_url)
    if value:
        client.base_url = value.rstrip("/")


async def _try_get_parcel(client: WanbangClient, number: str) -> tuple[dict | None, str | None]:
    try:
        response = await client.get_parcel(number)
        return response, None
    except Exception as exc:
        return None, str(exc)


async def _try_get_trackpoints(client: WanbangClient, number: str) -> tuple[dict | None, str | None]:
    try:
        response = await client._request_json(
            "GET",
            f"/api/trackPoints?trackingNumber={quote(number)}",
            operation="wanbang_trackpoints_query",
        )
        return response, None
    except Exception as exc:
        return None, str(exc)


async def _try_get_label(client: WanbangClient, number: str, number_type: str, output_dir: Path) -> tuple[dict | None, str | None]:
    try:
        content = await client.get_label(number, parcel_number_type=number_type)
        output_dir.mkdir(parents=True, exist_ok=True)
        label_path = output_dir / f"wanbang_{number}_{number_type}.pdf"
        label_path.write_bytes(content)
        return {
            "parcel_number_type": number_type,
            "file_path": str(label_path),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }, None
    except Exception as exc:
        return None, str(exc)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Query Wanbang parcel status and label PDF by process code or reference id.")
    parser.add_argument("number", nargs="?", default="DEMO-TRACKING-0001", help="Wanbang process code or reference id")
    parser.add_argument("--account-name", default="", help="Logistics authorization account name, defaults to first enabled Wanbang account")
    parser.add_argument("--base-url", default="", help="Override Wanbang API base URL for this query")
    parser.add_argument(
        "--parcel-number-type",
        choices=["auto", "ProcessCode", "ReferenceId"],
        default="auto",
        help="Number type used for label query. auto tries ProcessCode then ReferenceId.",
    )
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "output" / "wanbang_labels"), help="Directory for downloaded label PDFs")
    args = parser.parse_args()

    number = _clean(args.number)
    if not number:
        raise SystemExit("number is required")

    client, account_name = _load_client(args.account_name or None)
    _override_base_url(client, args.base_url)
    output_dir = Path(args.output_dir)
    summary = {
        "input_number": number,
        "account_name": account_name,
        "base_url": client.base_url,
        "track": None,
        "track_error": None,
        "parcel": None,
        "parcel_errors": [],
        "label": None,
        "label_errors": [],
    }

    track_response, track_error = await _try_get_trackpoints(client, number)
    track_data = _data(track_response or {})
    if track_response:
        summary["track"] = _track_summary(track_data)
    else:
        summary["track_error"] = track_error

    metadata = track_data.get("Metadata") if isinstance(track_data.get("Metadata"), dict) else {}
    process_code = _clean(metadata.get("TrackItemId"))
    reference_id = _clean(metadata.get("ReferenceId"))

    parcel_candidates = []
    for candidate in [process_code, number]:
        if candidate and candidate not in parcel_candidates:
            parcel_candidates.append(candidate)
    for candidate in parcel_candidates:
        parcel_response, parcel_error = await _try_get_parcel(client, candidate)
        if parcel_response:
            parcel = _data(parcel_response)
            summary["parcel"] = _parcel_summary(parcel)
            break
        summary["parcel_errors"].append({"number": candidate, "error": parcel_error})

    if summary["parcel"]:
        process_code = process_code or _clean(summary["parcel"].get("process_code"))
        reference_id = reference_id or _clean(summary["parcel"].get("reference_id"))

    label_candidates = []
    if args.parcel_number_type == "auto":
        label_candidates.extend(
            [
                (process_code, "ProcessCode"),
                (reference_id, "ReferenceId"),
                (number, "ProcessCode"),
                (number, "ReferenceId"),
            ]
        )
    else:
        label_candidates.append((number, args.parcel_number_type))

    seen_label_candidates = set()
    for label_number, number_type in label_candidates:
        label_number = _clean(label_number)
        key = (label_number, number_type)
        if not label_number or key in seen_label_candidates:
            continue
        seen_label_candidates.add(key)
        label, label_error = await _try_get_label(client, label_number, number_type, output_dir)
        if label:
            label["query_number"] = label_number
            summary["label"] = label
            break
        summary["label_errors"].append({"number": label_number, "parcel_number_type": number_type, "error": label_error})

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["track"] or summary["parcel"] or summary["label"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
