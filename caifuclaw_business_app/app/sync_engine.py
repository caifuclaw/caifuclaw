import asyncio
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .connector_client import ConnectorRuntimeClient
from .connectors.base import NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .credential_manager import get_credential_manager
from .config_loader import require
from .country_mapping import country_name_cn, country_name_to_code
from .deadline_settings import load_shipping_deadline_settings, update_order_dispatch_deadline
from .email_service import (
    EMAIL_NOTIFICATION_WANBANG_TRACKING_FAILURE,
    get_email_setting,
    notification_recipients_for,
    send_email,
)
from .label_platforms import label_shipment_id_for_order
from .label_storage import is_real_label_pdf, save_label_pdf
from .label_tracking import apply_label_result_tracking, clean_tracking_number
from .logistics_rules import apply_logistics_rules, load_enabled_logistics_rules
from .models import LabelFile, Order, OrderItem, PlatformAccount, Shipment, SyncAccountState, SyncJobLog, SyncSetting, generate_internal_order_no
from .oauth_tokens import canonical_oauth_platform, ensure_access_token
from .order_operation_logs import (
    ORDER_LOG_SYSTEM_SOURCE,
    SYSTEM_OPERATOR,
    add_order_operation_log,
    order_log_changes,
    safe_exception_message,
)
from .order_types import (
    infer_fulfillment_type,
    infer_is_overseas_warehouse,
    joom_offline_shipping_target_status,
    order_is_joom_bsi_draft,
    order_is_joom_fbj_warehouse,
    order_is_joom_offline_shipping,
    order_is_logistics_label_exempt,
    order_is_overseas_warehouse,
    wildberries_payload_country_code,
)
from .settings import get_settings
from .api_logger import log_api_call
from .sync_runtime import (
    JOB_TYPE_CATCHUP_ORDERS,
    JOB_TYPE_SYNC_ORDERS,
    audit_sync_event,
    mark_sync_failed,
    mark_sync_skipped_locked,
    mark_sync_started,
    mark_sync_success,
    sync_job_lock,
)
from .wanbang import (
    WANBANG_CARRIER_NAME,
    create_wanbang_shipment_for_order,
    fetch_existing_wanbang_shipment_for_order,
    fetch_wanbang_reference_id_by_tracking,
    fetch_wanbang_label_for_order,
    looks_like_wanbang_process_code,
    order_routes_to_wanbang,
    order_uses_wanbang,
)


_account_sync_locks: dict[tuple[str, str], asyncio.Lock] = {}
MERCADO_INCREMENTAL_LOOKBACK_SECONDS = 30 * 60
GENERATED_INTERNAL_ORDER_NO_RE = re.compile(r"^[0-9A-F]{16}$")
OZON_TRACKING_FALLBACK_STATUS = "awaiting_registration"
OZON_TRACKING_FALLBACK_SUBSTATUS = "posting_awaiting_registration"
OZON_TRACKING_FALLBACK_SOURCE = "ozon_tracking_fallback"
WANBANG_PLATFORM_TRACKING_OPERATION = "wanbang_platform_tracking_backfill"
WANBANG_PLATFORM_TRACKING_FINAL_STATUSES = {"registered", "existing"}

logger = logging.getLogger(__name__)


def _account_sync_lock(platform: str, account_id: str) -> asyncio.Lock:
    key = (platform, account_id)
    lock = _account_sync_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _account_sync_locks[key] = lock
    return lock


def _mercado_incremental_lookback_seconds(settings: dict | None) -> int:
    value = (settings or {}).get("mercado_incremental_lookback_seconds")
    if value in (None, ""):
        value = (settings or {}).get("incremental_lookback_seconds", MERCADO_INCREMENTAL_LOOKBACK_SECONDS)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return MERCADO_INCREMENTAL_LOOKBACK_SECONDS


def _effective_order_sync_since(
    platform: str,
    last_sync_at: datetime | None,
    settings: dict | None = None,
    *,
    full_refresh: bool = False,
    since_override: datetime | None = None,
) -> datetime | None:
    if since_override is not None:
        return since_override
    if full_refresh or last_sync_at is None:
        return None
    if platform != "mercadolibre":
        return last_sync_at
    lookback_seconds = _mercado_incremental_lookback_seconds(settings)
    if lookback_seconds <= 0:
        return last_sync_at
    return last_sync_at - timedelta(seconds=lookback_seconds)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _platform_time_text(value) -> str | None:
    if value in (None, ""):
        return None
    parsed = _parse_platform_datetime(value)
    if parsed:
        return f"{parsed.replace(microsecond=0).isoformat()}Z"
    text_value = str(value).strip()
    return text_value or None


def _parse_platform_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text_value = str(value).strip()
        if not text_value:
            return None
        text_value = text_value.replace(" ", "T").replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text_value)
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def _is_mercado_payload(raw_payload: dict) -> bool:
    return bool(
        str(raw_payload.get("marketplace") or "").lower() == "mercadolibre"
        or raw_payload.get("mercado_api_mode")
        or raw_payload.get("mercado_store_type")
    )


def _shipping_deadline_value(raw_payload: dict, order: dict, shipping: dict, shipment: dict):
    mercado_expiration_date = _first_value(raw_payload.get("expiration_date"), order.get("expiration_date")) if _is_mercado_payload(raw_payload) else None
    return _first_value(
        raw_payload.get("last_ship_date"),
        raw_payload.get("ship_by_date"),
        raw_payload.get("delivery_date_end"),
        raw_payload.get("shipping_deadline_at"),
        mercado_expiration_date,
        ((shipping.get("lead_time") or {}).get("estimated_delivery_time") or {}).get("pay_before") if isinstance(shipping.get("lead_time"), dict) else None,
        ((shipment.get("lead_time") or {}).get("estimated_delivery_time") or {}).get("pay_before") if isinstance(shipment.get("lead_time"), dict) else None,
    )


