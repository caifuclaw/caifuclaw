# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

from .country_mapping import country_name_to_code


SELLER_FULFILLMENT_TYPES = {
    "",
    "FBS",
    "DBS",
    "SDS",
    "SELLER",
    "SELF",
    "SELF_SHIP",
    "SELF_SHIPPING",
    "CROSSBORDER",
    "CROSS_BORDER",
}

OVERSEAS_FULFILLMENT_TYPES = {
    "FBO",
    "FBP",
    "FBJ",
    "FBW",
    "FULFILLMENT",
    "OVERSEAS",
    "OVERSEAS_WAREHOUSE",
    "PLATFORM_WAREHOUSE",
    "ALLEGRO_FULFILLMENT",
    "MERCADO_FULFILLMENT",
}

JOOM_PLATFORM_CODES = {"joom", "joom_logistics", "joomlogistics"}


def _to_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_dict(*values) -> dict:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _payload_country_values(raw_payload: dict) -> list:
    if not isinstance(raw_payload, dict):
        return []
    delivery = _first_dict(raw_payload.get("delivery_method"), raw_payload.get("delivery"))
    shipping = raw_payload.get("shipping") if isinstance(raw_payload.get("shipping"), dict) else {}
    shipment = raw_payload.get("shipment") if isinstance(raw_payload.get("shipment"), dict) else {}
    destination = shipping.get("destination") if isinstance(shipping.get("destination"), dict) else {}
    receiver = shipping.get("receiver_address") if isinstance(shipping.get("receiver_address"), dict) else {}
    address = raw_payload.get("address") if isinstance(raw_payload.get("address"), dict) else {}
    return [
        raw_payload.get("country_code"),
        raw_payload.get("country"),
        raw_payload.get("country_name_cn"),
        raw_payload.get("countryName"),
        raw_payload.get("country_name"),
        delivery.get("country_code"),
        shipping.get("country_id"),
        shipping.get("country_code"),
        shipment.get("country_id"),
        shipment.get("country_code"),
        destination.get("country_code"),
        destination.get("country"),
        receiver.get("country_code"),
        receiver.get("country"),
        address.get("country_code"),
        address.get("country"),
    ]


def wildberries_payload_country_code(raw_payload: dict | None) -> str:
    if not isinstance(raw_payload, dict):
        return ""
    platform_text = _to_text(raw_payload.get("site")).lower()
    if platform_text and platform_text != "wildberries":
        return ""
    supply = raw_payload.get("supply") if isinstance(raw_payload.get("supply"), dict) else {}
    cross_border_type = _to_text(raw_payload.get("crossBorderType") or supply.get("crossBorderType"))
    if cross_border_type != "1":
        return ""
    offices = raw_payload.get("offices") if isinstance(raw_payload.get("offices"), list) else []
    office_values = [
        raw_payload.get("office"),
        raw_payload.get("officeName"),
        raw_payload.get("office_name"),
        supply.get("destinationOffice"),
        supply.get("destinationOfficeName"),
        *offices,
    ]
    office_text = " ".join(_to_text(value).lower() for value in office_values if _to_text(value))
    if any(marker in office_text for marker in ("beijing", "china", "\u043f\u0435\u043a\u0438\u043d", "\u4e2d\u56fd", "\u4e2d\u570b")):
        return "CN"
    return ""


def normalize_fulfillment_type(value) -> str:
    text = _to_text(value)
    if not text:
        return "FBS"
    normalized = (
        text.upper()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
    )
    compact = normalized.replace("_", "")
    if "ALLEGRO" in normalized and "FULFILL" in normalized:
        return "ALLEGRO_FULFILLMENT"
    if "MERCADO" in normalized and "FULFILL" in normalized:
        return "MERCADO_FULFILLMENT"
    if "JOOM" in normalized and "WAREHOUSE" in normalized:
        return "FBJ"
    if "OVERSEAS" in normalized:
        return "OVERSEAS_WAREHOUSE"
    if "FULFILL" in normalized:
        return "FULFILLMENT"
    if "WAREHOUSE" in normalized and normalized not in {"WAREHOUSE", "DEFAULT_WAREHOUSE"}:
        return "PLATFORM_WAREHOUSE"
    for known in ("FBO", "FBP", "FBJ", "FBW", "FBS", "DBS", "SDS"):
        if compact == known:
            return known
    if compact in {"CROSSBORDER", "CROSSBORDERS"}:
        return "CROSSBORDER"
    return normalized[:40]


