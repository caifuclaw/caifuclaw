# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

ALLEGRO_LABEL_UNAVAILABLE_MESSAGE = (
    "Allegro 当前订单没有可用于下载面单的 shipmentId；"
    "只有运单号时无法从 Allegro 下载面单 PDF。"
)


def _to_text(value) -> str:
    return str(value or "").strip()


def _raw_payload(order) -> dict:
    payload = getattr(order, "raw_payload", None)
    return payload if isinstance(payload, dict) else {}


def _shipment_rows(order) -> list[dict]:
    payload = _raw_payload(order)
    shipments_payload = payload.get("shipments_payload") if isinstance(payload.get("shipments_payload"), dict) else {}
    shipment_rows = []
    for value in (
        payload.get("shipments"),
        payload.get("_shipments"),
        shipments_payload.get("shipments"),
        (payload.get("_shipments_payload") or {}).get("shipments") if isinstance(payload.get("_shipments_payload"), dict) else None,
    ):
        if isinstance(value, list):
            shipment_rows.extend(item for item in value if isinstance(item, dict))
    return shipment_rows


def _order_identity_values(order) -> set[str]:
    payload = _raw_payload(order)
    values = {
        _to_text(getattr(order, "platform_order_id", "")),
        _to_text(getattr(order, "platform_order_no", "")),
        _to_text(getattr(order, "posting_number", "")),
        _to_text(getattr(order, "shipment_tracking_number", "")),
        _to_text(payload.get("id")),
        _to_text(payload.get("order_id")),
        _to_text(payload.get("platform_order_id")),
        _to_text(payload.get("tracking_number")),
        _to_text(payload.get("shipment_tracking_number")),
    }
    for row in _shipment_rows(order):
        values.add(_to_text(row.get("waybill")))
    return {value for value in values if value}


def _order_shipment_ids(order) -> list[str]:
    values: list[str] = []
    for row in _shipment_rows(order):
        for key in ("id", "shipmentId", "shipment_id"):
            value = _to_text(row.get(key))
            if value and value not in values:
                values.append(value)
    return values


def label_shipment_id_for_order(order, shipment=None) -> tuple[str, str]:
    """Return the platform shipment id for label download, or an explanatory reason."""
    platform = _to_text(getattr(order, "platform", "")).lower()
    fallback = _to_text(getattr(order, "posting_number", "")) or _to_text(getattr(order, "platform_order_id", ""))
    existing_id = _to_text(getattr(shipment, "platform_shipment_id", ""))

    if platform == "allegro":
        identity_values = _order_identity_values(order)
        if existing_id and existing_id not in identity_values:
            return existing_id, ""
        shipment_ids = _order_shipment_ids(order)
        if shipment_ids:
            return shipment_ids[0], ""
        return "", ALLEGRO_LABEL_UNAVAILABLE_MESSAGE

    return existing_id or fallback, ""