def _first_value(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _first_dict(*values) -> dict:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _to_str(value) -> str:
    if value is None:
        return ""
    return str(value)


def _short_value(value) -> str:
    text = str(value or "").strip()
    return text or "-"


def _looks_like_generated_internal_order_no(value: object) -> bool:
    return bool(GENERATED_INTERNAL_ORDER_NO_RE.fullmatch(str(value or "").strip()))


def _order_log_snapshot(order: Order | None) -> dict[str, str]:
    if not order:
        return {}
    raw_payload = getattr(order, "raw_payload", None) or {}
    platform = getattr(order, "platform", "")
    posting_number = getattr(order, "posting_number", "")
    platform_status = getattr(order, "platform_status", "")
    return {
        "biz_status": _short_value(getattr(order, "biz_status", "")),
        "platform_status": _short_value(platform_status),
        "posting_number": _short_value(posting_number),
        "shipment_tracking_number": _short_value(
            clean_tracking_number(getattr(order, "shipment_tracking_number", ""), raw_payload, platform)
            or _tracking_number_from_payload(raw_payload)
            or _platform_tracking_number_from_posting(platform, posting_number, platform_status, raw_payload)
        ),
        "fulfillment_type": _short_value(getattr(order, "fulfillment_type", "")),
        "buyer_selected_logistics": _short_value(getattr(order, "buyer_selected_logistics", "")),
    }


ORDER_SYNC_LOG_LABELS = {
    "biz_status": "当前状态",
    "platform_status": "平台状态",
    "posting_number": "DEMO-ORDER-0001",
    "shipment_tracking_number": "DEMO-TRACKING-0001",
    "fulfillment_type": "履约类型",
    "buyer_selected_logistics": "买家自选物流",
}


def _order_sync_log_changes(order: Order, before: dict[str, str] | None) -> list[dict[str, str]]:
    return order_log_changes(before, _order_log_snapshot(order), ORDER_SYNC_LOG_LABELS)


def _order_sync_log_description(order: Order, before: dict[str, str] | None, *, created: bool) -> str:
    order_label = order.platform_order_no or order.posting_number or order.platform_order_id or str(order.id)
    if created or not before:
        parts = [
            f"订单 {order_label} 同步新增",
            f"平台状态：{_short_value(order.platform_status)}",
            f"当前状态：{_short_value(order.biz_status)}",
        ]
        tracking_number = _order_log_snapshot(order).get("shipment_tracking_number", "-")
        if tracking_number != "DEMO-TRACKING-0100":
            parts.append(f"货运单号：{tracking_number}")
        return "，".join(parts)

    changes = _order_sync_log_changes(order, before)
    if not changes:
        return (
            f"订单 {order_label} 同步更新，"
            f"平台状态：{_short_value(order.platform_status)}，"
            f"当前状态：{_short_value(order.biz_status)}，"
            "核心状态和物流信息无变化"
        )
    return f"订单 {order_label} 同步更新，" + "；".join(
        f"{change['label']}：{change['before']} -> {change['after']}" for change in changes
    )


def _tracking_number_from_payload(raw_payload: dict) -> str:
    if not isinstance(raw_payload, dict):
        return ""
    shipping = raw_payload.get("shipping") if isinstance(raw_payload.get("shipping"), dict) else {}
    shipment = raw_payload.get("shipment") if isinstance(raw_payload.get("shipment"), dict) else {}
    logistics = raw_payload.get("logistics") if isinstance(raw_payload.get("logistics"), dict) else {}
    tracking = raw_payload.get("tracking") if isinstance(raw_payload.get("tracking"), dict) else {}
    delivery = raw_payload.get("delivery") if isinstance(raw_payload.get("delivery"), dict) else {}
    shipments_payload = raw_payload.get("shipments_payload") if isinstance(raw_payload.get("shipments_payload"), dict) else {}

    def first_waybill(values) -> str:
        if not isinstance(values, list):
            return ""
        for item in values:
            if not isinstance(item, dict):
                continue
            value = _first_value(
                item.get("waybill"),
                item.get("waybillNumber"),
                item.get("waybill_number"),
                item.get("trackingNumber"),
                item.get("tracking_number"),
                item.get("trackingNo"),
                item.get("tracking_no"),
            )
            text = _to_str(value).strip()
            if text:
                return text
        return ""
    tracking_number = _to_str(
        _first_value(
            raw_payload.get("shipment_tracking_number"),
            raw_payload.get("tracking_number"),
            raw_payload.get("track_number"),
            raw_payload.get("trackingNumber"),
            raw_payload.get("trackNumber"),
            raw_payload.get("trackingNo"),
            raw_payload.get("tracking_no"),
            raw_payload.get("waybillNumber"),
            raw_payload.get("waybill_number"),
            shipment.get("shipment_tracking_number"),
            shipment.get("tracking_number"),
            shipment.get("track_number"),
            shipment.get("trackingNumber"),
            shipment.get("trackNumber"),
            shipment.get("trackingNo"),
            shipment.get("tracking_no"),
            shipment.get("waybillNumber"),
            shipment.get("waybill_number"),
            shipping.get("shipment_tracking_number"),
            shipping.get("tracking_number"),
            shipping.get("track_number"),
            shipping.get("trackingNumber"),
            shipping.get("trackNumber"),
            shipping.get("trackingNo"),
            shipping.get("tracking_no"),
            shipping.get("waybillNumber"),
            shipping.get("waybill_number"),
            logistics.get("shipment_tracking_number"),
            logistics.get("tracking_number"),
            logistics.get("trackingNumber"),
            logistics.get("number"),
            tracking.get("shipment_tracking_number"),
            tracking.get("tracking_number"),
            tracking.get("trackingNumber"),
            tracking.get("number"),
            delivery.get("trackingNumber"),
            delivery.get("tracking_number"),
            first_waybill(raw_payload.get("shipments")),
            first_waybill(shipping.get("shipments")),
            first_waybill(delivery.get("shipments")),
            first_waybill(shipments_payload.get("shipments")),
        )
    ).strip()
    return clean_tracking_number(tracking_number, raw_payload)


_OZON_POSTING_TRACKING_PENDING_STATUSES = {"awaiting_packaging", "awaiting_registration"}
_OZON_POSTING_TRACKING_PENDING_SUBSTATUSES = {"posting_created"}


def _ozon_posting_can_act_as_tracking(platform_status: str | None, raw_payload: dict | None = None) -> bool:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    status = str(platform_status or payload.get("status") or "").strip().lower()
    substatus = str(payload.get("substatus") or "").strip().lower()
    if status in _OZON_POSTING_TRACKING_PENDING_STATUSES:
        return False
    if substatus in _OZON_POSTING_TRACKING_PENDING_SUBSTATUSES:
        return False
    return bool(status)


def _ozon_label_not_ready(platform_status: str | None, raw_payload: dict | None = None, tracking_number: str | None = "") -> bool:
    if tracking_number:
        return False
    return not _ozon_posting_can_act_as_tracking(platform_status, raw_payload)


def _allegro_label_fetch_unavailable_message(value) -> bool:
    text = str(value or "")
    markers = (
        "Allegro 订单 shipment 面单接口不可用",
        "Feature unavailable",
        "只有运单号时无法从 Allegro 下载面单 PDF",
        "没有可用于下载面单的 shipmentId",
        "没有可用于下载面单的 Allegro shipmentId",
        "只有通过 Ship with Allegro/WZA 创建的 shipment 才能下载面单",
        "Allegro WZA 面单接口返回 406 Not Acceptable",
        "当前 shipment 没有可下载平台面单",
    )
    return any(marker in text for marker in markers)


def _platform_tracking_number_from_posting(
    platform: str | None,
    posting_number: str | None,
    platform_status: str | None = None,
    raw_payload: dict | None = None,
) -> str:
    if str(platform or "").lower() == "ozon":
        if not _ozon_posting_can_act_as_tracking(platform_status, raw_payload):
            return ""
        return str(posting_number or "").strip()
    return ""


def _country_name_cn(code: str | None) -> str:
    return country_name_cn(code)


def _country_name_to_code(name: str | None) -> str:
    """Convert country name (Russian/English/Chinese) to ISO country code."""
    return country_name_to_code(name)


def _platform_endpoint(endpoint_key: str) -> str:
    return require("platform_endpoints", endpoint_key)


def _ensure_base_url(settings: dict, endpoint_key: str) -> None:
    if settings.get("base_url"):
        return
    settings["base_url"] = _platform_endpoint(endpoint_key)


def _first_order(raw_payload: dict) -> dict:
    return _first_dict(*_as_list(raw_payload.get("orders")))


def _first_payment(raw_payload: dict) -> dict:
    order = _first_order(raw_payload)
    return _first_dict(*_as_list(order.get("payments")), *_as_list(raw_payload.get("payments")))


def _shipping_destination_address(shipping: dict) -> dict:
    destination = shipping.get("destination") if isinstance(shipping.get("destination"), dict) else {}
    return _first_dict(
        destination.get("shipping_address"),
        destination,
        shipping.get("receiver_address"),
        shipping.get("shipping_address"),
    )


def _extract_order_fields(raw_payload: dict) -> dict:
    customer = raw_payload.get("customer") or raw_payload.get("buyer") or raw_payload.get("user") or {}
    delivery = raw_payload.get("delivery_method") or raw_payload.get("delivery") or {}
    shipping = raw_payload.get("shipping") or {}
    shipment = raw_payload.get("shipment") if isinstance(raw_payload.get("shipment"), dict) else {}
    order = _first_order(raw_payload)
    payment = _first_payment(raw_payload)
    destination_address = _shipping_destination_address(shipping) or _shipping_destination_address(shipment)
    receiver = shipping.get("receiver_address") or destination_address or raw_payload.get("address") or {}
    analytics = raw_payload.get("analytics_data") or {}
    customer_address = customer.get("address") or {}
    products = raw_payload.get("products") or []
    financial = raw_payload.get("financial_data") or {}
    financial_products = financial.get("products") or []

    # --- country ---
    country_code = _to_str(
        _first_value(
            receiver.get("country_code"),
            (receiver.get("country") or {}).get("id") if isinstance(receiver.get("country"), dict) else None,
            (destination_address.get("country") or {}).get("id") if isinstance(destination_address.get("country"), dict) else None,
            shipping.get("country_id"),
            shipment.get("country_id"),
            delivery.get("country_code"),
            raw_payload.get("country_code"),
        )
    ).upper()
    # Fallback: resolve from country name (e.g. Ozon stores "Россия" in customer.address.country)
    if not country_code:
        country_name_raw = _first_value(
            customer_address.get("country"),
            receiver.get("country"),
            (receiver.get("country") or {}).get("name") if isinstance(receiver.get("country"), dict) else None,
            (destination_address.get("country") or {}).get("name") if isinstance(destination_address.get("country"), dict) else None,
            raw_payload.get("country"),
        )
        country_code = _country_name_to_code(country_name_raw)
    if country_code == "AR":
        country_name_cn = "阿根廷"
    else:
        country_name_cn = _country_name_cn(country_code)
    # analytics_data.region is a region name (e.g. "ЧЕЛЯБИНСКАЯ ОБЛАСТЬ"), not a country code
    # Only use it if it looks like a 2-letter code
    if not country_code:
        region = _to_str(analytics.get("region")).upper()
        if len(region) == 2 and region.isalpha():
            country_code = region
    wb_country_code = wildberries_payload_country_code(raw_payload)
    if wb_country_code:
        country_code = wb_country_code
        country_name_cn = _country_name_cn(country_code)

    # --- amount & currency ---
    amount = _first_value(
        raw_payload.get("order_amount"),
        raw_payload.get("sum"),
        raw_payload.get("total_amount"),
        raw_payload.get("amount"),
        order.get("paid_amount"),
        payment.get("total_paid_amount"),
        payment.get("transaction_amount"),
    )
    currency = _first_value(
        raw_payload.get("currency_code"),
        raw_payload.get("currency"),
        raw_payload.get("money_currency"),
        order.get("currency_id"),
        payment.get("currency_id"),
        shipping.get("currency_id"),
        shipment.get("currency_id"),
    )
    # Fallback: sum from products list (Ozon stores price/currency per product)
    if not amount and products:
        try:
            total = sum(float(p.get("price", 0)) * int(p.get("quantity", 1)) for p in products)
            amount = f"{total:.2f}"
        except (ValueError, TypeError):
            pass
    if not currency and products:
        currency = _first_value(*(_item_currency(p) for p in products if isinstance(p, dict)))
    # Fallback: financial_data.products
    if not amount and financial_products:
        try:
            total = sum(
                float(fp.get("price", 0)) * int(fp.get("quantity", 1))
                for fp in financial_products
            )
            amount = f"{total:.2f}"
        except (ValueError, TypeError):
            pass
    if not currency and financial_products:
        currency = _first_value(*(_item_currency(fp) for fp in financial_products if isinstance(fp, dict)))

    payment_at = _parse_platform_datetime(
        _first_value(
            payment.get("date_approved"),
            payment.get("date_created"),
            order.get("date_closed"),
            raw_payload.get("in_process_at"),
            raw_payload.get("payment_at"),
            raw_payload.get("created_at"),
            raw_payload.get("order_date"),
            raw_payload.get("date_created"),
            order.get("date_created"),
        )
    )
    platform_created_at = _parse_platform_datetime(
        _first_value(
            raw_payload.get("created_at"),
            raw_payload.get("order_date"),
            raw_payload.get("date_created"),
            order.get("date_created"),
            raw_payload.get("in_process_at"),
        )
    )
    shipping_deadline_at = _parse_platform_datetime(_shipping_deadline_value(raw_payload, order, shipping, shipment))
    if not shipping_deadline_at and payment_at:
        shipping_deadline_at = payment_at + timedelta(days=5)
    return {
        "site": _to_str(_first_value(raw_payload.get("site"), raw_payload.get("marketplace"), raw_payload.get("domain"))),
        "buyer_id": _to_str(_first_value(customer.get("id"), customer.get("customer_id"), raw_payload.get("customer_id"), raw_payload.get("buyer_id"))),
        "buyer_name": _to_str(_first_value(
            customer.get("name"),
            customer.get("full_name"),
            customer.get("nickname"),
            (order.get("buyer") or {}).get("nickname") if isinstance(order.get("buyer"), dict) else None,
            " ".join(
                part.strip()
                for part in [
                    _to_str((order.get("buyer") or {}).get("first_name") if isinstance(order.get("buyer"), dict) else ""),
                    _to_str((order.get("buyer") or {}).get("last_name") if isinstance(order.get("buyer"), dict) else ""),
                ]
                if part and part.strip()
            ),
            shipping.get("receiver_name"),
            receiver.get("name"),
            receiver.get("receiver_name"),
            (shipping.get("destination") or {}).get("receiver_name") if isinstance(shipping.get("destination"), dict) else None,
        )),
        "platform_created_at": platform_created_at,
        "platform_handover_deadline": _parse_platform_datetime(
            _first_value(
                raw_payload.get("shipment_date"),
                raw_payload.get("platform_handover_deadline"),
                raw_payload.get("ship_by_date"),
                raw_payload.get("delivery_date_begin"),
                shipping.get("date_first_printed"),
            )
        ),
        "handover_at": _parse_datetime(
            _first_value(
                raw_payload.get("shipped_at"),
                raw_payload.get("handover_at"),
                raw_payload.get("delivering_date"),
                raw_payload.get("last_ship_date"),
            )
        ),
        "country_code": country_code,
        "country_name_cn": country_name_cn,
        "buyer_selected_logistics": _to_str(
            _first_value(
                delivery.get("name"),
                shipping.get("tracking_method"),
                shipment.get("tracking_method"),
                ((shipping.get("lead_time") or {}).get("shipping_method") or {}).get("name") if isinstance(shipping.get("lead_time"), dict) else None,
                shipping.get("shipping_mode"),
                shipping.get("logistic_type"),
                (shipping.get("logistic") or {}).get("type") if isinstance(shipping.get("logistic"), dict) else None,
                raw_payload.get("buyer_selected_logistics"),
            )
        ),
        "order_amount": _to_str(amount),
        "currency": _to_str(currency),
        "shipment_tracking_number": _tracking_number_from_payload(raw_payload),
        "payment_at": payment_at,
        "shipping_deadline_at": shipping_deadline_at,
    }


def _item_sku(item: dict, platform: str = "") -> str:
    source_item = _first_dict(item.get("item"), item.get("product"), item.get("offer"), item)
    variation = _first_dict(item.get("variation"), source_item.get("variation"))
    raw_item = item.get("raw_payload") if isinstance(item.get("raw_payload"), dict) else {}
    raw_offer = raw_item.get("offer") if isinstance(raw_item.get("offer"), dict) else {}
    offer = _first_dict(item.get("offer"), raw_offer, source_item.get("offer"), source_item)
    external = offer.get("external") if isinstance(offer.get("external"), dict) else {}
    if _to_str(platform).strip().lower() == "allegro":
        seller_sku = _to_str(
            _first_value(
                external.get("id"),
                item.get("seller_sku"),
                item.get("sellerSku"),
                item.get("seller_custom_field"),
                raw_item.get("seller_sku"),
                raw_item.get("sellerSku"),
                raw_item.get("sku"),
                offer.get("seller_sku"),
                offer.get("sellerSku"),
                offer.get("sku"),
            )
        ).strip()
        if seller_sku:
            return seller_sku
    return _to_str(
        _first_value(
            item.get("offer_id"),
            item.get("offerId"),
            item.get("seller_sku"),
            item.get("seller_custom_field"),
            item.get("sku"),
            source_item.get("seller_sku"),
            source_item.get("seller_custom_field"),
            source_item.get("sku"),
            variation.get("seller_sku"),
            variation.get("seller_custom_field"),
            source_item.get("id"),
            item.get("item_id"),
            item.get("id"),
        )
    ).strip()


def _item_display_name(item: dict | None) -> str:
    item = item or {}
    source_item = _first_dict(item.get("item"), item.get("product"), item.get("offer"), item)
    variant = _first_dict(item.get("variant"), item.get("variation"), source_item.get("variant"), source_item.get("variation"))
    return _to_str(
        _first_value(
            item.get("platform_product_name"),
            item.get("product_name"),
            item.get("name"),
            item.get("title"),
            item.get("item_title"),
            item.get("productName"),
            item.get("product_name"),
            item.get("offer_name"),
            item.get("goods_name"),
            item.get("goodsName"),
            item.get("subject"),
            item.get("description"),
            source_item.get("name"),
            source_item.get("title"),
            source_item.get("item_title"),
            source_item.get("productName"),
            source_item.get("product_name"),
            source_item.get("offer_name"),
            source_item.get("subject"),
            variant.get("name"),
            variant.get("title"),
        )
    ).strip()


def _item_quantity(item: dict) -> int:
    value = _first_value(item.get("quantity"), item.get("count"), 1)
    try:
        return int(value or 1)
    except (TypeError, ValueError):
        return 1


def _item_unit_price(item: dict) -> str | None:
    source_item = _first_dict(item.get("item"), item.get("product"), item.get("offer"), item)
    value = _first_value(item.get("price"), item.get("unit_price"), item.get("full_unit_price"), item.get("price_unit"), item.get("priceWithoutCommission"), source_item.get("price"))
    if isinstance(value, dict):
        value = _first_value(value.get("amount"), value.get("value"), value.get("price"))
    return None if value in (None, "") else _to_str(value)


def _item_currency(item: dict, fallback: str = "") -> str:
    source_item = _first_dict(item.get("item"), item.get("product"), item.get("offer"), item)
    price = item.get("price")
    price_currency = price.get("currency") if isinstance(price, dict) else None
    return _to_str(_first_value(item.get("currency_code"), item.get("currency_id"), item.get("currency"), price_currency, source_item.get("currency_code"), source_item.get("currency_id"), fallback))


def _extract_order_items(raw_payload: dict) -> list[dict]:
    for value in (raw_payload.get("products"), raw_payload.get("items"), raw_payload.get("order_items")):
        items = [item for item in _as_list(value) if isinstance(item, dict)]
        if items:
            return items
    nested_items: list[dict] = []
    for order in _as_list(raw_payload.get("orders")):
        if not isinstance(order, dict):
            continue
        for value in (order.get("products"), order.get("items"), order.get("order_items")):
            nested_items.extend(item for item in _as_list(value) if isinstance(item, dict))
    if nested_items:
        return nested_items
    config = raw_payload.get("config") if isinstance(raw_payload.get("config"), dict) else {}
    return [item for item in _as_list(config.get("items")) if isinstance(item, dict)]


def _normalized_order_item_payloads(raw_payload: dict, fallback_currency: str = "", platform: str = "") -> list[dict]:
    items = _extract_order_items(raw_payload or {})
    if not items:
        return [{"sku": "", "platform_product_name": "", "quantity": 1, "unit_price": None, "currency": fallback_currency or "", "raw_payload": {}}]
    return [
        {
            "sku": _item_sku(item, platform),
            "platform_product_name": _item_display_name(item),
            "quantity": _item_quantity(item),
            "unit_price": _item_unit_price(item),
            "currency": _item_currency(item, fallback_currency),
            "raw_payload": item,
        }
        for item in items
    ]


def _has_real_order_items(raw_payload: dict | None, platform: str = "") -> bool:
    items = _extract_order_items(raw_payload or {})
    return any(_item_sku(item, platform) for item in items)


def _replace_order_items(db: Session, order: Order) -> None:
    if not order.id:
        db.flush()
    db.query(OrderItem).filter(OrderItem.order_id == order.id).delete(synchronize_session=False)
    for item in _normalized_order_item_payloads(order.raw_payload or {}, order.currency or "", order.platform):
        db.add(OrderItem(order_id=order.id, **item))


def _merge_payload_preserving_existing(existing: dict | None, incoming: dict | None) -> dict:
    if not isinstance(existing, dict) or not existing:
        return incoming or {}
    if not isinstance(incoming, dict) or not incoming:
        return existing
    merged = dict(existing)
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_payload_preserving_existing(merged.get(key), value)
        else:
            merged[key] = value
    return merged


def _normalized_order_from_row(row: Order) -> NormalizedOrder:
    return NormalizedOrder(
        platform_order_id=row.platform_order_id,
        platform_order_no=row.platform_order_no or "",
        posting_number=row.posting_number or "",
        platform_status=row.platform_status or "",
        raw_payload=row.raw_payload or {},
        fulfillment_type=row.fulfillment_type or infer_fulfillment_type(row.platform, row.raw_payload or {}),
        is_overseas_warehouse=order_is_overseas_warehouse(row),
    )


def _label_exists(db: Session, shipment_id: int | None, sha256: str) -> bool:
    if not shipment_id or not sha256:
        return False
    return bool(
        db.scalar(
            select(LabelFile.id)
            .where(LabelFile.shipment_id == shipment_id, LabelFile.sha256 == sha256)
            .limit(1)
        )
    )


def _pdf_text_contains(content: bytes, text: str) -> bool:
    text = str(text or "").strip()
    if not content or not text:
        return False
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages[:3])
    except Exception:
        return False
    return text in pdf_text


def _ozon_fallback_raw_payload(update: OrderStatusUpdate | None, row: Order) -> dict:
    update_payload = getattr(update, "raw_payload", None) if update else None
    if isinstance(update_payload, dict):
        return update_payload
    return row.raw_payload if isinstance(row.raw_payload, dict) else {}


def ozon_tracking_fallback_candidate_reason(row: Order, update: OrderStatusUpdate | None = None) -> tuple[bool, str]:
    if str(getattr(row, "platform", "") or "").strip().lower() != "ozon":
        return False, "not_ozon"
    payload = _ozon_fallback_raw_payload(update, row)
    status = str(
        (getattr(update, "platform_status", "") if update else "")
        or getattr(row, "platform_status", "")
        or payload.get("status")
        or ""
    ).strip().lower()
    substatus = str(payload.get("substatus") or "").strip().lower()
    tracking_number = clean_tracking_number(
        (getattr(update, "shipment_tracking_number", "") if update else "")
        or getattr(row, "shipment_tracking_number", "")
        or payload.get("tracking_number")
        or payload.get("shipment_tracking_number"),
        payload,
        "ozon",
    )
    if status != OZON_TRACKING_FALLBACK_STATUS:
        return False, f"status_not_fallback:{status or '-'}"
    if substatus != OZON_TRACKING_FALLBACK_SUBSTATUS:
        return False, f"substatus_not_fallback:{substatus or '-'}"
    if tracking_number:
        return False, "tracking_already_available"
    posting_number = str(getattr(row, "posting_number", "") or payload.get("posting_number") or "").strip()
    if not posting_number:
        return False, "missing_posting_number"
    return True, ""