def _payload_type_values(raw_payload: dict) -> list:
    if not isinstance(raw_payload, dict):
        return []
    delivery = _first_dict(raw_payload.get("delivery_method"), raw_payload.get("delivery"))
    shipping = raw_payload.get("shipping") if isinstance(raw_payload.get("shipping"), dict) else {}
    shipment = raw_payload.get("shipment") if isinstance(raw_payload.get("shipment"), dict) else {}
    logistics = raw_payload.get("logistics") if isinstance(raw_payload.get("logistics"), dict) else {}
    fulfillment = raw_payload.get("fulfillment") if isinstance(raw_payload.get("fulfillment"), dict) else {}
    provider = fulfillment.get("provider") if isinstance(fulfillment.get("provider"), dict) else {}
    shipping_option = raw_payload.get("shippingOption") if isinstance(raw_payload.get("shippingOption"), dict) else {}
    shipping_option_snake = raw_payload.get("shipping_option") if isinstance(raw_payload.get("shipping_option"), dict) else {}
    warehouse = raw_payload.get("warehouse") if isinstance(raw_payload.get("warehouse"), dict) else {}
    return [
        raw_payload.get("fulfillmentType"),
        raw_payload.get("fulfillment_type"),
        raw_payload.get("deliveryType"),
        raw_payload.get("delivery_type"),
        raw_payload.get("delivery_schema"),
        raw_payload.get("logisticsType"),
        raw_payload.get("logistics_type"),
        raw_payload.get("warehouseType"),
        raw_payload.get("warehouse_type"),
        delivery.get("delivery_schema"),
        delivery.get("type"),
        delivery.get("fulfillmentType"),
        delivery.get("fulfillment_type"),
        delivery.get("tpl_provider"),
        shipping.get("logistic_type"),
        shipping.get("mode"),
        shipping.get("warehouseType"),
        shipping.get("warehouse_type"),
        shipment.get("logistic_type"),
        shipment.get("mode"),
        logistics.get("type"),
        logistics.get("logistic_type"),
        provider.get("id"),
        provider.get("name"),
        fulfillment.get("status"),
        shipping_option.get("warehouseType"),
        shipping_option.get("warehouse_type"),
        shipping_option_snake.get("warehouseType"),
        shipping_option_snake.get("warehouse_type"),
        warehouse.get("type"),
        warehouse.get("warehouseType"),
        warehouse.get("warehouse_type"),
    ]


def _payload_name_values(raw_payload: dict) -> list:
    if not isinstance(raw_payload, dict):
        return []
    shipping_option = raw_payload.get("shippingOption") if isinstance(raw_payload.get("shippingOption"), dict) else {}
    shipping_option_snake = raw_payload.get("shipping_option") if isinstance(raw_payload.get("shipping_option"), dict) else {}
    warehouse = raw_payload.get("warehouse") if isinstance(raw_payload.get("warehouse"), dict) else {}
    return [
        raw_payload.get("source"),
        shipping_option.get("warehouseName"),
        shipping_option.get("warehouse_name"),
        shipping_option_snake.get("warehouseName"),
        shipping_option_snake.get("warehouse_name"),
        warehouse.get("name"),
        warehouse.get("warehouseName"),
        warehouse.get("warehouse_name"),
    ]


def _joom_physical_warehouse_payload(raw_payload: dict | None) -> bool:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    shipping_option = payload.get("shippingOption") if isinstance(payload.get("shippingOption"), dict) else {}
    shipping_option_snake = payload.get("shipping_option") if isinstance(payload.get("shipping_option"), dict) else {}
    warehouse_type = _to_text(
        shipping_option.get("warehouseType")
        or shipping_option.get("warehouse_type")
        or shipping_option_snake.get("warehouseType")
        or shipping_option_snake.get("warehouse_type")
    )
    return warehouse_type.casefold() == "physical"


