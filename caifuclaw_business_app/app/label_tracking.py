from __future__ import annotations

from datetime import datetime


def _to_text(value) -> str:
    return "" if value is None else str(value).strip()


def _first_value(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _looks_like_wildberries_payload(raw_payload: dict | None, platform: str | None = None) -> bool:
    if str(platform or "").lower() == "wildberries":
        return True
    if not isinstance(raw_payload, dict):
        return False
    site = _to_text(raw_payload.get("site")).lower()
    if site == "wildberries":
        return True
    return any(key in raw_payload for key in ("supplyId", "supply_id", "wildberries_sticker_barcode", "crossBorderType"))


def is_invalid_wildberries_tracking_number(value, raw_payload: dict | None = None, platform: str | None = None) -> bool:
    text = _to_text(value)
    if not text or not _looks_like_wildberries_payload(raw_payload, platform):
        return False
    supply = raw_payload.get("supply") if isinstance(raw_payload, dict) and isinstance(raw_payload.get("supply"), dict) else {}
    supply_id = _to_text(
        _first_value(
            raw_payload.get("supplyId") if isinstance(raw_payload, dict) else None,
            raw_payload.get("supply_id") if isinstance(raw_payload, dict) else None,
            supply.get("id"),
        )
    )
    return bool(text.startswith("*") or text.upper().startswith("WB-GI") or (supply_id and text == supply_id))


def is_invalid_ozon_tracking_number(value, raw_payload: dict | None = None, platform: str | None = None) -> bool:
    text = _to_text(value)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    is_ozon = str(platform or "").lower() == "ozon" or (
        "posting_number" in payload and str(payload.get("status") or "").lower().startswith("awaiting_")
    )
    if not text or not is_ozon:
        return False
    posting_number = _to_text(payload.get("posting_number"))
    status = _to_text(payload.get("status")).lower()
    substatus = _to_text(payload.get("substatus")).lower()
    if text != posting_number:
        return False
    fallback = payload.get("ozon_tracking_fallback")
    if fallback is True:
        return False
    if isinstance(fallback, dict) and fallback.get("tracking_number") == text:
        return False
    return status in {"awaiting_packaging", "awaiting_registration"} or substatus == "posting_created"


def clean_tracking_number(value, raw_payload: dict | None = None, platform: str | None = None) -> str:
    text = _to_text(value)
    if is_invalid_wildberries_tracking_number(text, raw_payload, platform):
        return ""
    if is_invalid_ozon_tracking_number(text, raw_payload, platform):
        return ""
    return text


def label_result_tracking_number(label_result) -> str:
    payload = getattr(label_result, "raw_payload", None)
    if not isinstance(payload, dict):
        return ""
    candidates = [
        payload.get("shipment_tracking_number"),
        payload.get("tracking_number"),
        payload.get("trackingNumber"),
        payload.get("trackingNo"),
        payload.get("waybill_number"),
        payload.get("waybillNumber"),
        payload.get("waybillNo"),
        payload.get("parcelId"),
        payload.get("parcelID"),
        payload.get("parcel_id"),
    ]
    stickers = payload.get("stickers") if isinstance(payload.get("stickers"), list) else []
    for sticker in stickers:
        if isinstance(sticker, dict):
            candidates.extend(
                [
                    sticker.get("shipment_tracking_number"),
                    sticker.get("tracking_number"),
                    sticker.get("trackingNumber"),
                    sticker.get("trackingNo"),
                    sticker.get("waybill_number"),
                    sticker.get("waybillNumber"),
                    sticker.get("waybillNo"),
                    sticker.get("parcelId"),
                    sticker.get("parcelID"),
                    sticker.get("parcel_id"),
                ]
            )
    for value in candidates:
        text = clean_tracking_number(value, payload, "wildberries")
        if text:
            return text
    return ""


def apply_label_result_tracking(order, shipment, label_result) -> bool:
    tracking_number = label_result_tracking_number(label_result)
    if not tracking_number:
        return False

    changed = False
    if getattr(order, "shipment_tracking_number", None) != tracking_number:
        order.shipment_tracking_number = tracking_number
        changed = True

    if shipment is not None and getattr(shipment, "tracking_number", None) != tracking_number:
        shipment.tracking_number = tracking_number
        changed = True

    raw_payload = getattr(order, "raw_payload", None)
    raw_payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
    label_payload = getattr(label_result, "raw_payload", None)
    if isinstance(label_payload, dict):
        raw_payload["label_payload"] = label_payload
        stickers = label_payload.get("stickers")
        if stickers is not None:
            raw_payload["stickers"] = stickers
        stickers_by_order_id = label_payload.get("stickers_by_order_id")
        if stickers_by_order_id is not None:
            raw_payload["stickers_by_order_id"] = stickers_by_order_id
    raw_payload["shipment_tracking_number"] = tracking_number
    raw_payload["tracking_number"] = tracking_number
    raw_payload["waybill_number"] = tracking_number
    raw_payload["label_tracking_number"] = tracking_number
    if getattr(order, "raw_payload", None) != raw_payload:
        order.raw_payload = raw_payload
        changed = True

    if changed and hasattr(order, "updated_at"):
        order.updated_at = datetime.utcnow()
    return changed