async def apply_ozon_tracking_fallback_from_label(
    db: Session,
    row: Order,
    connector,
    update: OrderStatusUpdate | None = None,
    *,
    started_at: datetime | None = None,
) -> dict:
    """Use Ozon posting_number as tracking only after a real platform label is available."""
    started_at = started_at or datetime.utcnow()
    if started_at.tzinfo is not None:
        started_at = started_at.astimezone(timezone.utc).replace(tzinfo=None)
    candidate, reason = ozon_tracking_fallback_candidate_reason(row, update)
    if not candidate:
        return {"applied": False, "reason": reason}

    raw_payload = _ozon_fallback_raw_payload(update, row)
    posting_number = str(row.posting_number or raw_payload.get("posting_number") or "").strip()
    shipment_result = ShipmentResult(
        platform_shipment_id=posting_number,
        tracking_number=posting_number,
        carrier="Ozon",
        status=OZON_TRACKING_FALLBACK_STATUS,
        raw_payload={"fallback_tracking": True, "posting_number": posting_number},
    )
    normalized = NormalizedOrder(
        platform_order_id=row.platform_order_id,
        platform_order_no=row.platform_order_no or "",
        posting_number=row.posting_number or "",
        platform_status=row.platform_status or raw_payload.get("status") or "",
        raw_payload=raw_payload or row.raw_payload or {},
        fulfillment_type=row.fulfillment_type or "FBS",
        is_overseas_warehouse=order_is_overseas_warehouse(row),
    )
    try:
        label_result = await connector.fetch_label(shipment_result, normalized)
    except Exception as exc:
        return {"applied": False, "reason": f"label_fetch_failed:{str(exc)[:240]}"}

    content = label_result.content
    if not is_real_label_pdf(content):
        return {"applied": False, "reason": "label_not_real_pdf"}
    if not _pdf_text_contains(content, posting_number):
        return {"applied": False, "reason": "label_text_missing_posting"}

    delivery_method = raw_payload.get("delivery_method") if isinstance(raw_payload.get("delivery_method"), dict) else {}
    carrier = str(delivery_method.get("name") or delivery_method.get("tpl_provider") or "Ozon").strip()
    platform_status = str(raw_payload.get("status") or row.platform_status or OZON_TRACKING_FALLBACK_STATUS).strip()
    file_path, sha256 = save_label_pdf(
        row.tenant_id,
        "ozon",
        row.account_id,
        posting_number,
        content,
    )
    _upsert_shipment_info(
        db,
        row,
        platform_shipment_id=posting_number,
        tracking_number=posting_number,
        carrier=carrier,
        status=platform_status,
    )
    shipment = _latest_shipment_for_order(db, row.id)
    if shipment and not _label_exists(db, shipment.id, sha256):
        db.add(
            LabelFile(
                shipment_id=shipment.id,
                file_path=file_path,
                content_type=label_result.content_type or "application/pdf",
                sha256=sha256,
            )
        )

    fallback_marker = {
        "tracking_number": posting_number,
        "applied_at": started_at.isoformat(),
        "source": OZON_TRACKING_FALLBACK_SOURCE,
    }
    fallback_payload = dict(raw_payload or {})
    fallback_payload["ozon_tracking_fallback"] = fallback_marker
    row.shipment_tracking_number = posting_number
    row.platform_status = platform_status
    row.raw_payload = _merge_payload_preserving_existing(row.raw_payload or {}, fallback_payload)
    row.last_api_payload = fallback_payload
    row.logistics_last_synced_at = datetime.utcnow()
    row.error_message = ""
    if row.local_status in {"", "new", "failed_retryable", "shipment_created", "label_downloading"}:
        row.local_status = "label_saved"
    row.updated_at = datetime.utcnow()

    add_order_operation_log(
        db,
        order_id=row.id,
        operation_type="ozon_tracking_fallback",
        operation_attribute="同步物流信息",
        description=(
            f"Ozon 兜底：面单可下载但平台仍 {OZON_TRACKING_FALLBACK_STATUS}，"
            f"使用 posting_number 作为临时货运单号：{posting_number}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=started_at,
        event_key=f"ozon_tracking_fallback:{row.id}:{posting_number}",
        extra={
            "platform": "ozon",
            "account_id": row.account_id,
            "posting_number": posting_number,
            "fallback_tracking": True,
            "fallback_marker": fallback_marker,
            "source_status": platform_status,
            "source_substatus": raw_payload.get("substatus") if isinstance(raw_payload, dict) else "",
            "label_sha256": sha256,
        },
    )
    return {
        "applied": True,
        "reason": "applied",
        "tracking_number": posting_number,
        "label_path": file_path,
        "label_sha256": sha256,
        "shipment_id": shipment.id if shipment else None,
    }


def _shipment_payload_id(raw_payload: dict | None) -> str:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    shipment = payload.get("shipment") if isinstance(payload.get("shipment"), dict) else {}
    shipping = payload.get("shipping") if isinstance(payload.get("shipping"), dict) else {}
    logistics = payload.get("logistics") if isinstance(payload.get("logistics"), dict) else {}
    return _to_str(
        _first_value(
            payload.get("platform_shipment_id"),
            payload.get("shipment_id"),
            payload.get("shipping_id"),
            shipment.get("platform_shipment_id"),
            shipment.get("id"),
            shipment.get("shipment_id"),
            shipping.get("platform_shipment_id"),
            shipping.get("id"),
            shipping.get("shipment_id"),
            logistics.get("shipment_id"),
            logistics.get("id"),
        )
    ).strip()


def _latest_shipment_for_order(db: Session, order_id: int | None) -> Shipment | None:
    if not order_id:
        return None
    return db.scalar(select(Shipment).where(Shipment.order_id == order_id).order_by(Shipment.id.desc()))


def _upsert_shipment_info(
    db: Session,
    order: Order,
    *,
    platform_shipment_id: str = "",
    tracking_number: str = "",
    carrier: str = "",
    status: str = "",
) -> dict:
    platform_shipment_id = str(platform_shipment_id or "").strip()
    tracking_number = str(tracking_number or "").strip()
    carrier = str(carrier or "").strip()
    status = str(status or "").strip()
    if not any((platform_shipment_id, tracking_number, carrier, status)):
        return {"created": False, "updated": False, "tracking_updated": False}

    shipment = _latest_shipment_for_order(db, order.id)
    created = False
    updated = False
    tracking_updated = False
    if shipment is None:
        shipment = Shipment(
            order_id=order.id,
            platform_shipment_id=platform_shipment_id or order.posting_number or order.platform_order_id,
            tracking_number=tracking_number,
            carrier=carrier,
            status=status or "created",
        )
        db.add(shipment)
        db.flush()
        return {"created": True, "updated": True, "tracking_updated": bool(tracking_number)}

    if platform_shipment_id and shipment.platform_shipment_id != platform_shipment_id:
        shipment.platform_shipment_id = platform_shipment_id
        updated = True
    if tracking_number and shipment.tracking_number != tracking_number:
        shipment.tracking_number = tracking_number
        updated = True
        tracking_updated = True
    if carrier and shipment.carrier != carrier:
        shipment.carrier = carrier
        updated = True
    if status and shipment.status != status:
        shipment.status = status
        updated = True
    return {"created": created, "updated": updated, "tracking_updated": tracking_updated}


def _has_existing_platform_shipment(db: Session, order: Order) -> bool:
    shipment = _latest_shipment_for_order(db, order.id)
    if order_uses_wanbang(order) and shipment is not None:
        carrier = str(shipment.carrier or "").strip().lower()
        if not any(marker in carrier for marker in ("wanb", "万邦")):
            return False
    order_tracking_number = (
        clean_tracking_number(order.shipment_tracking_number, order.raw_payload or {}, order.platform)
        or _tracking_number_from_payload(order.raw_payload or {})
    )
    if order_uses_wanbang(order) and str(order.platform or "").strip().lower() == "dmsmatrix":
        shipment_tracking = clean_tracking_number(shipment.tracking_number, order.raw_payload or {}, order.platform) if shipment else ""
        return bool(order_tracking_number or shipment_tracking)
    if canonical_oauth_platform(order.platform) == "joom_logistics":
        if shipment is not None and (shipment.status or "").lower() in {"failed", "error"}:
            return False
        if shipment is not None and (shipment.tracking_number or "").strip():
            return True
        return bool(order_tracking_number)
    if str(order.platform or "").lower() == "ozon" and shipment is not None:
        posting_number = str(order.posting_number or order.platform_order_id or "").strip()
        shipment_status = str(shipment.status or "").strip().lower()
        shipment_id = str(shipment.platform_shipment_id or "").strip()
        shipment_tracking = str(shipment.tracking_number or "").strip()
        if (
            posting_number
            and shipment_status in _OZON_POSTING_TRACKING_PENDING_STATUSES
            and shipment_id in {"", posting_number}
            and shipment_tracking in {"", posting_number}
        ):
            return False
    if shipment is not None:
        if (shipment.status or "").lower() in {"failed", "error"}:
            return False
        shipment_tracking = clean_tracking_number(shipment.tracking_number, order.raw_payload or {}, order.platform)
        if (shipment.platform_shipment_id or "").strip() or shipment_tracking:
            return True
    return bool(
        order_tracking_number
        or _shipment_payload_id(order.raw_payload or {})
    )


def _latest_real_label_for_order(db: Session, order: Order) -> LabelFile | None:
    shipment = _latest_shipment_for_order(db, order.id)
    if shipment is None:
        return None
    label = db.scalar(
        select(LabelFile).where(LabelFile.shipment_id == shipment.id).order_by(LabelFile.id.desc())
    )
    if not label or not label.file_path:
        return None
    try:
        path = Path(label.file_path)
        if path.exists() and path.stat().st_size > 0 and is_real_label_pdf(path.read_bytes()):
            return label
    except Exception:
        return None
    return None


def _order_tracking_number_for_refresh(db: Session, order: Order) -> str:
    payload = getattr(order, "raw_payload", None) or {}
    tracking_number = (
        clean_tracking_number(
            getattr(order, "shipment_tracking_number", None),
            payload,
            getattr(order, "platform", None),
        )
        or _tracking_number_from_payload(payload)
        or _platform_tracking_number_from_posting(
            getattr(order, "platform", None),
            getattr(order, "posting_number", None),
            getattr(order, "platform_status", None),
            payload,
        )
    )
    if not tracking_number:
        shipment = _latest_shipment_for_order(db, order.id)
        tracking_number = clean_tracking_number(shipment.tracking_number, payload, getattr(order, "platform", None)) if shipment else ""
    return tracking_number


def _order_needs_wanbang_reference_backfill(order: Order, tracking_number: str) -> bool:
    if not tracking_number:
        return False
    current = str(getattr(order, "internal_order_no", "") or "").strip()
    if current and not _looks_like_generated_internal_order_no(current) and not looks_like_wanbang_process_code(current):
        return False
    return order_routes_to_wanbang(order)


def _store_wanbang_reference_lookup(order: Order, lookup, tracking_number: str) -> None:
    raw_payload = getattr(order, "raw_payload", None)
    raw_payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
    raw_response = lookup.raw_response if isinstance(getattr(lookup, "raw_response", None), dict) else {}
    raw_payload["wanbang_trackpoints"] = {
        "queried_tracking_number": tracking_number,
        "reference_id": getattr(lookup, "reference_id", "") or "",
        "tracking_number": getattr(lookup, "tracking_number", "") or "",
        "track_item_id": getattr(lookup, "track_item_id", "") or "",
        "match": getattr(lookup, "match", "") or "",
        "raw_response": raw_response,
    }
    order.raw_payload = raw_payload
    if hasattr(order, "last_api_payload"):
        order.last_api_payload = raw_response


def _wanbang_platform_tracking_state(order: Order) -> dict:
    raw_payload = getattr(order, "raw_payload", None)
    if not isinstance(raw_payload, dict):
        return {}
    value = raw_payload.get("wanbang_platform_tracking")
    return dict(value) if isinstance(value, dict) else {}


def _store_wanbang_platform_tracking_state(order: Order, state: dict) -> None:
    raw_payload = getattr(order, "raw_payload", None)
    raw_payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
    raw_payload["wanbang_platform_tracking"] = state
    order.raw_payload = raw_payload


def _wanbang_platform_tracking_log_request(order: Order, tracking_number: str) -> dict:
    return {
        "order_id": order.id,
        "platform_order_id": str(getattr(order, "platform_order_id", "") or ""),
        "tracking_number": tracking_number,
        "carrier": WANBANG_CARRIER_NAME,
    }


def _wanbang_platform_tracking_failure_state(
    previous: dict,
    *,
    tracking_number: str,
    attempt_count: int,
    attempted_at: datetime,
    source: str,
    error: str,
) -> dict:
    state = {
        "status": "failed",
        "tracking_number": tracking_number,
        "carrier": WANBANG_CARRIER_NAME,
        "attempt_count": attempt_count,
        "last_attempt_at": attempted_at.isoformat(),
        "source": source,
        "error": error[:1000],
    }
    if str(previous.get("tracking_number") or "").strip() == tracking_number:
        for key in (
            "failure_email_recipient",
            "failure_email_sent_at",
            "failure_email_error",
            "failure_email_attempt_count",
        ):
            if previous.get(key) not in (None, ""):
                state[key] = previous[key]
    return state


async def _send_wanbang_platform_tracking_failure_email(
    db: Session,
    order: Order,
    state: dict,
) -> None:
    tracking_number = str(state.get("tracking_number") or "").strip()
    if not tracking_number or state.get("failure_email_sent_at"):
        return

    error = str(state.get("error") or "未知错误").strip()
    order_number = str(
        getattr(order, "posting_number", "")
        or getattr(order, "platform_order_no", "")
        or getattr(order, "platform_order_id", "")
        or getattr(order, "id", "")
    ).strip()
    subject = f"[CaifuClaw AI] 万邦运单回填失败：{order.platform} {order_number}"
    body = "\n".join(
        [
            "万邦货运单号回填至原平台失败，请及时处理。",
            "",
            f"平台：{order.platform}",
            f"店铺：{order.account_id}",
            f"订单号：{order_number}",
            f"万邦货运单号：{tracking_number}",
            f"触发来源：{state.get('source') or 'unknown'}",
            f"回填尝试次数：{state.get('attempt_count') or 1}",
            f"失败原因：{error[:1000]}",
            "",
            "系统会在后续店铺同步中自动重试。",
        ]
    )
    try:
        email_setting = get_email_setting(db)
        recipients = notification_recipients_for(email_setting, EMAIL_NOTIFICATION_WANBANG_TRACKING_FAILURE)
        if not recipients:
            raise RuntimeError("未配置万邦接口 / 运单回填异常的邮件收件人")
        await asyncio.to_thread(
            send_email,
            email_setting,
            recipients,
            subject,
            body,
        )
    except Exception as exc:
        message = safe_exception_message(exc)[:1000]
        logger.warning(
            "Wanbang tracking backfill alert email skipped for order %s, tracking %s: %s",
            order_number,
            tracking_number,
            message,
        )
        state["failure_email_error"] = message
        state["failure_email_attempt_count"] = int(state.get("failure_email_attempt_count") or 0) + 1
        return

    state["failure_email_recipient"] = ", ".join(recipients)
    state["failure_email_sent_at"] = datetime.utcnow().isoformat()
    state.pop("failure_email_error", None)
    state["failure_email_attempt_count"] = int(state.get("failure_email_attempt_count") or 0) + 1


async def backfill_wanbang_tracking_to_platform(
    db: Session,
    order: Order,
    *,
    tracking_number: str = "",
    source: str = "",
    job_log_id: int | None = None,
) -> dict:
    """Register a WanbExpress waybill with the order's original marketplace.

    Wanbang routing intentionally bypasses ``create_platform_shipment``.  This
    independent operation runs after Wanbang has returned a waybill and keeps
    its own state so it can be retried without recreating a Wanbang parcel.
    """
    stats = {"attempted": 0, "registered": 0, "existing": 0, "skipped": 0, "unsupported": 0, "failed": 0}
    if not order_uses_wanbang(order):
        return stats

    tracking_number = str(tracking_number or _order_tracking_number_for_refresh(db, order)).strip()
    if not tracking_number:
        stats["skipped"] = 1
        return stats

    previous = _wanbang_platform_tracking_state(order)
    previous_status = str(previous.get("status") or "").strip().lower()
    previous_tracking = str(previous.get("tracking_number") or "").strip()
    if previous_status in WANBANG_PLATFORM_TRACKING_FINAL_STATUSES and previous_tracking == tracking_number:
        stats["skipped"] = 1
        return stats
    if source == "retry" and previous_status not in {"failed", "pending"}:
        stats["skipped"] = 1
        return stats

    attempt_count = int(previous.get("attempt_count") or 0) + 1
    attempted_at = datetime.utcnow()
    request_body = _wanbang_platform_tracking_log_request(order, tracking_number)
    stats["attempted"] = 1
    try:
        local_setting = db.scalar(
            select(SyncSetting).where(
                SyncSetting.platform == order.platform,
                SyncSetting.account_id == order.account_id,
            )
        )
        connector = _connector_for_account(db, order.platform, order.account_id, local_setting)
        if hasattr(connector, "settings") and isinstance(connector.settings, dict):
            connector.settings["dry_run_fulfillment"] = False
        started = perf_counter()
        result = await connector.register_tracking_number(
            _normalized_order_from_row(order),
            tracking_number,
            WANBANG_CARRIER_NAME,
        )
        duration_ms = int((perf_counter() - started) * 1000)
    except Exception as exc:
        error = safe_exception_message(exc)
        failure_state = _wanbang_platform_tracking_failure_state(
            previous,
            tracking_number=tracking_number,
            attempt_count=attempt_count,
            attempted_at=attempted_at,
            source=source,
            error=error,
        )
        _store_wanbang_platform_tracking_state(order, failure_state)
        await _send_wanbang_platform_tracking_failure_email(db, order, failure_state)
        _store_wanbang_platform_tracking_state(order, failure_state)
        log_api_call(
            platform=order.platform,
            account_id=order.account_id,
            operation=WANBANG_PLATFORM_TRACKING_OPERATION,
            method="CONNECTOR",
            url=f"{order.platform}://shipments/register-tracking",
            request_body=request_body,
            error_message=error[:4000],
            extra={"job_log_id": job_log_id, "source": source, "attempt_count": attempt_count},
        )
        add_order_operation_log(
            db,
            order_id=order.id,
            operation_type=WANBANG_PLATFORM_TRACKING_OPERATION,
            operation_attribute="回填平台货运单号",
            description=f"将万邦货运单号 {tracking_number} 回填至 {order.platform} 失败：{error[:300]}",
            operator=SYSTEM_OPERATOR,
            source=ORDER_LOG_SYSTEM_SOURCE,
            operated_at=attempted_at,
            event_key=f"wanbang_platform_tracking_failed:{order.id}:{tracking_number}:{attempt_count}",
            extra={"job_log_id": job_log_id, "source": source, "tracking_number": tracking_number, "error": error[:1000]},
        )
        stats["failed"] = 1
        return stats

    status = str(getattr(result, "status", "") or "").strip().lower()
    platform_shipment_id = str(getattr(result, "platform_shipment_id", "") or "").strip()
    response_body = {"platform_shipment_id": platform_shipment_id, "status": status}
    if status == "unsupported":
        reason = ""
        raw_payload = getattr(result, "raw_payload", None)
        if isinstance(raw_payload, dict):
            reason = str(raw_payload.get("reason") or "").strip()
        _store_wanbang_platform_tracking_state(
            order,
            {
                "status": "unsupported",
                "tracking_number": tracking_number,
                "carrier": WANBANG_CARRIER_NAME,
                "attempt_count": attempt_count,
                "last_attempt_at": attempted_at.isoformat(),
                "source": source,
                "error": reason,
            },
        )
        log_api_call(
            platform=order.platform,
            account_id=order.account_id,
            operation=WANBANG_PLATFORM_TRACKING_OPERATION,
            method="CONNECTOR",
            url=f"{order.platform}://shipments/register-tracking",
            request_body=request_body,
            response_status=200,
            response_body=response_body,
            duration_ms=duration_ms,
            extra={"job_log_id": job_log_id, "source": source, "unsupported": True},
        )
        add_order_operation_log(
            db,
            order_id=order.id,
            operation_type=WANBANG_PLATFORM_TRACKING_OPERATION,
            operation_attribute="回填平台货运单号",
            description=f"{order.platform} 暂不支持回填万邦货运单号 {tracking_number}" + (f"：{reason[:300]}" if reason else ""),
            operator=SYSTEM_OPERATOR,
            source=ORDER_LOG_SYSTEM_SOURCE,
            operated_at=attempted_at,
            event_key=f"wanbang_platform_tracking_unsupported:{order.id}:{tracking_number}",
            extra={"job_log_id": job_log_id, "source": source, "tracking_number": tracking_number, "reason": reason[:1000]},
        )
        stats["unsupported"] = 1
        return stats

    if status not in WANBANG_PLATFORM_TRACKING_FINAL_STATUSES:
        error = f"Unexpected external tracking registration status: {status or 'empty'}"
        failure_state = _wanbang_platform_tracking_failure_state(
            previous,
            tracking_number=tracking_number,
            attempt_count=attempt_count,
            attempted_at=attempted_at,
            source=source,
            error=error,
        )
        _store_wanbang_platform_tracking_state(order, failure_state)
        await _send_wanbang_platform_tracking_failure_email(db, order, failure_state)
        _store_wanbang_platform_tracking_state(order, failure_state)
        log_api_call(
            platform=order.platform,
            account_id=order.account_id,
            operation=WANBANG_PLATFORM_TRACKING_OPERATION,
            method="CONNECTOR",
            url=f"{order.platform}://shipments/register-tracking",
            request_body=request_body,
            response_status=502,
            response_body=response_body,
            error_message=error,
            duration_ms=duration_ms,
            extra={"job_log_id": job_log_id, "source": source, "attempt_count": attempt_count},
        )
        stats["failed"] = 1
        return stats

    _store_wanbang_platform_tracking_state(
        order,
        {
            "status": status,
            "tracking_number": tracking_number,
            "carrier": WANBANG_CARRIER_NAME,
            "platform_shipment_id": platform_shipment_id,
            "attempt_count": attempt_count,
            "last_attempt_at": attempted_at.isoformat(),
            "registered_at": attempted_at.isoformat(),
            "source": source,
        },
    )
    log_api_call(
        platform=order.platform,
        account_id=order.account_id,
        operation=WANBANG_PLATFORM_TRACKING_OPERATION,
        method="CONNECTOR",
        url=f"{order.platform}://shipments/register-tracking",
        request_body=request_body,
        response_status=200,
        response_body=response_body,
        duration_ms=duration_ms,
        extra={"job_log_id": job_log_id, "source": source, "result": status},
    )
    add_order_operation_log(
        db,
        order_id=order.id,
        operation_type=WANBANG_PLATFORM_TRACKING_OPERATION,
        operation_attribute="回填平台货运单号",
        description=f"已将万邦货运单号 {tracking_number} 回填至 {order.platform}" + (f"（平台 shipment: {platform_shipment_id}）" if platform_shipment_id else ""),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=attempted_at,
        event_key=f"wanbang_platform_tracking:{order.id}:{tracking_number}",
        extra={"job_log_id": job_log_id, "source": source, "tracking_number": tracking_number, "platform_shipment_id": platform_shipment_id, "result": status},
    )
    stats[status] = 1
    return stats


async def retry_wanbang_tracking_backfill_for_account(
    db: Session,
    platform: str,
    account_id: str,
    *,
    job_log_id: int | None = None,
    batch_size: int = 100,
) -> dict:
    """Retry only previous transient backfill failures for one marketplace account."""
    stats = {"attempted": 0, "registered": 0, "existing": 0, "skipped": 0, "unsupported": 0, "failed": 0}
    rows = db.scalars(
        select(Order)
        .where(Order.platform == platform, Order.account_id == account_id)
        .order_by(Order.updated_at.desc(), Order.id.desc())
        .limit(max(1, batch_size))
    ).all()
    for order in rows:
        state = _wanbang_platform_tracking_state(order)
        if str(state.get("status") or "").strip().lower() not in {"failed", "pending"}:
            continue
        row_stats = await backfill_wanbang_tracking_to_platform(
            db,
            order,
            tracking_number=str(state.get("tracking_number") or ""),
            source="retry",
            job_log_id=job_log_id,
        )
        for key in stats:
            stats[key] += int(row_stats.get(key, 0) or 0)
    return stats


async def backfill_wanbang_reference_id_for_order(db: Session, order: Order, *, job_log_id: int | None = None) -> dict:
    stats = {"attempted": 0, "updated": 0, "skipped": 0, "conflict": 0, "failed": 0}
    tracking_number = _order_tracking_number_for_refresh(db, order)
    if not _order_needs_wanbang_reference_backfill(order, tracking_number):
        return stats

    stats["attempted"] = 1
    try:
        lookup = await fetch_wanbang_reference_id_by_tracking(db, order, tracking_number)
    except Exception as exc:
        stats["failed"] = 1
        error = safe_exception_message(exc)
        add_order_operation_log(
            db,
            order_id=order.id,
            operation_type="wanbang_reference_backfill",
            operation_attribute="同步物流信息",
            description=f"通过货运单号 {tracking_number} 查询万邦 ReferenceId 失败：{error[:300]}",
            operator=SYSTEM_OPERATOR,
            source=ORDER_LOG_SYSTEM_SOURCE,
            operated_at=datetime.utcnow(),
            event_key=f"wanbang_reference_backfill_failed:{order.id}:{tracking_number}",
            extra={"job_log_id": job_log_id, "tracking_number": tracking_number, "error": error[:1000]},
        )
        return stats

    reference_id = str(getattr(lookup, "reference_id", "") or "").strip()
    _store_wanbang_reference_lookup(order, lookup, tracking_number)
    if not reference_id:
        stats["skipped"] = 1
        return stats

    current = str(getattr(order, "internal_order_no", "") or "").strip()
    if current == reference_id:
        stats["skipped"] = 1
        return stats

    if current and not _looks_like_generated_internal_order_no(current) and not looks_like_wanbang_process_code(current):
        stats["skipped"] = 1
        return stats

    conflict = db.scalar(select(Order).where(Order.internal_order_no == reference_id, Order.id != order.id).limit(1))
    if conflict:
        stats["conflict"] = 1
        order.error_message = f"万邦 ReferenceId 回填跳过：{reference_id} 已被订单 {getattr(conflict, 'id', '')} 使用"
        add_order_operation_log(
            db,
            order_id=order.id,
            operation_type="wanbang_reference_backfill",
            operation_attribute="同步物流信息",
            description=f"通过货运单号 {tracking_number} 获取到万邦 ReferenceId {reference_id}，但该值已被其他订单使用，已跳过",
            operator=SYSTEM_OPERATOR,
            source=ORDER_LOG_SYSTEM_SOURCE,
            operated_at=datetime.utcnow(),
            event_key=f"wanbang_reference_backfill_conflict:{order.id}:{reference_id}",
            extra={
                "job_log_id": job_log_id,
                "tracking_number": tracking_number,
                "reference_id": reference_id,
                "conflict_order_id": getattr(conflict, "id", None),
            },
        )
        return stats

    order.internal_order_no = reference_id
    order.error_message = ""
    order.updated_at = datetime.utcnow()
    add_order_operation_log(
        db,
        order_id=order.id,
        operation_type="wanbang_reference_backfill",
        operation_attribute="同步物流信息",
        description=f"通过货运单号 {tracking_number} 从万邦补齐 ReferenceId：{reference_id}",
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=datetime.utcnow(),
        event_key=f"wanbang_reference_backfill:{order.id}:{reference_id}",
        extra={
            "job_log_id": job_log_id,
            "tracking_number": tracking_number,
            "reference_id": reference_id,
            "track_item_id": getattr(lookup, "track_item_id", "") or "",
            "match": getattr(lookup, "match", "") or "",
        },
    )
    if hasattr(db, "flush"):
        db.flush()
    stats["updated"] = 1
    return stats


def _has_tracking_and_real_label(db: Session, order: Order) -> bool:
    tracking_number = _order_tracking_number_for_refresh(db, order)
    return bool(tracking_number and _latest_real_label_for_order(db, order))


def _should_refresh_order_status(db: Session, order: Order, now: datetime) -> tuple[bool, str]:
    if order.biz_status in TERMINAL_BIZ_STATUSES:
        return False, "terminal"
    if order.biz_status == "已妥投":
        return False, "delivered_confirmed"
    if not _uses_high_frequency_status_refresh(db, order):
        last_synced_at = getattr(order, "logistics_last_synced_at", None)
        if last_synced_at and now - last_synced_at < timedelta(seconds=LOW_FREQUENCY_STATUS_REFRESH_SECONDS):
            return False, "low_frequency_cooldown"
    return True, "eligible"


def _uses_high_frequency_status_refresh(db: Session, order: Order) -> bool:
    return order.biz_status in HIGH_FREQUENCY_BIZ_STATUSES and not _order_tracking_number_for_refresh(db, order)


def _mark_low_frequency_status_refresh_attempted(db: Session, rows: list[Order], now: datetime) -> int:
    marked = 0
    for row in rows:
        if _uses_high_frequency_status_refresh(db, row):
            continue
        row.logistics_last_synced_at = now
        marked += 1
    return marked


def _apply_status_update_to_order(
    db: Session,
    order: Order,
    update: OrderStatusUpdate,
    *,
    connector_settings: dict | None = None,
) -> dict:
    changed = False
    raw_payload = update.raw_payload or {}
    order.last_api_payload = raw_payload
    extracted = _extract_order_fields(raw_payload)
    merged_payload = _merge_payload_preserving_existing(order.raw_payload, raw_payload)
    if merged_payload != order.raw_payload:
        order.raw_payload = merged_payload
        changed = True

    country_code = extracted["country_code"] or order.country_code
    country_name_cn = extracted["country_name_cn"] or order.country_name_cn
    existing_tracking_number = clean_tracking_number(order.shipment_tracking_number, order.raw_payload or {}, order.platform)
    tracking_number = (
        update.shipment_tracking_number
        or extracted["shipment_tracking_number"]
        or _platform_tracking_number_from_posting(
            order.platform,
            update.posting_number or order.posting_number,
            update.platform_status or order.platform_status,
            raw_payload,
        )
        or existing_tracking_number
        or ""
    )
    if order_is_logistics_label_exempt(order):
        tracking_number = ""
    handover_at = order.handover_at or _parse_datetime(update.handover_at) or extracted["handover_at"]

    if country_code and order.country_code != country_code:
        order.country_code = country_code
        changed = True
    if country_name_cn and order.country_name_cn != country_name_cn:
        order.country_name_cn = country_name_cn
        changed = True
    tracking_changed = False
    if tracking_number and order.shipment_tracking_number != tracking_number:
        order.shipment_tracking_number = tracking_number
        tracking_changed = True
        changed = True
    elif not tracking_number and order.shipment_tracking_number and not existing_tracking_number:
        order.shipment_tracking_number = ""
        tracking_changed = True
        changed = True
    if handover_at and order.handover_at != handover_at:
        order.handover_at = handover_at
        changed = True

    new_status = update.platform_status
    if new_status:
        if new_status != order.platform_status:
            order.platform_status = new_status
            changed = True
        download_mode = str((connector_settings or {}).get("fbo_fbp_download_mode") or "none").lower()
        next_biz_status = _platform_snapshot_biz_status(order, download_mode=download_mode)
        if next_biz_status != order.biz_status:
            order.biz_status = next_biz_status
            changed = True
        if _apply_joom_offline_shipping_metadata(order):
            changed = True

    shipment_result = {"created": False, "updated": False, "tracking_updated": False}
    shipment_payload_id = _shipment_payload_id(raw_payload)
    if (
        not order_is_logistics_label_exempt(order)
        and (canonical_oauth_platform(order.platform) != "joom_logistics" or tracking_number)
        and (order.platform != "ozon" or tracking_number or shipment_payload_id)
        and (order.platform != "wildberries" or tracking_number or shipment_payload_id)
    ):
        shipment_result = _upsert_shipment_info(
            db,
            order,
            platform_shipment_id=shipment_payload_id or update.posting_number or order.posting_number,
            tracking_number=tracking_number,
            carrier=extracted["buyer_selected_logistics"] or order.buyer_selected_logistics or order.platform,
            status=new_status or "",
        )
    changed = changed or shipment_result["updated"]
    if changed:
        order.updated_at = datetime.utcnow()
    return {
        "updated": changed,
        "tracking_updated": tracking_changed or shipment_result["tracking_updated"],
        "shipment_created": shipment_result["created"],
        "shipment_updated": shipment_result["updated"],
    }


def _mercado_shipment_seed(row: Order) -> dict | None:
    raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    shipment = raw_payload.get("shipment") if isinstance(raw_payload.get("shipment"), dict) else {}
    shipping = raw_payload.get("shipping") if isinstance(raw_payload.get("shipping"), dict) else {}
    shipment_id = _first_value(shipment.get("id"), shipping.get("id"))
    order_id = row.platform_order_id or raw_payload.get("id")
    if not order_id:
        return None
    seed = {"id": order_id}
    if shipment_id:
        seed["shipment"] = {"id": shipment_id}
    return seed


def _is_mercado_legacy_incomplete(row: Order) -> bool:
    if row.platform != "mercadolibre":
        return False
    raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    shipment = raw_payload.get("shipment") if isinstance(raw_payload.get("shipment"), dict) else {}
    shipping = raw_payload.get("shipping") if isinstance(raw_payload.get("shipping"), dict) else {}
    shipment_id = _first_value(shipment.get("id"), shipping.get("id"))
    legacy_posting = row.posting_number in ("", None, row.platform_order_id, row.platform_order_no)
    missing_core_fields = not row.platform_status or not row.order_amount or not row.currency or not row.platform_created_at
    return bool(shipment_id and (legacy_posting or missing_core_fields))


def _connector_for_account(db: Session, platform: str, account_id: str, local_setting: SyncSetting | None = None):
    account = db.scalar(
        select(PlatformAccount).where(
            PlatformAccount.platform == platform,
            PlatformAccount.account_id == account_id,
        )
    )
    if not account:
        raise ValueError(f"Shop not found: {platform}/{account_id}")
    if not account.encrypted_credentials:
        raise ValueError(f"No credentials found for shop: {platform}/{account_id}")

    credentials = get_credential_manager().decrypt_credentials(account.encrypted_credentials)
    settings = dict(account.settings or {})
    endpoint_key = {
        "joomlogistics": "joom_logistics",
        "wildberrie": "wildberries",
        "shopify_admin": "shopify",
        "ebay_sell": "ebay",
        "walmart_marketplace": "walmart",
        "shein_open": "shein",
        "coupang_openapi": "coupang",
        "wayfair_partner": "wayfair",
        "dms_matrix": "dmsmatrix",
        "dms-matrix": "dmsmatrix",
        "dms_matrix_erp": "dmsmatrix",
        "dmsmatrix_erp": "dmsmatrix",
    }.get(platform, platform)
    _ensure_base_url(settings, endpoint_key)
    # Provide account_id to connectors for API request logging context.
    settings["account_id"] = account_id
    settings["display_name"] = account.display_name or account_id
    if local_setting:
        settings["dry_run_fulfillment"] = local_setting.dry_run_fulfillment

    oauth_platform = canonical_oauth_platform(platform)
    if oauth_platform in {"joom_logistics", "mercadolibre", "allegro"}:
        credentials = ensure_access_token(db, account, credentials, settings)
        if not credentials.get("access_token"):
            raise ValueError(f"{oauth_platform} OAuth token not found, please complete authorization first")

    runtime_settings = get_settings()
    return ConnectorRuntimeClient(
        runtime_url=runtime_settings.connector_runtime_url,
        platform=platform,
        credentials=credentials,
        settings=settings,
        account_id=account_id,
        internal_service_token=runtime_settings.internal_service_token,
    )


def _connector_for(config: dict, local_setting: SyncSetting | None = None):
    platform = config["platform"].lower()
    settings = dict(config.get("settings") or {})
    endpoint_key = {
        "joomlogistics": "joom_logistics",
        "wildberrie": "wildberries",
        "shopify_admin": "shopify",
        "ebay_sell": "ebay",
        "walmart_marketplace": "walmart",
        "shein_open": "shein",
        "coupang_openapi": "coupang",
        "wayfair_partner": "wayfair",
        "dms_matrix": "dmsmatrix",
        "dms-matrix": "dmsmatrix",
        "dms_matrix_erp": "dmsmatrix",
        "dmsmatrix_erp": "dmsmatrix",
    }.get(platform, platform)
    _ensure_base_url(settings, endpoint_key)
    if local_setting:
        settings["dry_run_fulfillment"] = local_setting.dry_run_fulfillment
    runtime_settings = get_settings()
    return ConnectorRuntimeClient(
        runtime_url=runtime_settings.connector_runtime_url,
        platform=platform,
        credentials=config["credentials"],
        settings=settings,
        account_id=str(config.get("account_id") or settings.get("account_id") or ""),
        internal_service_token=runtime_settings.internal_service_token,
    )


def upsert_local_account(db: Session, config: dict) -> PlatformAccount:
    row = db.scalar(
        select(PlatformAccount).where(
            PlatformAccount.platform == config["platform"],
            PlatformAccount.account_id == config["account_id"],
        )
    )
    if not row:
        row = PlatformAccount(platform=config["platform"], account_id=config["account_id"])
        db.add(row)
    row.display_name = config.get("display_name") or ""
    row.enabled = bool(config.get("enabled", True))
    row.auth_type = config.get("auth_type") or "api_key"
    row.credential_type = config.get("auth_type") or "api_key"
    row.settings = config.get("settings") or {}
    if config.get("credentials") and not row.encrypted_credentials:
        row.encrypted_credentials = get_credential_manager().encrypt_credentials(config["credentials"])
        row.credentials_version = row.credentials_version or "imported"

    setting = db.scalar(
        select(SyncSetting).where(
            SyncSetting.platform == config["platform"],
            SyncSetting.account_id == config["account_id"],
        )
    )
    if not setting:
        setting = SyncSetting(
            platform=config["platform"],
            account_id=config["account_id"],
            enabled=bool(config.get("enabled", True)),
            interval_seconds=int((config.get("settings") or {}).get("sync_interval_seconds", 1200)),
            dry_run_fulfillment=bool((config.get("settings") or {}).get("dry_run_fulfillment", False)),
        )
        db.add(setting)
    db.commit()
    return row


async def refresh_configs(db: Session) -> list[dict]:
    accounts = db.scalars(select(PlatformAccount)).all()
    configs = []
    for account in accounts:
        configs.append(
            {
                "platform": account.platform,
                "account_id": account.account_id,
                "display_name": account.display_name,
                "enabled": account.enabled,
                "auth_type": account.credential_type,
                "settings": account.settings or {},
            }
        )
    return configs


_BIZ_STATUS_ORDER = {
    "待处理": 0,
    "待打印": 1,
    "待采购": 2,
    "配货中": 3,
    "已发货": 4,
    "已妥投": 5,
    "已完成": 6,
    "已作废": 6,
}

TERMINAL_BIZ_STATUSES = {"已完成", "已作废"}
STATUS_REFRESH_BIZ_STATUSES = {"待处理", "待打印", "待采购", "配货中", "已发货"}
LOW_FREQUENCY_STATUS_REFRESH_SECONDS = 6 * 60 * 60
HIGH_FREQUENCY_BIZ_STATUSES = {"待处理"}
VOIDED_PLATFORM_STATUSES = {
    "cancel",
    "canceled",
    "cancelled",
    "cancelled_by_seller",
    "paidbyjoomrefund",
    "refunded",
}
DELIVERED_PLATFORM_STATUSES = {
    "complete",
    "completed",
    "delivered",
    "received",
    "shipped",
    "sold",
}
# Joom returns fulfilledOnline once its online fulfillment label/tracking is
# ready. That must not override the local print/purchase workflow as "已发货".
SHIPPED_PLATFORM_STATUSES = set()

_DOWNSTREAM_LOCAL_STATUSES = {
    "picking",
    "shipment_creating",
    "label_downloading",
    "label_saved",
    "shipment_created",
    "shipped",
}

# Global safety switch for platform shipment creation.
# False enables real shipment submission for all platforms.
PLATFORM_SHIPMENT_CREATION_DISABLED = False


def _advance_biz_status(current: str | None, candidate: str | None) -> str:
    if not candidate:
        return current or "待处理"
    if not current:
        return candidate
    if current == "配货中" and candidate == "已发货":
        return current
    current_rank = _BIZ_STATUS_ORDER.get(current)
    candidate_rank = _BIZ_STATUS_ORDER.get(candidate)
    if current_rank is None or candidate_rank is None:
        return candidate
    if candidate_rank < current_rank:
        return current
    return candidate


def _record_fulfillment_failure(
    order: Order,
    exc: Exception,
    *,
    previous_biz_status: str | None,
    previous_local_status: str | None,
) -> None:
    if previous_local_status in _DOWNSTREAM_LOCAL_STATUSES:
        order.local_status = previous_local_status
    else:
        order.local_status = "failed_retryable"
    order.biz_status = _advance_biz_status(previous_biz_status or order.biz_status, "待处理")
    order.error_message = str(exc)


def _compute_biz_status(
    platform_status: str,
    fulfillment_type: str,
    download_mode: str,
    current: str | None,
    platform: str = "",
) -> str:
    """根据平台状态 + 履约类型 + 店铺 FBO/FBP 下载配置，计算业务状态。
    规则（二次命中时只向前推进，不从配货中/已发货等状态回退到待处理）：
    1. cancel / cancelled / refunded    -> 已作废
    2. complete / delivered / shipped    -> 已妥投（Wildberries complete 除外）
    3. Allegro SENT -> 已发货，PICKED_UP -> 已妥投
    4. FBO/FBP 且 download_mode=to_completed -> 已完成
    5. FBO/FBP 且 download_mode=to_unshipped:
         - delivering 类状态 -> 已发货
         - 其他              -> 待处理
    6. FBS delivering 类状态 -> 已发货
    7. 其余（FBS awaiting_* / Joom fulfilledOnline）：如 current 已处于下游状态（配货中/已发货/已妥投/已完成/已作废）则保留，否则待处理
    """
    ps = (platform_status or "").lower()
    platform_key = canonical_oauth_platform(platform)
    if ps in VOIDED_PLATFORM_STATUSES:
        return _advance_biz_status(current, "已作废")
    if platform_key == "wildberries" and ps == "complete":
        return _advance_biz_status(current, "待处理")
    if platform_key == "allegro":
        if ps == "sent":
            if current in TERMINAL_BIZ_STATUSES:
                return current
            return "已发货"
        if ps == "picked_up":
            return _advance_biz_status(current, "已妥投")
    if ps in SHIPPED_PLATFORM_STATUSES:
        return _advance_biz_status(current, "已发货")
    if ps in DELIVERED_PLATFORM_STATUSES:
        return _advance_biz_status(current, "已妥投")
    if fulfillment_type in ("FBO", "FBP"):
        if download_mode == "to_completed":
            return _advance_biz_status(current, "已完成")
        if download_mode == "to_unshipped":
            if ps in ("delivering", "driver_pickup", "sent_by_seller"):
                return _advance_biz_status(current, "已发货")
            return _advance_biz_status(current, "待处理")
        return _advance_biz_status(current, "待处理")
    # FBS
    if ps in ("delivering", "driver_pickup", "sent_by_seller"):
        return _advance_biz_status(current, "已发货")
    return _advance_biz_status(current, "待处理")


def _platform_snapshot_biz_status(order: Order, *, download_mode: str = "none") -> str:
    if order_is_joom_bsi_draft(order):
        if (order.platform_status or "").lower() in VOIDED_PLATFORM_STATUSES:
            return _compute_biz_status(
                order.platform_status,
                order.fulfillment_type or "PHYSICAL",
                download_mode,
                order.biz_status,
                order.platform,
            )
        # Orders with a BSI draft move locally only after their canonical
        # follow-up rows are confirmed. A later Joom snapshot must not regress
        # that local completion back to pending.
        return order.biz_status or "待处理"
    if order_is_joom_fbj_warehouse(order):
        if (order.platform_status or "").lower() in VOIDED_PLATFORM_STATUSES:
            return _compute_biz_status(
                order.platform_status,
                order.fulfillment_type or "FBJ",
                download_mode,
                order.biz_status,
                order.platform,
            )
        if order.biz_status in {"已发货", "已妥投", "已完成"}:
            return order.biz_status
        # FBJ orders are shown as pending until their follow-up export succeeds.
        # The scheduled task still keeps them out of label printing and purchase.
        return "待处理"
    offline_target = joom_offline_shipping_target_status(order)
    if offline_target:
        current = order.biz_status or ""
        current_rank = _BIZ_STATUS_ORDER.get(current)
        target_rank = _BIZ_STATUS_ORDER.get(offline_target)
        if current_rank is not None and target_rank is not None and current_rank > target_rank:
            return current
        return offline_target
    if order_is_joom_offline_shipping(order):
        return order.biz_status or "待处理"
    fulfillment_type = order.fulfillment_type or infer_fulfillment_type(order.platform, order.raw_payload or {})
    return _compute_biz_status(
        order.platform_status,
        fulfillment_type,
        download_mode,
        order.biz_status,
        order.platform,
    )


def _apply_joom_offline_shipping_metadata(order: Order) -> bool:
    if joom_offline_shipping_target_status(order) != "已发货":
        return False
    changed = False
    if order.local_status != "shipped":
        order.local_status = "shipped"
        changed = True
    extracted = _extract_order_fields(order.raw_payload or {})
    platform_shipped_at = extracted.get("handover_at")
    if order.shipped_at is None and platform_shipped_at is not None:
        order.shipped_at = platform_shipped_at
        changed = True
    if order.error_message:
        order.error_message = ""
        changed = True
    return changed


def _refresh_biz_status_from_platform_snapshot(order: Order, *, connector_settings: dict | None = None) -> bool:
    """Recompute biz_status from the platform_status already stored on the order."""
    platform_status = getattr(order, "platform_status", None)
    if not platform_status:
        return False
    download_mode = str((connector_settings or {}).get("fbo_fbp_download_mode") or "none").lower()
    next_biz_status = _platform_snapshot_biz_status(order, download_mode=download_mode)
    changed = next_biz_status != order.biz_status
    if changed:
        order.biz_status = next_biz_status
    if _apply_joom_offline_shipping_metadata(order):
        changed = True
    if changed:
        order.updated_at = datetime.utcnow()
    return changed


def _find_existing_order(db: Session, platform: str, shop_id: str, normalized: NormalizedOrder) -> Order | None:
    row = db.scalar(
        select(Order).where(
            Order.shop_id == shop_id,
            Order.platform_order_id == normalized.platform_order_id,
            Order.posting_number == (normalized.posting_number or ""),
        )
    )
    if not row and platform == "mercadolibre":
        legacy_posting_numbers = {
            "",
            normalized.platform_order_id,
            normalized.platform_order_no,
        }
        legacy_posting_numbers.discard(None)
        legacy_posting_numbers.discard(normalized.posting_number or "")
        if legacy_posting_numbers:
            row = db.scalar(
                select(Order)
                .where(
                    Order.shop_id == shop_id,
                    Order.platform_order_id == normalized.platform_order_id,
                    Order.posting_number.in_(legacy_posting_numbers),
                )
                .limit(1)
            )
    if not row and platform == "joom_logistics":
        # Joom's order endpoint does not provide a stable posting number for
        # every response. Match by order id so a historical backfill cannot
        # create a second row when the posting number changes from blank.
        row = db.scalar(
            select(Order)
            .where(
                Order.shop_id == shop_id,
                Order.platform == platform,
                Order.platform_order_id == normalized.platform_order_id,
            )
            .order_by(Order.id)
            .limit(1)
        )
    if not row and platform == "allegro":
        identity_values = {
            value
            for value in (
                normalized.platform_order_id,
                normalized.platform_order_no,
                normalized.posting_number,
            )
            if value
        }
        if identity_values:
            row = db.scalar(
                select(Order)
                .where(
                    Order.shop_id == shop_id,
                    Order.platform == platform,
                    or_(
                        Order.platform_order_id.in_(identity_values),
                        Order.platform_order_no.in_(identity_values),
                        Order.posting_number.in_(identity_values),
                    ),
                )
                .limit(1)
            )
    return row


def upsert_order(db: Session, config: dict, normalized: NormalizedOrder) -> Order:
    settings = get_settings()
    platform = config["platform"]
    preserve_complete_payload = platform == "mercadolibre"
    shop_id = str(config["account_id"])
    row = _find_existing_order(db, platform, shop_id, normalized)
    existing_payload = row.raw_payload if row and isinstance(row.raw_payload, dict) else {}
    if not row:
        row = Order(
            tenant_id=settings.default_tenant_id,
            internal_order_no=generate_internal_order_no(),
            platform=platform,
            account_id=config["account_id"],
            shop_id=shop_id,
            shop_name=config.get("display_name") or shop_id,
            platform_order_id=normalized.platform_order_id,
            platform_order_no=normalized.platform_order_no or None,
            posting_number=normalized.posting_number or "",
            local_status="new",
            biz_status="待处理",
        )
        db.add(row)

    row.platform = platform
    row.account_id = config["account_id"]
    row.shop_id = shop_id
    row.shop_name = config.get("display_name") or shop_id
    row.platform_order_no = normalized.platform_order_no or row.platform_order_no
    row.posting_number = normalized.posting_number or row.posting_number
    if preserve_complete_payload and normalized.platform_status in (None, "", "None"):
        pass
    else:
        row.platform_status = _to_str(normalized.platform_status)
    incoming_payload = normalized.raw_payload or {}
    row.raw_payload = (
        _merge_payload_preserving_existing(row.raw_payload or {}, incoming_payload)
        if preserve_complete_payload
        else incoming_payload
    )
    if not preserve_complete_payload and isinstance(row.raw_payload, dict):
        for key in ("wanbang", "wanbang_trackpoints", "wanbang_platform_tracking"):
            if key in existing_payload and key not in row.raw_payload:
                row.raw_payload[key] = existing_payload[key]
    fulfillment_type = infer_fulfillment_type(
        platform,
        row.raw_payload or {},
        getattr(normalized, "fulfillment_type", "FBS") or "FBS",
    )
    row.fulfillment_type = fulfillment_type
    row.is_overseas_warehouse = bool(getattr(normalized, "is_overseas_warehouse", False)) or infer_is_overseas_warehouse(
        platform,
        fulfillment_type,
        row.raw_payload or {},
    )
    extracted = _extract_order_fields(row.raw_payload or {})
    row.site = row.site or extracted["site"]
    row.buyer_id = extracted["buyer_id"] or row.buyer_id
    row.buyer_name = extracted["buyer_name"] or row.buyer_name
    row.platform_created_at = extracted["platform_created_at"] or row.platform_created_at
    row.platform_handover_deadline = extracted["platform_handover_deadline"] or row.platform_handover_deadline
    row.country_code = extracted["country_code"] or row.country_code
    row.country_name_cn = extracted["country_name_cn"] or row.country_name_cn
    row.buyer_selected_logistics = extracted["buyer_selected_logistics"] or row.buyer_selected_logistics
    row.order_amount = extracted["order_amount"] or row.order_amount
    row.currency = extracted["currency"] or row.currency
    if order_is_logistics_label_exempt(row):
        row.shipment_tracking_number = ""
    else:
        row.shipment_tracking_number = (
            extracted["shipment_tracking_number"]
            or _platform_tracking_number_from_posting(platform, row.posting_number, row.platform_status, row.raw_payload or {})
            or clean_tracking_number(row.shipment_tracking_number, row.raw_payload or {}, platform)
        )
    row.payment_at = extracted["payment_at"] or row.payment_at
    row.shipping_deadline_at = extracted["shipping_deadline_at"] or row.shipping_deadline_at
    deadline_settings = config.get("_shipping_deadline_settings")
    if deadline_settings is None:
        deadline_settings = load_shipping_deadline_settings(db)
        config["_shipping_deadline_settings"] = deadline_settings
    update_order_dispatch_deadline(row, deadline_settings)
    row.handover_at = row.handover_at or extracted["handover_at"]
    # 二次命中时按规则覆盖 biz_status
    download_mode = str((config.get("settings") or {}).get("fbo_fbp_download_mode") or "none").lower()
    row.biz_status = _platform_snapshot_biz_status(row, download_mode=download_mode)
    _apply_joom_offline_shipping_metadata(row)
    logistics_rules = config.get("_logistics_match_rules")
    if logistics_rules is None:
        logistics_rules = load_enabled_logistics_rules(db)
        config["_logistics_match_rules"] = logistics_rules
    apply_logistics_rules(row, logistics_rules)
    if not preserve_complete_payload:
        _replace_order_items(db, row)
    elif _has_real_order_items(incoming_payload, platform):
        _replace_order_items(db, row)
    elif not row.id or not db.scalars(select(OrderItem.id).where(OrderItem.order_id == row.id).limit(1)).first():
        _replace_order_items(db, row)
    return row


async def _repair_mercado_legacy_orders(
    db: Session,
    connector,
    config: dict,
    *,
    full_refresh: bool,
) -> int:
    if config["platform"] != "mercadolibre" or not hasattr(connector, "hydrate_order_seeds"):
        return 0
    settings = config.get("settings") or {}
    if not bool(settings.get("auto_repair_legacy_orders", True)):
        return 0

    default_limit = 500 if full_refresh else 50
    limit = int(settings.get("legacy_repair_batch_size", default_limit) or default_limit)
    if limit <= 0:
        return 0

    candidate_rows = db.scalars(
        select(Order)
        .where(
            Order.platform == "mercadolibre",
            Order.account_id == config["account_id"],
        )
        .order_by(Order.updated_at, Order.id)
        .limit(max(limit * 3, limit))
    ).all()
    rows = [row for row in candidate_rows if _is_mercado_legacy_incomplete(row)][:limit]
    if not rows:
        return 0

    seeds = []
    for row in rows:
        seed = _mercado_shipment_seed(row)
        if seed:
            seeds.append(seed)
    if not seeds:
        return 0

    repaired = 0
    normalized_orders = await connector.hydrate_order_seeds(seeds)
    for normalized in normalized_orders:
        incoming = normalized.raw_payload or {}
        shipping = incoming.get("shipping") if isinstance(incoming.get("shipping"), dict) else {}
        has_tracking = bool(_first_value(shipping.get("tracking_number"), shipping.get("trackingNumber")))
        has_core_fields = bool(normalized.platform_status and incoming.get("order_amount") and incoming.get("currency_code"))
        if normalized.posting_number == normalized.platform_order_id and not has_tracking and not has_core_fields:
            continue
        upsert_order(db, config, normalized)
        repaired += 1
    if repaired:
        db.commit()
    return repaired


async def sync_account(
    db: Session,
    config: dict,
    *,
    full_refresh: bool = False,
    job_type: str = JOB_TYPE_SYNC_ORDERS,
    since_override: datetime | None = None,
) -> dict:
    platform = config["platform"]
    account_id = config["account_id"]
    lock = _account_sync_lock(platform, account_id)
    if lock.locked():
        mark_sync_skipped_locked(db, platform, account_id, job_type=job_type)
        db.commit()
        return {"status": "skipped", "reason": "sync already running", "platform": platform, "account_id": account_id}
    async with lock:
        with sync_job_lock(db, platform, account_id, job_type) as lock_acquired:
            if not lock_acquired:
                mark_sync_skipped_locked(db, platform, account_id, job_type=job_type)
                db.commit()
                return {
                    "status": "skipped",
                    "reason": "sync already running in another process",
                    "platform": platform,
                    "account_id": account_id,
                }
            return await _sync_account_locked(db, config, full_refresh=full_refresh, job_type=job_type, since_override=since_override)


async def _sync_account_locked(
    db: Session,
    config: dict,
    *,
    full_refresh: bool = False,
    job_type: str = JOB_TYPE_SYNC_ORDERS,
    since_override: datetime | None = None,
) -> dict:
    platform = config["platform"]
    account_id = config["account_id"]
    local_setting = db.scalar(select(SyncSetting).where(SyncSetting.platform == platform, SyncSetting.account_id == account_id))
    mark_sync_started(db, platform, account_id, job_type=job_type)
    log = SyncJobLog(platform=platform, account_id=account_id, job_type=job_type, status="running")
    db.add(log)
    db.commit()

    try:
        connector = _connector_for_account(db, platform, account_id, local_setting)
        legacy_repaired = await _repair_mercado_legacy_orders(
            db,
            connector,
            config,
            full_refresh=full_refresh,
        )
        
        # 增量同步：获取上次同步时间。Mercado CBT 搜索存在短暂延迟可见，正常增量同步保留回看窗口避免漏单。
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == platform,
                PlatformAccount.account_id == account_id,
            )
        )
        last_sync_time = _effective_order_sync_since(
            platform,
            account.last_sync_at if account else None,
            account.settings if account else config.get("settings"),
            full_refresh=full_refresh,
            since_override=since_override,
        )
        
        # 根据是否有上次同步时间，决定是增量还是全量同步
        fetch_started = perf_counter()
        try:
            if hasattr(connector, "settings") and isinstance(connector.settings, dict):
                connector.settings["full_refresh"] = full_refresh
                if job_type == JOB_TYPE_CATCHUP_ORDERS and platform == "joom_logistics":
                    connector.settings["joom_use_orders_multi_incremental"] = True
                    connector.settings.pop("order_status", None)
            normalized_orders = await connector.fetch_unprocessed_orders(since=last_sync_time)
            log_api_call(
                platform=platform,
                account_id=account_id,
                operation=job_type,
                method="CONNECTOR",
                url=f"{platform}://fetch_unprocessed_orders",
                request_body={"since": last_sync_time.isoformat() if last_sync_time else None, "full_refresh": full_refresh, "job_type": job_type},
                response_status=200,
                response_body={"orders": len(normalized_orders)},
                duration_ms=int((perf_counter() - fetch_started) * 1000),
                extra={"job_log_id": log.id, "job_type": job_type},
            )
        except Exception as fetch_exc:
            log_api_call(
                platform=platform,
                account_id=account_id,
                operation=job_type,
                method="CONNECTOR",
                url=f"{platform}://fetch_unprocessed_orders",
                request_body={"since": last_sync_time.isoformat() if last_sync_time else None, "full_refresh": full_refresh, "job_type": job_type},
                error_message=str(fetch_exc)[:4000],
                duration_ms=int((perf_counter() - fetch_started) * 1000),
                extra={"job_log_id": log.id, "job_type": job_type},
            )
            raise
        
        saved_orders = 0
        new_orders = 0
        updated_orders = 0
        skipped_completed_label_orders = 0
        labels_saved = 0
        wanbang_reference_attempted = 0
        wanbang_reference_updated = 0
        wanbang_reference_conflicts = 0
        wanbang_reference_failed = 0
        wanbang_platform_tracking_retry = {"attempted": 0, "registered": 0, "existing": 0, "skipped": 0, "unsupported": 0, "failed": 0}
        
        for normalized in normalized_orders:
            existing_order = _find_existing_order(db, platform, str(account_id), normalized)
            if existing_order and _has_tracking_and_real_label(db, existing_order):
                ref_stats = await backfill_wanbang_reference_id_for_order(db, existing_order, job_log_id=log.id)
                wanbang_reference_attempted += int(ref_stats.get("attempted", 0) or 0)
                wanbang_reference_updated += int(ref_stats.get("updated", 0) or 0)
                wanbang_reference_conflicts += int(ref_stats.get("conflict", 0) or 0)
                wanbang_reference_failed += int(ref_stats.get("failed", 0) or 0)
                if any(ref_stats.get(key, 0) for key in ("updated", "conflict", "failed")):
                    db.commit()
                skipped_completed_label_orders += 1
                continue
            before_snapshot = _order_log_snapshot(existing_order) if existing_order else {}
            
            order = upsert_order(db, config, normalized)
            db.flush()
            ref_stats = await backfill_wanbang_reference_id_for_order(db, order, job_log_id=log.id)
            wanbang_reference_attempted += int(ref_stats.get("attempted", 0) or 0)
            wanbang_reference_updated += int(ref_stats.get("updated", 0) or 0)
            wanbang_reference_conflicts += int(ref_stats.get("conflict", 0) or 0)
            wanbang_reference_failed += int(ref_stats.get("failed", 0) or 0)
            saved_orders += 1

            sync_changes: list[dict[str, str]] = []
            if existing_order:
                updated_orders += 1
                sync_changes = _order_sync_log_changes(order, before_snapshot)
                sync_description = _order_sync_log_description(order, before_snapshot, created=False)
                sync_event_key = f"sync_order:{order.id}:updated:{log.id}"
            else:
                new_orders += 1
                sync_description = _order_sync_log_description(order, before_snapshot, created=True)
                sync_event_key = f"sync_order:{order.id}:created:{log.id}"
            if not existing_order or sync_changes:
                add_order_operation_log(
                    db,
                    order_id=order.id,
                    operation_type="order_sync",
                    operation_attribute="订单同步",
                    description=sync_description,
                    operator=SYSTEM_OPERATOR,
                    source=ORDER_LOG_SYSTEM_SOURCE,
                    operated_at=datetime.utcnow(),
                    event_key=sync_event_key,
                    extra={
                        "job_log_id": log.id,
                        "platform": platform,
                        "account_id": account_id,
                        "result": "created" if not existing_order else "changed",
                        "changes": sync_changes,
                    },
                )
            db.commit()

        retry_batch_size = (config.get("settings") or {}).get("wanbang_platform_tracking_retry_batch_size", 100)
        try:
            retry_batch_size = max(1, int(retry_batch_size))
        except (TypeError, ValueError):
            retry_batch_size = 100
        wanbang_platform_tracking_retry = await retry_wanbang_tracking_backfill_for_account(
            db,
            platform,
            account_id,
            job_log_id=log.id,
            batch_size=retry_batch_size,
        )

        # 定时面单补拉：为已入库、状态为“配货中/已发货”且本地没有有效 PDF 的订单
        # 逐单调平台 fetch_label（强制真实 API），以 posting_number 为文件名存盘
        if bool((config.get("settings") or {}).get("auto_cache_labels", False)):
            try:
                labels_auto = await _auto_cache_labels(db, connector, platform, account_id)
            except Exception as label_exc:
                labels_auto = 0
                log.message = (log.message or "") + f" | label_cache_error={label_exc}"
            labels_saved += labels_auto

        if local_setting:
            local_setting.last_run_at = datetime.utcnow()

        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == platform,
                PlatformAccount.account_id == account_id,
            )
        )
        if account:
            account.last_sync_at = datetime.utcnow()
            account.last_sync_status = "success"

        log.status = "success"
        log.message = (
            f"orders={saved_orders}, new={new_orders}, updated={updated_orders}, labels={labels_saved}, "
            f"skipped_completed_labels={skipped_completed_label_orders}, "
            f"wanbang_reference_attempted={wanbang_reference_attempted}, "
            f"wanbang_reference_updated={wanbang_reference_updated}, "
            f"wanbang_reference_conflicts={wanbang_reference_conflicts}, "
            f"wanbang_reference_failed={wanbang_reference_failed}, "
            f"wanbang_platform_tracking_attempted={wanbang_platform_tracking_retry['attempted']}, "
            f"wanbang_platform_tracking_registered={wanbang_platform_tracking_retry['registered']}, "
            f"wanbang_platform_tracking_existing={wanbang_platform_tracking_retry['existing']}, "
            f"wanbang_platform_tracking_failed={wanbang_platform_tracking_retry['failed']}, "
            f"legacy_repaired={legacy_repaired}"
        )
        log.ended_at = datetime.utcnow()
        mark_sync_success(db, platform, account_id, job_type=job_type, message=log.message)
        if job_type == JOB_TYPE_CATCHUP_ORDERS:
            audit_sync_event(
                db,
                "catchup_completed",
                platform=platform,
                account_id=account_id,
                job_type=job_type,
                status="success",
                message=log.message,
                extra={"job_log_id": log.id, "orders": saved_orders, "new": new_orders, "updated": updated_orders},
            )
        db.commit()
        return {
            "status": "success",
            "orders": saved_orders,
            "new": new_orders,
            "updated": updated_orders,
            "skipped_completed_labels": skipped_completed_label_orders,
            "labels": labels_saved,
            "legacy_repaired": legacy_repaired,
            "wanbang_reference_attempted": wanbang_reference_attempted,
            "wanbang_reference_updated": wanbang_reference_updated,
            "wanbang_reference_conflicts": wanbang_reference_conflicts,
            "wanbang_reference_failed": wanbang_reference_failed,
            "wanbang_platform_tracking_retry": wanbang_platform_tracking_retry,
        }
    except Exception as exc:
        log.status = "failed"
        log.message = str(exc)
        log.ended_at = datetime.utcnow()
        mark_sync_failed(db, platform, account_id, job_type=job_type, message=str(exc))
        audit_sync_event(
            db,
            "sync_job_failed",
            platform=platform,
            account_id=account_id,
            job_type=job_type,
            status="failed",
            message=str(exc),
            extra={"job_log_id": log.id},
        )
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == platform,
                PlatformAccount.account_id == account_id,
            )
        )
        if account:
            account.last_sync_status = f"failed: {exc}"
        db.commit()
        raise