def _joom_fbj_warehouse_payload(raw_payload: dict | None) -> bool:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    shipping_option = payload.get("shippingOption") if isinstance(payload.get("shippingOption"), dict) else {}
    shipping_option_snake = payload.get("shipping_option") if isinstance(payload.get("shipping_option"), dict) else {}
    warehouse_name = _to_text(
        shipping_option.get("warehouseName")
        or shipping_option.get("warehouse_name")
        or shipping_option_snake.get("warehouseName")
        or shipping_option_snake.get("warehouse_name")
    )
    warehouse_type = _to_text(
        shipping_option.get("warehouseType")
        or shipping_option.get("warehouse_type")
        or shipping_option_snake.get("warehouseType")
        or shipping_option_snake.get("warehouse_type")
    )
    if warehouse_name.casefold() == "joom logistics cn warehouse" and warehouse_type.casefold() == "fulfillment":
        return True
    return any(normalize_fulfillment_type(value) == "FBJ" for value in _payload_type_values(payload))


def infer_fulfillment_type(platform: str | None, raw_payload: dict | None, provided: str | None = None) -> str:
    provided_type = normalize_fulfillment_type(provided)
    if provided and provided_type not in SELLER_FULFILLMENT_TYPES:
        return provided_type
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    for value in _payload_type_values(payload):
        value_type = normalize_fulfillment_type(value)
        if value and value_type not in SELLER_FULFILLMENT_TYPES:
            return value_type
        if value and value_type in {"FBS", "DBS", "SDS", "CROSSBORDER"}:
            provided_type = value_type
    return provided_type or "FBS"


def infer_is_overseas_warehouse(platform: str | None, fulfillment_type: str | None, raw_payload: dict | None = None) -> bool:
    normalized = normalize_fulfillment_type(fulfillment_type)
    platform_text = _to_text(platform).lower()
    if platform_text in JOOM_PLATFORM_CODES:
        # Joom's physical warehouse type represents an overseas warehouse;
        # the logistics rule determines which carrier handles it.
        return _joom_physical_warehouse_payload(raw_payload)
    if normalized in OVERSEAS_FULFILLMENT_TYPES:
        return True
    if platform_text == "wildberries" and normalized not in {"", "FBS"}:
        return True
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    type_values = _payload_type_values(payload)
    type_text = " ".join(_to_text(value).lower() for value in type_values if value not in (None, ""))
    if any(marker in type_text for marker in ("fbj", "fbp", "fbo", "fbw", "overseas", "fulfillment")):
        return True
    name_text = " ".join(_to_text(value).lower() for value in _payload_name_values(payload) if value not in (None, ""))
    if any(marker in name_text for marker in ("fbj", "overseas", "fulfillment")):
        return True
    return "joom logistics" in name_text and "warehouse" in name_text


def order_is_overseas_warehouse(order) -> bool:
    platform = _to_text(getattr(order, "platform", None)).lower()
    if platform in JOOM_PLATFORM_CODES:
        return order_is_joom_overseas_warehouse(order)
    if bool(getattr(order, "is_overseas_warehouse", False)):
        return True
    return infer_is_overseas_warehouse(
        getattr(order, "platform", None),
        getattr(order, "fulfillment_type", None),
        getattr(order, "raw_payload", None),
    )


def order_is_joom_overseas_warehouse(order) -> bool:
    """Return whether a Joom order is fulfilled from a physical overseas warehouse."""
    platform = _to_text(getattr(order, "platform", None)).lower()
    return platform in JOOM_PLATFORM_CODES and _joom_physical_warehouse_payload(getattr(order, "raw_payload", None))


def order_is_joom_fbj_warehouse(order) -> bool:
    """Return whether a Joom order must only be exported for FBJ fulfillment."""
    platform = _to_text(getattr(order, "platform", None)).lower()
    if platform not in JOOM_PLATFORM_CODES:
        return False
    if normalize_fulfillment_type(getattr(order, "fulfillment_type", None)) == "FBJ":
        return True
    return _joom_fbj_warehouse_payload(getattr(order, "raw_payload", None))


def order_has_bsi_draft(order) -> bool:
    """Return whether the order already has a BSI draft number recorded."""
    return bool(_to_text(getattr(order, "bsi_order_no", None)))


def order_is_joom_bsi_draft(order) -> bool:
    """Return whether a Joom order is already in the BSI post-draft workflow."""
    platform = _to_text(getattr(order, "platform", None)).lower()
    return platform in JOOM_PLATFORM_CODES and order_has_bsi_draft(order)