def _is_delivered_mercadolibre_with_tracking(row: Order, shipment: Shipment | None = None) -> bool:
    if str(getattr(row, "platform", "") or "").lower() != "mercadolibre":
        return False
    if str(getattr(row, "platform_status", "") or "").lower() != "delivered":
        return False
    payload = getattr(row, "raw_payload", None) or {}
    tracking_values = [getattr(row, "shipment_tracking_number", "")]
    if shipment is not None:
        tracking_values.append(getattr(shipment, "tracking_number", ""))
    return any(clean_tracking_number(value, payload, getattr(row, "platform", None)) for value in tracking_values)


async def _auto_cache_labels(db: Session, connector, platform: str, account_id: str) -> int:
    """为已进入物流流程且本地无有效面单的订单，逐单从平台拉取并存盘。返回拉取笔数。"""
    target_rows = db.scalars(
        select(Order).where(
            Order.platform == platform,
            Order.account_id == account_id,
            (
                Order.biz_status.in_(["待打印", "配货中", "已发货"])
                | Order.local_status.in_(["shipment_created", "label_downloading", "label_saved"])
            ),
            Order.is_overseas_warehouse == False,
        )
    ).all()
    target_rows = [
        row
        for row in target_rows
        if not order_is_logistics_label_exempt(row)
        and not order_is_joom_offline_shipping(row)
    ]
    if not target_rows:
        return 0

    need_rows: list[Order] = []
    for r in target_rows:
        shipment = db.scalar(
            select(Shipment).where(Shipment.order_id == r.id).order_by(Shipment.id.desc())
        )
        if _is_delivered_mercadolibre_with_tracking(r, shipment):
            # MercadoLibre rejects label downloads once the shipment is delivered.
            # The scheduled pipeline handles these orders as shipped, so avoid retrying
            # the same permanently unavailable label on every regular order sync.
            continue
        label = None
        if shipment:
            label = db.scalar(
                select(LabelFile).where(LabelFile.shipment_id == shipment.id).order_by(LabelFile.id.desc())
            )
        if label and label.file_path:
            p = Path(label.file_path)
            try:
                if p.exists() and p.stat().st_size > 0 and is_real_label_pdf(p.read_bytes()):
                    r.error_message = ""
                    if shipment and not shipment.tracking_number and r.shipment_tracking_number:
                        shipment.tracking_number = r.shipment_tracking_number
                    continue  # 本地已缓存真实面单
            except Exception:
                pass
        need_rows.append(r)

    if not need_rows:
        return 0

    # 强制真实平台接口
    if hasattr(connector, "settings") and isinstance(connector.settings, dict):
        connector.settings["dry_run_fulfillment"] = False

    saved = 0
    for r in need_rows:
        try:
            if order_uses_wanbang(r):
                label_result, shipment_result = await fetch_wanbang_label_for_order(db, r)
                content = label_result.content
                if not is_real_label_pdf(content):
                    continue
                posting_number = shipment_result.platform_shipment_id or r.posting_number or r.platform_order_id
                file_path, sha256 = save_label_pdf(
                    r.tenant_id, platform, account_id, posting_number, content
                )
                shipment = db.scalar(
                    select(Shipment).where(Shipment.order_id == r.id).order_by(Shipment.id.desc())
                )
                if shipment is None:
                    shipment = Shipment(
                        order_id=r.id,
                        platform_shipment_id=shipment_result.platform_shipment_id or posting_number,
                        tracking_number=shipment_result.tracking_number or r.shipment_tracking_number or "",
                        carrier=shipment_result.carrier or WANBANG_CARRIER_NAME,
                        status="label_ready",
                    )
                    db.add(shipment)
                    db.flush()
                else:
                    if shipment_result.platform_shipment_id:
                        shipment.platform_shipment_id = shipment_result.platform_shipment_id
                    if shipment_result.tracking_number:
                        shipment.tracking_number = shipment_result.tracking_number
                    if shipment_result.carrier:
                        shipment.carrier = shipment_result.carrier
                    shipment.status = "label_ready"
                apply_label_result_tracking(r, shipment, label_result)
                if shipment_result.tracking_number:
                    r.shipment_tracking_number = shipment_result.tracking_number
                    shipment.tracking_number = shipment_result.tracking_number
                    await backfill_wanbang_tracking_to_platform(
                        db,
                        r,
                        tracking_number=shipment_result.tracking_number,
                        source="label_fetch",
                    )
                db.add(
                    LabelFile(
                        shipment_id=shipment.id,
                        file_path=file_path,
                        content_type=label_result.content_type or "application/pdf",
                        sha256=sha256,
                    )
                )
                if r.local_status in {"new", "failed_retryable", ""}:
                    r.local_status = "label_saved"
                r.error_message = ""
                saved += 1
                continue
            if platform == "ozon" and _ozon_label_not_ready(
                r.platform_status,
                r.raw_payload or {},
                clean_tracking_number(r.shipment_tracking_number, r.raw_payload or {}, r.platform),
            ):
                fallback_result = await apply_ozon_tracking_fallback_from_label(db, r, connector)
                if fallback_result.get("applied"):
                    saved += 1
                continue
            posting_number = r.posting_number or r.platform_order_id
            shipment = db.scalar(
                select(Shipment).where(Shipment.order_id == r.id).order_by(Shipment.id.desc())
            )
            platform_shipment_id, unavailable_reason = label_shipment_id_for_order(r, shipment)
            if unavailable_reason:
                r.error_message = unavailable_reason
                continue
            shipment_result = ShipmentResult(
                platform_shipment_id=platform_shipment_id,
                tracking_number=r.shipment_tracking_number or posting_number,
                carrier="Ozon" if platform == "ozon" else platform,
                status="label_ready",
                raw_payload=r.raw_payload or {},
            )
            normalized = NormalizedOrder(
                platform_order_id=r.platform_order_id,
                platform_order_no=r.platform_order_no or "",
                posting_number=r.posting_number or "",
                platform_status=r.platform_status or "",
                raw_payload=r.raw_payload or {},
                fulfillment_type=r.fulfillment_type or infer_fulfillment_type(platform, r.raw_payload or {}),
                is_overseas_warehouse=order_is_overseas_warehouse(r),
            )
            try:
                label_result = await connector.fetch_label(shipment_result, normalized)
            except Exception as exc:
                if platform == "allegro" and _allegro_label_fetch_unavailable_message(exc):
                    r.error_message = str(exc)[:500]
                    continue
                raise
            content = label_result.content
            if not is_real_label_pdf(content):
                continue
            file_path, sha256 = save_label_pdf(
                r.tenant_id, platform, account_id, posting_number, content
            )
            if shipment is None:
                shipment = Shipment(
                    order_id=r.id,
                    platform_shipment_id=platform_shipment_id,
                    tracking_number=r.shipment_tracking_number or "",
                    carrier="Ozon" if platform == "ozon" else platform,
                    status="label_ready",
                )
                db.add(shipment)
                db.flush()
            elif platform_shipment_id and getattr(shipment, "platform_shipment_id", "") != platform_shipment_id:
                shipment.platform_shipment_id = platform_shipment_id
            apply_label_result_tracking(r, shipment, label_result)
            if shipment and not shipment.tracking_number and r.shipment_tracking_number:
                shipment.tracking_number = r.shipment_tracking_number
            db.add(
                LabelFile(
                    shipment_id=shipment.id,
                    file_path=file_path,
                    content_type=label_result.content_type or "application/pdf",
                    sha256=sha256,
                )
            )
            if r.local_status in {"new", "failed_retryable", ""}:
                r.local_status = "label_saved"
            r.error_message = ""
            saved += 1
        except Exception:
            continue
    db.commit()
    return saved


def _logistics_lookup_number(order: Order) -> str:
    lookup_number = order.posting_number
    if not lookup_number and order.platform in {"joom_logistics", "allegro"}:
        lookup_number = order.platform_order_id
    if not lookup_number and order.platform == "mercadolibre":
        lookup_number = _shipment_payload_id(order.raw_payload) or order.platform_order_id
    return str(lookup_number or "").strip()


def _merge_logistics_stats(base: dict, extra: dict, *, prefix: str = "") -> dict:
    for key, value in extra.items():
        target_key = f"{prefix}{key}" if prefix else key
        if isinstance(value, int):
            base[target_key] = int(base.get(target_key, 0) or 0) + value
        elif key == "errors":
            base.setdefault(target_key, [])
            base[target_key].extend(value or [])
        else:
            base[target_key] = value
    return base


def order_logistics_refresh_result(stats: dict, order_id: int) -> dict:
    order_results = stats.get("order_results") or {}
    return dict(order_results.get(str(order_id)) or order_results.get(order_id) or {})


def order_logistics_refresh_description(stats: dict, order: Order, *, prefix: str) -> str:
    order_result = order_logistics_refresh_result(stats, order.id)
    return (
        f"{prefix}：本订单请求 {int(order_result.get('requested', 0) or 0)} 条，"
        f"返回 {int(order_result.get('received', 0) or 0)} 条，"
        f"更新 {int(order_result.get('updated', 0) or 0)} 条"
    )