def _normalized_shipping_type_values(value) -> set[str]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return {_to_text(item).replace("_", "").replace("-", "").lower() for item in values if _to_text(item)}


def order_is_joom_offline_shipping(order) -> bool:
    if _to_text(getattr(order, "platform", None)).lower() not in {"joom", "joom_logistics", "joomlogistics"}:
        return False
    raw_payload = getattr(order, "raw_payload", None)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    offline_types = {"offline", "offlineonly"}
    requirement_types = _normalized_shipping_type_values(payload.get("onlineShippingRequirement"))
    allowed_types = _normalized_shipping_type_values(payload.get("allowedShippingTypes"))
    if requirement_types.intersection(offline_types) or allowed_types.intersection(offline_types):
        return True
    online_required = payload.get("onlineShippingRequired")
    is_explicitly_offline = online_required is False or _to_text(online_required).lower() in {"false", "0", "no"}
    shipping_method = _to_text(payload.get("shippingMethod") or payload.get("shipping_method")).lower()
    return is_explicitly_offline and shipping_method == "manual"


def order_is_joom_standard_online_fulfillment(order) -> bool:
    """Return whether a Joom order uses the platform's normal online-label flow."""
    platform = _to_text(getattr(order, "platform", None)).lower()
    if platform not in JOOM_PLATFORM_CODES:
        return False
    if (
        order_is_joom_overseas_warehouse(order)
        or order_is_joom_fbj_warehouse(order)
        or order_is_joom_bsi_draft(order)
        or order_is_joom_offline_shipping(order)
    ):
        return False
    fulfillment_type = normalize_fulfillment_type(getattr(order, "fulfillment_type", None))
    return fulfillment_type == "DEFAULT" or fulfillment_type in SELLER_FULFILLMENT_TYPES


def joom_offline_shipping_target_status(order, tracking_number: str | None = None) -> str:
    if not order_is_joom_offline_shipping(order):
        return ""
    payload = getattr(order, "raw_payload", None)
    payload = payload if isinstance(payload, dict) else {}
    platform_status = _to_text(getattr(order, "platform_status", None) or payload.get("status")).lower()
    if platform_status in {"cancel", "canceled", "cancelled", "cancelled_by_seller", "paidbyjoomrefund", "refunded"}:
        return "已作废"
    if platform_status in {"complete", "completed"}:
        return "已完成"
    if platform_status in {"delivered", "received"}:
        return "已妥投"
    shipment = payload.get("shipment") if isinstance(payload.get("shipment"), dict) else {}
    tracking = _to_text(
        tracking_number
        or getattr(order, "shipment_tracking_number", None)
        or payload.get("shipment_tracking_number")
        or payload.get("tracking_number")
        or payload.get("trackingNumber")
        or shipment.get("trackingNumber")
        or shipment.get("tracking_number")
    )
    if platform_status == "shipped" and tracking:
        return "已发货"
    return ""


def _country_value_is_russia(value) -> bool:
    text = _to_text(value)
    if not text:
        return False
    if country_name_to_code(text) == "RU":
        return True
    upper = text.upper()
    if upper in {"RUS", "RUSSIA", "RUSSIAN FEDERATION"}:
        return True
    if "RUSSIA" in upper or "RUSSIAN FEDERATION" in upper or "\u0420\u041e\u0421\u0421" in upper:
        return True
    if "\u4fc4\u7f57\u65af" in text or "\u4fc4\u7f85\u65af" in text:
        return True
    normalized = upper
    for char in "()[]{}<>，,;:|/\\-_":
        normalized = normalized.replace(char, " ")
    return "RU" in {part.strip() for part in normalized.split()}


def _matches_russia_destination(order) -> bool:
    raw_payload = getattr(order, "raw_payload", None)
    if wildberries_payload_country_code(raw_payload if isinstance(raw_payload, dict) else {}) == "CN":
        return False
    country_values = [
        getattr(order, "country_code", None),
        getattr(order, "country_name_cn", None),
        *_payload_country_values(raw_payload if isinstance(raw_payload, dict) else {}),
    ]
    return any(_country_value_is_russia(value) for value in country_values)


def order_is_logistics_label_exempt(order) -> bool:
    platform_text = _to_text(getattr(order, "platform", None)).lower()
    return platform_text == "wildberries" and _matches_russia_destination(order)