def order_logistics_refresh_log_extra(stats: dict, order: Order) -> dict:
    batch_result = dict(stats or {})
    batch_result.pop("order_results", None)
    return {
        "result": batch_result,
        "order_result": order_logistics_refresh_result(stats, order.id),
    }


def _order_logistics_refresh_result(stats: dict, order_id: int) -> dict:
    order_results = stats.setdefault("order_results", {})
    key = str(order_id)
    if key not in order_results:
        order_results[key] = {
            "requested": 0,
            "received": 0,
            "updated": 0,
            "snapshot_status_updated": 0,
            "tracking_updated": 0,
            "shipment_created": 0,
            "shipment_updated": 0,
        }
    return order_results[key]


async def refresh_order_logistics_for_rows(
    db: Session,
    rows: list[Order],
    *,
    eligible_statuses: set[str] | None = None,
    preserve_biz_status: bool = False,
) -> dict:
    """Refresh status/logistics for selected eligible orders and backfill tracking numbers."""
    eligible_statuses = eligible_statuses or STATUS_REFRESH_BIZ_STATUSES
    now = datetime.utcnow()
    stats = {
        "total": len(rows),
        "eligible": 0,
        "skipped_not_picking": 0,
        "skipped_not_eligible": 0,
        "skipped_terminal": 0,
        "skipped_delivered_confirmed": 0,
        "skipped_low_frequency_cooldown": 0,
        "skipped_overseas_warehouse": 0,
        "skipped_logistics_label_exempt": 0,
        "skipped_external_logistics": 0,
        "eligible_statuses": sorted(eligible_statuses),
        "low_frequency_interval_seconds": LOW_FREQUENCY_STATUS_REFRESH_SECONDS,
        "requested": 0,
        "received": 0,
        "updated": 0,
        "snapshot_status_updated": 0,
        "tracking_updated": 0,
        "ozon_tracking_fallback_applied": 0,
        "shipment_created": 0,
        "shipment_updated": 0,
        "low_frequency_attempted": 0,
        "failed_accounts": 0,
        "refreshed_order_ids": [],
        "order_results": {},
        "errors": [],
    }
    eligible_rows: list[Order] = []
    for row in rows:
        if not preserve_biz_status and row.biz_status in (eligible_statuses or set()):
            if _refresh_biz_status_from_platform_snapshot(row):
                stats["updated"] += 1
                stats["snapshot_status_updated"] += 1
                order_result = _order_logistics_refresh_result(stats, row.id)
                order_result["updated"] += 1
                order_result["snapshot_status_updated"] += 1
        if order_is_overseas_warehouse(row):
            stats["skipped_overseas_warehouse"] += 1
            continue
        if order_is_logistics_label_exempt(row):
            stats["skipped_logistics_label_exempt"] += 1
            continue
        if order_uses_wanbang(row):
            stats["skipped_external_logistics"] += 1
            continue
        if row.biz_status == "已妥投":
            stats["skipped_delivered_confirmed"] += 1
            continue
        if row.biz_status not in eligible_statuses:
            stats["skipped_not_eligible"] += 1
            if row.biz_status not in TERMINAL_BIZ_STATUSES:
                stats["skipped_not_picking"] += 1
            if row.biz_status in TERMINAL_BIZ_STATUSES:
                stats["skipped_terminal"] += 1
            continue
        should_refresh, reason = _should_refresh_order_status(db, row, now)
        if not should_refresh:
            if reason == "terminal":
                stats["skipped_terminal"] += 1
            elif reason == "delivered_confirmed":
                stats["skipped_delivered_confirmed"] += 1
            elif reason == "low_frequency_cooldown":
                stats["skipped_low_frequency_cooldown"] += 1
            else:
                stats["skipped_not_eligible"] += 1
                stats["skipped_not_picking"] += 1
            continue
        eligible_rows.append(row)
    stats["eligible"] = len(eligible_rows)
    if not eligible_rows:
        return stats

    from collections import defaultdict

    account_orders: dict[tuple[str, str], list[Order]] = defaultdict(list)
    for order in eligible_rows:
        account_orders[(order.platform, order.account_id)].append(order)

    for (plat, acc_id), order_list in account_orders.items():
        with sync_job_lock(db, plat, acc_id, "status_refresh") as lock_acquired:
            if not lock_acquired:
                stats["failed_accounts"] += 1
                stats["errors"].append({"platform": plat, "account_id": acc_id, "stage": "status_refresh", "message": "status refresh already running"})
                audit_sync_event(
                    db,
                    "job_skipped_locked",
                    platform=plat,
                    account_id=acc_id,
                    job_type="status_refresh",
                    status="skipped",
                    message="status refresh already running",
                )
                continue
            account_stats = await _refresh_order_logistics_for_account(
                db,
                plat,
                acc_id,
                order_list,
                stats,
                now=now,
                preserve_biz_status=preserve_biz_status,
            )
            stats.update(account_stats)

    db.commit()
    return stats


async def _refresh_order_logistics_for_account(
    db: Session,
    plat: str,
    acc_id: str,
    order_list: list[Order],
    stats: dict,
    *,
    now: datetime,
    preserve_biz_status: bool,
) -> dict:
    local_setting = db.scalar(
        select(SyncSetting).where(SyncSetting.platform == plat, SyncSetting.account_id == acc_id)
    )
    try:
        connector = _connector_for_account(db, plat, acc_id, local_setting)
    except Exception as exc:
        stats["failed_accounts"] += 1
        stats["errors"].append({"platform": plat, "account_id": acc_id, "stage": "connector", "message": str(exc)})
        return stats

    lookup_numbers_by_order_id: dict[int, str] = {}
    for order in order_list:
        lookup_number = _logistics_lookup_number(order)
        if lookup_number:
            lookup_numbers_by_order_id[order.id] = lookup_number
            _order_logistics_refresh_result(stats, order.id)["requested"] += 1

    lookup_numbers = list(dict.fromkeys(lookup_numbers_by_order_id.values()))
    if not lookup_numbers:
        return stats
    stats["requested"] += len(lookup_numbers)

    try:
        updates = await connector.fetch_order_status_updates(lookup_numbers)
    except Exception as exc:
        stats["failed_accounts"] += 1
        stats["errors"].append({"platform": plat, "account_id": acc_id, "stage": "status_updates", "message": str(exc)})
        stats["low_frequency_attempted"] = int(stats.get("low_frequency_attempted", 0) or 0) + _mark_low_frequency_status_refresh_attempted(
            db,
            order_list,
            now,
        )
        return stats

    stats["received"] += len(updates)
    status_map: dict[str, OrderStatusUpdate] = {update.posting_number: update for update in updates}
    connector_settings = getattr(connector, "settings", {}) if connector else {}
    for order in order_list:
        lookup_number = lookup_numbers_by_order_id.get(order.id, "")
        if not lookup_number:
            continue
        before_refresh = _order_log_snapshot(order)
        order_result = _order_logistics_refresh_result(stats, order.id)
        update = status_map.get(lookup_number)
        if update:
            order_result["received"] += 1
            previous_biz_status = order.biz_status
            result = _apply_status_update_to_order(db, order, update, connector_settings=connector_settings)
            if (
                preserve_biz_status
                and order.biz_status != previous_biz_status
                and not joom_offline_shipping_target_status(order)
            ):
                order.biz_status = previous_biz_status
            if result["updated"]:
                stats["updated"] += 1
                order_result["updated"] += 1
            if result["tracking_updated"]:
                stats["tracking_updated"] += 1
                order_result["tracking_updated"] += 1
            if result["shipment_created"]:
                stats["shipment_created"] += 1
                order_result["shipment_created"] += 1
            elif result["shipment_updated"]:
                stats["shipment_updated"] += 1
                order_result["shipment_updated"] += 1
            if not result["tracking_updated"]:
                fallback_result = await apply_ozon_tracking_fallback_from_label(
                    db,
                    order,
                    connector,
                    update,
                    started_at=now,
                )
                if fallback_result.get("applied"):
                    stats["updated"] += 1
                    stats["tracking_updated"] += 1
                    stats["ozon_tracking_fallback_applied"] += 1
                    order_result["updated"] += 1
                    order_result["tracking_updated"] += 1
                    order_result["ozon_tracking_fallback_applied"] = 1
        refresh_changes = _order_sync_log_changes(order, before_refresh)
        if refresh_changes:
            order_label = (
                getattr(order, "platform_order_no", "")
                or getattr(order, "posting_number", "")
                or getattr(order, "platform_order_id", "")
                or str(order.id)
            )
            add_order_operation_log(
                db,
                order_id=order.id,
                operation_type="sync_logistics",
                operation_attribute="同步物流信息",
                description=f"订单 {order_label} 物流状态更新，" + "；".join(
                    f"{change['label']}：{change['before']} -> {change['after']}" for change in refresh_changes
                ),
                operator=SYSTEM_OPERATOR,
                source=ORDER_LOG_SYSTEM_SOURCE,
                operated_at=now,
                extra={"result": "changed", "changes": refresh_changes},
            )
        order.logistics_last_synced_at = now
        stats["refreshed_order_ids"].append(order.id)
    return stats


async def submit_platform_shipments_and_refresh_logistics(
    db: Session,
    rows: list[Order],
    *,
    eligible_statuses: set[str] | None = None,
    preserve_biz_status_on_refresh: bool = False,
) -> dict:
    """Submit eligible orders to platforms, then refresh logistics/tracking for the same rows."""
    eligible_statuses = eligible_statuses or {"配货中"}
    stats = {
        "total": len(rows),
        "eligible": 0,
        "skipped_not_picking": 0,
        "skipped_not_eligible": 0,
        "skipped_overseas_warehouse": 0,
        "skipped_logistics_label_exempt": 0,
        "skipped_joom_offline_shipping": 0,
        "eligible_statuses": sorted(eligible_statuses),
        "submitted": 0,
        "skipped_existing": 0,
        "skipped_creation_disabled": 0,
        "submit_failed": 0,
        "tracking_updated": 0,
        "shipment_created": 0,
        "shipment_updated": 0,
        "platform_tracking_attempted": 0,
        "platform_tracking_registered": 0,
        "platform_tracking_existing": 0,
        "platform_tracking_skipped": 0,
        "platform_tracking_unsupported": 0,
        "platform_tracking_failed": 0,
        "errors": [],
    }
    overseas_rows = [row for row in rows if order_is_overseas_warehouse(row)]
    overseas_ids = {row.id for row in overseas_rows}
    exempt_rows = [row for row in rows if row.id not in overseas_ids and order_is_logistics_label_exempt(row)]
    exempt_ids = {row.id for row in exempt_rows}
    joom_offline_rows = [
        row
        for row in rows
        if row.id not in overseas_ids and row.id not in exempt_ids and order_is_joom_offline_shipping(row)
    ]
    joom_offline_ids = {row.id for row in joom_offline_rows}
    eligible_rows = [
        row
        for row in rows
        if row.biz_status in eligible_statuses
        and row.id not in overseas_ids
        and row.id not in exempt_ids
        and row.id not in joom_offline_ids
    ]
    stats["eligible"] = len(eligible_rows)
    stats["skipped_overseas_warehouse"] = len(overseas_rows)
    stats["skipped_logistics_label_exempt"] = len(exempt_rows)
    stats["skipped_joom_offline_shipping"] = len(joom_offline_rows)
    stats["skipped_not_picking"] = len(rows) - len(eligible_rows) - len(overseas_rows) - len(exempt_rows) - len(joom_offline_rows)
    stats["skipped_not_eligible"] = len(rows) - len(eligible_rows) - len(overseas_rows) - len(exempt_rows) - len(joom_offline_rows)
    if not eligible_rows:
        return stats

    for row in eligible_rows:
        existing_shipment = _latest_shipment_for_order(db, row.id)
        existing_tracking_number = (
            clean_tracking_number(row.shipment_tracking_number, row.raw_payload or {}, row.platform)
            or _tracking_number_from_payload(row.raw_payload or {})
            or (
                clean_tracking_number(existing_shipment.tracking_number, row.raw_payload or {}, row.platform)
                if existing_shipment
                else ""
            )
        )
        if order_uses_wanbang(row) and existing_tracking_number:
            # A waybill already belongs to this order.  Do not create, look up, or
            # re-register a Wanbang parcel; retain the normal downstream refresh.
            if not row.shipment_tracking_number:
                row.shipment_tracking_number = existing_tracking_number
                stats["tracking_updated"] += 1
            if existing_shipment and not row.handover_at:
                row.handover_at = existing_shipment.created_at
            if row.local_status in {"", "new", "failed_retryable", "picking"}:
                row.local_status = "shipment_created"
            stats["skipped_existing"] += 1
            continue
        if _has_existing_platform_shipment(db, row):
            if existing_shipment and existing_shipment.tracking_number and not row.shipment_tracking_number:
                row.shipment_tracking_number = existing_shipment.tracking_number
                stats["tracking_updated"] += 1
            if existing_shipment and not row.handover_at:
                row.handover_at = existing_shipment.created_at
            if row.local_status in {"", "new", "failed_retryable", "picking"}:
                row.local_status = "shipment_created"
            stats["skipped_existing"] += 1
            continue

        if PLATFORM_SHIPMENT_CREATION_DISABLED:
            stats["skipped_creation_disabled"] += 1
            continue

        previous_biz_status = row.biz_status
        previous_local_status = row.local_status
        try:
            with sync_job_lock(db, row.platform, row.account_id, "shipment_create") as lock_acquired:
                if not lock_acquired:
                    stats["submit_failed"] += 1
                    stats["errors"].append(
                        {
                            "platform": row.platform,
                            "account_id": row.account_id,
                            "order_id": row.id,
                            "stage": "submit",
                            "message": "shipment create already running",
                        }
                    )
                    audit_sync_event(
                        db,
                        "job_skipped_locked",
                        platform=row.platform,
                        account_id=row.account_id,
                        job_type="shipment_create",
                        status="skipped",
                        message="shipment create already running",
                        extra={"order_id": row.id},
                    )
                    continue
                if order_uses_wanbang(row) and str(row.platform or "").strip().lower() == "dmsmatrix":
                    shipment_result = await fetch_existing_wanbang_shipment_for_order(db, row)
                elif order_uses_wanbang(row):
                    shipment_result = await create_wanbang_shipment_for_order(db, row)
                else:
                    local_setting = db.scalar(
                        select(SyncSetting).where(SyncSetting.platform == row.platform, SyncSetting.account_id == row.account_id)
                    )
                    connector = _connector_for_account(db, row.platform, row.account_id, local_setting)
                    if hasattr(connector, "settings") and isinstance(connector.settings, dict):
                        connector.settings["dry_run_fulfillment"] = False
                    shipment_result = await connector.create_platform_shipment(_normalized_order_from_row(row))
                order_tracking_changed = bool(
                    shipment_result.tracking_number and row.shipment_tracking_number != shipment_result.tracking_number
                )
                shipment_stats = _upsert_shipment_info(
                    db,
                    row,
                    platform_shipment_id=shipment_result.platform_shipment_id,
                    tracking_number=shipment_result.tracking_number,
                    carrier=shipment_result.carrier,
                    status=shipment_result.status,
                )
                if order_tracking_changed:
                    row.shipment_tracking_number = shipment_result.tracking_number
                    stats["tracking_updated"] += 1
                row.handover_at = row.handover_at or datetime.utcnow()
                row.local_status = "shipment_created"
                row.error_message = ""
                row.updated_at = datetime.utcnow()
                stats["submitted"] += 1
                if shipment_stats["created"]:
                    stats["shipment_created"] += 1
                elif shipment_stats["updated"]:
                    stats["shipment_updated"] += 1
                if shipment_stats["tracking_updated"] and not order_tracking_changed:
                    stats["tracking_updated"] += 1
                if order_uses_wanbang(row):
                    backfill_stats = await backfill_wanbang_tracking_to_platform(
                        db,
                        row,
                        tracking_number=shipment_result.tracking_number or row.shipment_tracking_number,
                        source="shipment_create",
                    )
                    for key, value in backfill_stats.items():
                        stats[f"platform_tracking_{key}"] += int(value or 0)
        except Exception as exc:
            _record_fulfillment_failure(
                row,
                exc,
                previous_biz_status=previous_biz_status,
                previous_local_status=previous_local_status,
            )
            stats["submit_failed"] += 1
            stats["errors"].append({"platform": row.platform, "account_id": row.account_id, "order_id": row.id, "stage": "submit", "message": str(exc)})

    db.commit()
    refresh_stats = await refresh_order_logistics_for_rows(
        db,
        eligible_rows,
        eligible_statuses=eligible_statuses,
        preserve_biz_status=preserve_biz_status_on_refresh,
    )
    _merge_logistics_stats(stats, refresh_stats, prefix="refresh_")
    stats["tracking_updated"] += int(refresh_stats.get("tracking_updated", 0) or 0)
    stats["shipment_created"] += int(refresh_stats.get("shipment_created", 0) or 0)
    stats["shipment_updated"] += int(refresh_stats.get("shipment_updated", 0) or 0)
    return stats


async def sync_enabled_accounts(
    db: Session,
    platform: str | None = None,
    account_id: str | None = None,
    *,
    full_refresh: bool = False,
) -> list[dict]:
    rows = db.scalars(select(PlatformAccount).where(PlatformAccount.enabled == True)).all()
    results = []
    for account in rows:
        if platform and account.platform != platform:
            continue
        if account_id and account.account_id != account_id:
            continue
        config = {
            "platform": account.platform,
            "account_id": account.account_id,
            "display_name": account.display_name,
            "enabled": account.enabled,
            "auth_type": account.auth_type,
            "settings": account.settings or {},
        }
        results.append(await sync_account(db, config, full_refresh=full_refresh))
    return results


async def run_due_catchups(db: Session, *, limit: int = 5) -> list[dict]:
    rows = db.scalars(
        select(SyncAccountState)
        .where(
            SyncAccountState.job_type == JOB_TYPE_SYNC_ORDERS,
            SyncAccountState.catchup_required == True,
        )
        .order_by(SyncAccountState.updated_at, SyncAccountState.id)
        .limit(max(1, limit))
    ).all()
    results: list[dict] = []
    for state in rows:
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == state.platform,
                PlatformAccount.account_id == state.account_id,
                PlatformAccount.enabled == True,
            )
        )
        setting = db.scalar(
            select(SyncSetting).where(
                SyncSetting.platform == state.platform,
                SyncSetting.account_id == state.account_id,
                SyncSetting.enabled == True,
            )
        )
        if not account or not setting:
            state.catchup_required = False
            state.last_message = "catchup skipped: account or setting disabled"
            db.commit()
            continue
        config = {
            "platform": account.platform,
            "account_id": account.account_id,
            "display_name": account.display_name,
            "enabled": account.enabled,
            "auth_type": account.auth_type,
            "settings": dict(account.settings or {}),
        }
        since = state.catchup_from
        audit_sync_event(
            db,
            "catchup_started",
            platform=account.platform,
            account_id=account.account_id,
            job_type=JOB_TYPE_CATCHUP_ORDERS,
            status="running",
            message=f"catchup from {since.isoformat() if since else 'beginning'}",
            extra={
                "catchup_from": since.isoformat() if since else None,
                "catchup_to": state.catchup_to.isoformat() if state.catchup_to else None,
            },
        )
        db.commit()
        try:
            result = await sync_account(
                db,
                config,
                full_refresh=True,
                job_type=JOB_TYPE_CATCHUP_ORDERS,
                since_override=since,
            )
            if result.get("status") == "success":
                state.catchup_required = False
                state.catchup_to = None
                state.last_message = "catchup completed"
                db.commit()
            results.append({"platform": account.platform, "account_id": account.account_id, **result})
        except Exception as exc:
            results.append({"platform": account.platform, "account_id": account.account_id, "status": "failed", "error": str(exc)})
    return results


async def sync_order_statuses(db: Session, platform: str | None = None, account_id: str | None = None) -> dict:
    """Refresh platform logistics/status for active non-terminal orders."""
    stmt = select(Order).where(Order.biz_status.in_(STATUS_REFRESH_BIZ_STATUSES))
    if platform:
        stmt = stmt.where(Order.platform == platform)
    if account_id:
        stmt = stmt.where(Order.account_id == account_id)
    orders = db.scalars(stmt).all()
    if not orders:
        return {"status": "success", "updated": 0, "total": 0}
    result = await refresh_order_logistics_for_rows(db, orders)
    return {"status": "success", **result}
