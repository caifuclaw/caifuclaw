from __future__ import annotations

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from time import perf_counter
from types import SimpleNamespace
from urllib.parse import quote, urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api_logger import log_api_call
from .connectors.base import LabelResult, ShipmentResult
from .credential_manager import get_credential_manager
from .logistics_rules import LOGISTICS_MATCH_STATUS_MANUAL, LOGISTICS_MATCH_STATUS_MATCHED
from .models import LogisticsAuthorization, Order, OrderItem, PlatformAccount, Shipment

WANBANG_CARRIER_CODE = "wanbang_suda_new"
WANBANG_CARRIER_NAME = "WanbExpress"
WANBANG_DEFAULT_BASE_URL = "https://api.wanbexpress.com"
WANBANG_SANDBOX_HOST = "api-sbx.wanbexpress.com"
WANBANG_MATCH_STATUSES = {LOGISTICS_MATCH_STATUS_MATCHED, LOGISTICS_MATCH_STATUS_MANUAL}
WANBANG_IMPORTED_PROCESS_CODE_RE = re.compile(r"WNBAA\d{10}[A-Z0-9]{2}", re.IGNORECASE)
WANBANG_PROCESSABLE_STATUSES = {
    "confirmed",
    "processing",
    "processed",
    "ready",
    "readytoship",
    "labelready",
    "label_ready",
    "picked",
    "packed",
    "shipping",
    "shipped",
    "collected",
    "intransit",
    "transit",
    "delivered",
}
WANBANG_UNPROCESSABLE_STATUSES = {"created", "new", "draft", "unconfirmed", "cancelled", "canceled", "deleted", "rejected", "failed"}


class WanbangApiError(RuntimeError):
    pass


class WanbangLabelNotReady(WanbangApiError):
    pass


@dataclass
class WanbangTestFlowResult:
    order_id: int
    order_no: str
    account_name: str = ""
    process_code: str = ""
    tracking_number: str = ""
    parcel_status: str = ""
    reference_id: str = ""
    label_number_type: str = "ProcessCode"
    label_bytes: int = 0
    label_sha256: str = ""
    label_attempts: int = 0
    label_ready: bool = False
    create_response: dict = field(default_factory=dict)
    confirm_response: dict | None = None
    parcel_response: dict | None = None
    request_payload: dict = field(default_factory=dict)


@dataclass
class WanbangReferenceLookupResult:
    reference_id: str = ""
    tracking_number: str = ""
    match: str = ""
    track_item_id: str = ""
    raw_response: dict = field(default_factory=dict)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _to_decimal(value: object, default: str = "0") -> Decimal:
    try:
        if value in (None, ""):
            return Decimal(default)
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _positive_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_int(value: object, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _decimal_or_none(value: object) -> Decimal | None:
    try:
        if value in (None, ""):
            return None
        parsed = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return parsed if parsed > 0 else None


def _bool_setting(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _first(*values: object) -> str:
    for value in values:
        text = _clean(value)
        if text:
            return text
    return ""


def _normalize_status(value: object) -> str:
    return "".join(ch for ch in _clean(value).casefold() if ch.isalnum() or ch == "_")


def _wanbang_status_is_processable(value: object) -> bool:
    return _normalize_status(value) in WANBANG_PROCESSABLE_STATUSES


def _wanbang_status_is_unprocessable(value: object) -> bool:
    return _normalize_status(value) in WANBANG_UNPROCESSABLE_STATUSES


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _nested(data: dict, *keys: str) -> object:
    current: object = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _unit_from_text(text: object) -> str:
    lowered = _clean(text).casefold()
    if re.search(r"\b(kg|kilogram|kilograms)\b", lowered):
        return "kg"
    if re.search(r"\b(g|gram|grams)\b", lowered):
        return "g"
    if re.search(r"\bmm\b", lowered):
        return "mm"
    if re.search(r"\b(cm|centymetr|centymetry|centimeter|centimeters)\b", lowered):
        return "cm"
    if re.search(r"\bm\b", lowered):
        return "m"
    return ""


def _first_numeric_parameter_value(parameter: dict) -> tuple[Decimal | None, str]:
    range_value = _dict(parameter.get("rangeValue"))
    values: list[object] = []
    values.extend(_list(parameter.get("values")))
    values.extend(_list(parameter.get("valuesIds")))
    values.extend(
        [
            range_value.get("from"),
            range_value.get("to"),
            range_value.get("value"),
        ]
    )
    unit = _unit_from_text(parameter.get("name"))
    for value in values:
        if isinstance(value, dict):
            unit = unit or _unit_from_text(value.get("unit"))
            value = _first(value.get("value"), value.get("amount"), value.get("from"), value.get("to"))
        text = _clean(value)
        if not text:
            continue
        parsed = _decimal_or_none(text.split()[0])
        if parsed is not None:
            unit = unit or _unit_from_text(text)
            return parsed, unit
    return None, unit


def _weight_kg_from_parameter(parameter: dict) -> Decimal | None:
    value, unit = _first_numeric_parameter_value(parameter)
    if value is None:
        return None
    if unit == "g":
        return value / Decimal("1000")
    return value


def _dimension_cm_from_parameter(parameter: dict) -> Decimal | None:
    value, unit = _first_numeric_parameter_value(parameter)
    if value is None:
        return None
    if unit == "mm":
        return value / Decimal("10")
    if unit == "m":
        return value * Decimal("100")
    return value


def _parameter_name(parameter: dict) -> str:
    return _clean(parameter.get("name")).casefold()


def _dimension_key_from_parameter(parameter: dict) -> str:
    name = _parameter_name(parameter)
    if any(marker in name for marker in ("length", "depth", "długość", "glebokosc", "głębokość", "thickness", "grubość")):
        return "length_cm"
    if any(marker in name for marker in ("width", "szerokość", "szerokosc")):
        return "width_cm"
    if any(marker in name for marker in ("height", "wysokość", "wysokosc")):
        return "height_cm"
    return ""


def _battery_type_from_parameter(parameter: dict) -> str:
    name = _parameter_name(parameter)
    if not any(marker in name for marker in ("battery", "bateria", "akumulator")):
        return ""
    values = " ".join(_clean(value) for value in _list(parameter.get("values")) + _list(parameter.get("valuesIds"))).casefold()
    if not values:
        return ""
    if any(marker in values for marker in ("no", "none", "without", "brak", "nie dotyczy")):
        return "NOBattery"
    if any(marker in values for marker in ("lithium", "lit", "li-ion", "li ion", "li-poly", "li polymer")):
        return "LithiumBattery"
    return "Battery"


def _allegro_product_info_from_offer(offer: dict) -> dict:
    parameters: list[dict] = []
    for parameter in _list(offer.get("parameters")):
        if isinstance(parameter, dict):
            parameters.append(parameter)
    for element in _list(offer.get("productSet")):
        product = _dict(_dict(element).get("product"))
        for parameter in _list(product.get("parameters")):
            if isinstance(parameter, dict):
                parameters.append(parameter)

    info: dict[str, object] = {
        "offer_id": _clean(offer.get("id")),
        "external_id": _clean(_dict(offer.get("external")).get("id")),
        "category_id": _clean(_dict(offer.get("category")).get("id")),
        "name": _clean(offer.get("name")),
        "raw_offer": offer,
    }
    for parameter in parameters:
        name = _parameter_name(parameter)
        if "weight" in name or "waga" in name:
            weight = _weight_kg_from_parameter(parameter)
            if weight is not None and info.get("weight_kg") in (None, ""):
                info["weight_kg"] = weight
        dimension_key = _dimension_key_from_parameter(parameter)
        if dimension_key and info.get(dimension_key) in (None, ""):
            dimension = _dimension_cm_from_parameter(parameter)
            if dimension is not None:
                info[dimension_key] = dimension
        battery_type = _battery_type_from_parameter(parameter)
        if battery_type and not info.get("with_battery_type"):
            info["with_battery_type"] = battery_type
    return info


def _wanbang_base_url(value: object, *, allow_sandbox: bool = False) -> str:
    text = _clean(value)
    if not text:
        return WANBANG_DEFAULT_BASE_URL
    if WANBANG_SANDBOX_HOST in text.lower() and not allow_sandbox:
        return WANBANG_DEFAULT_BASE_URL
    return text


def _raw_wanbang_process_code(order: Order) -> str:
    raw_payload = getattr(order, "raw_payload", None)
    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    return _first(
        _nested(raw_payload, "wanbang", "ProcessCode"),
        _nested(raw_payload, "wanbang", "process_code"),
        _nested(raw_payload, "wanbang", "TrackItemId"),
        _nested(raw_payload, "wanbang_trackpoints", "track_item_id"),
        _nested(raw_payload, "wanbang_trackpoints", "metadata", "TrackItemId"),
    )


def looks_like_wanbang_process_code(value: object) -> bool:
    return _looks_like_imported_wanbang_process_code(value)


def order_routes_to_wanbang(order: Order) -> bool:
    """Return whether the order's matched logistics rule selected Wanbang."""
    return _clean(getattr(order, "logistics_carrier_code", "")).lower() == WANBANG_CARRIER_CODE and _clean(
        getattr(order, "logistics_match_status", "")
    ).lower() in WANBANG_MATCH_STATUSES


def order_uses_wanbang(order: Order) -> bool:
    platform = _clean(getattr(order, "platform", "")).lower()
    if not order_routes_to_wanbang(order):
        return False
    if platform == "allegro":
        return True
    if platform == "dmsmatrix":
        return _looks_like_imported_wanbang_process_code(getattr(order, "internal_order_no", "")) or _looks_like_imported_wanbang_process_code(
            _raw_wanbang_process_code(order)
        )
    return False


def allegro_order_uses_wanbang(order: Order) -> bool:
    return order_uses_wanbang(order)


def is_wanbang_shipment(shipment: Shipment | None) -> bool:
    if shipment is None:
        return False
    carrier = _clean(getattr(shipment, "carrier", "")).casefold()
    return any(marker in carrier for marker in ("wanb", "万邦"))


def _authorization_channel_value(row: LogisticsAuthorization) -> str:
    head = _first(row.carrier_name, row.carrier_code)
    tail = _clean(row.account_name)
    return f"{head} / {tail}" if head and tail else head or tail


def _authorization_candidates(row: LogisticsAuthorization) -> set[str]:
    value = _authorization_channel_value(row)
    items = {
        value,
        f"{value} / {row.carrier_code}" if value else "",
        _clean(row.carrier_code),
        _clean(row.carrier_name),
        _clean(row.account_name),
    }
    return {item.casefold() for item in items if item}


def resolve_wanbang_authorization(db: Session, order: Order) -> LogisticsAuthorization:
    channel = _clean(getattr(order, "logistics_channel", ""))
    rows = db.scalars(
        select(LogisticsAuthorization).where(
            LogisticsAuthorization.enabled == True,
            LogisticsAuthorization.carrier_code == WANBANG_CARRIER_CODE,
        )
    ).all()
    if not rows:
        raise WanbangApiError("Wanbang logistics authorization is not enabled")

    channel_key = channel.casefold()
    for row in rows:
        if channel_key in _authorization_candidates(row):
            return row

    for row in rows:
        value = _authorization_channel_value(row).casefold()
        carrier_name = _clean(row.carrier_name).casefold()
        account_name = _clean(row.account_name).casefold()
        if value and value in channel_key:
            return row
        if account_name and account_name in channel_key:
            return row
        if carrier_name and carrier_name in channel_key:
            return row

    if len(rows) == 1:
        return rows[0]
    raise WanbangApiError(f"Wanbang authorization not found for logistics channel: {channel}")


def resolve_wanbang_test_authorization(db: Session, order: Order) -> LogisticsAuthorization:
    try:
        return resolve_wanbang_authorization(db, order)
    except WanbangApiError as original_exc:
        rows = db.scalars(
            select(LogisticsAuthorization).where(
                LogisticsAuthorization.enabled == True,
                LogisticsAuthorization.carrier_code == WANBANG_CARRIER_CODE,
            )
        ).all()
        if not rows:
            raise

        test_rows = [
            row
            for row in rows
            if any("测试" in _clean(value) or "test" in _clean(value).casefold() for value in (row.account_name, row.carrier_name))
        ]
        if len(test_rows) == 1:
            return test_rows[0]
        if len(rows) == 1:
            return rows[0]
        raise WanbangApiError(
            "Wanbang test authorization is ambiguous; match the order logistics channel or keep only one enabled Wanbang test account"
        ) from original_exc


def _decrypt_credentials(row: LogisticsAuthorization) -> dict:
    return get_credential_manager().decrypt_credentials(row.encrypted_credentials) if row.encrypted_credentials else {}


class WanbangClient:
    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        settings = settings or {}
        self.customer_code = _first(credentials.get("customer_code"), credentials.get("account_no"), credentials.get("account"))
        self.token = _clean(credentials.get("token"))
        allow_sandbox = _bool_setting(settings.get("allow_sandbox"), _bool_setting(settings.get("sandbox"), False))
        self.base_url = _wanbang_base_url(settings.get("base_url") or settings.get("api_base_url"), allow_sandbox=allow_sandbox)
        self.settings = settings
        if not self.customer_code:
            raise WanbangApiError("Wanbang customer_code is required")
        if not self.token:
            raise WanbangApiError("Wanbang token is required")

    def _headers(self, *, json_request: bool = False) -> dict:
        nonce = str(int(time.time() * 1000))
        headers = {
            "Authorization": f"Hc-OweDeveloper {self.customer_code};{self.token};{nonce}",
            "Accept": "application/json",
        }
        if json_request:
            headers["Content-Type"] = "application/json"
        return headers

    def _url(self, path: str) -> str:
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    async def _request_json(self, method: str, path: str, *, json_body: dict | None = None, operation: str) -> dict:
        url = self._url(path)
        started = perf_counter()
        response_status: int | None = None
        response_body: dict | None = None
        success = False
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.request(method, url, headers=self._headers(json_request=json_body is not None), json=json_body)
            response_status = response.status_code
            response.raise_for_status()
            response_body = response.json() if response.content else {}
            if isinstance(response_body, dict) and response_body.get("Succeeded") is False:
                error = response_body.get("Error") or response_body.get("Message") or response_body
                raise WanbangApiError(f"Wanbang API failed: {error}")
            success = True
            return response_body if isinstance(response_body, dict) else {}
        except Exception as exc:
            log_api_call(
                platform=WANBANG_CARRIER_CODE,
                account_id=self.customer_code,
                method=method,
                url=url,
                operation=operation,
                request_body=json_body,
                response_status=response_status,
                response_body=response_body,
                error_message=str(exc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise
        finally:
            if success:
                log_api_call(
                    platform=WANBANG_CARRIER_CODE,
                    account_id=self.customer_code,
                    method=method,
                    url=url,
                    operation=operation,
                    request_body=json_body,
                    response_status=response_status,
                    response_body=response_body,
                    duration_ms=int((perf_counter() - started) * 1000),
                )

    async def _request_pdf(self, path: str, *, operation: str) -> bytes:
        url = self._url(path)
        started = perf_counter()
        response_status: int | None = None
        response_body: dict | None = None
        success = False
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url, headers=self._headers())
            response_status = response.status_code
            if response.status_code == 404:
                raise WanbangLabelNotReady("Wanbang label is not ready")
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
                try:
                    response_body = response.json()
                except Exception:
                    response_body = {"content_length": len(response.content)}
                raise WanbangApiError(f"Wanbang label response is not PDF: {content_type or response.status_code}")
            success = True
            return response.content
        except Exception as exc:
            log_api_call(
                platform=WANBANG_CARRIER_CODE,
                account_id=self.customer_code,
                method="GET",
                url=url,
                operation=operation,
                response_status=response_status,
                response_body=response_body,
                error_message=str(exc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise
        finally:
            if success:
                log_api_call(
                    platform=WANBANG_CARRIER_CODE,
                    account_id=self.customer_code,
                    method="GET",
                    url=url,
                    operation=operation,
                    response_status=response_status,
                    response_body={"content_type": "application/pdf"},
                    duration_ms=int((perf_counter() - started) * 1000),
                )

    async def create_parcel(self, payload: dict) -> dict:
        return await self._request_json("POST", "/api/parcels", json_body=payload, operation="wanbang_create_parcel")

    async def confirm_parcel(self, process_code: str) -> dict:
        return await self._request_json("POST", f"/api/parcels/{process_code}/confirmation", operation="wanbang_confirm_parcel")

    async def get_parcel(self, process_code: str) -> dict:
        return await self._request_json("GET", f"/api/parcels/{process_code}", operation="wanbang_get_parcel")

    async def get_trackpoints(self, tracking_number: str) -> dict:
        tracking_number = _clean(tracking_number)
        if not tracking_number:
            raise WanbangApiError("Wanbang trackPoints query requires trackingNumber")
        return await self._request_json(
            "GET",
            f"/api/trackPoints?trackingNumber={quote(tracking_number, safe='')}",
            operation="wanbang_trackpoints_query",
        )

    async def get_label(self, process_code: str, *, parcel_number_type: str = "ProcessCode") -> bytes:
        return await self._request_pdf(
            f"/api/parcels/{process_code}/label?parcelNumberType={parcel_number_type}",
            operation="wanbang_get_label",
        )


def _shipping_address(raw_payload: dict, config: dict) -> dict:
    delivery_address = _dict(_nested(raw_payload, "delivery", "address"))
    buyer = _dict(raw_payload.get("buyer"))
    shipping_address = _dict(_nested(raw_payload, "shipping", "receiver_address"))
    city = _first(delivery_address.get("city"), shipping_address.get("city"))
    street = _first(delivery_address.get("street"), delivery_address.get("address"), shipping_address.get("street1"))
    country_code = _first(delivery_address.get("countryCode"), delivery_address.get("country_code"), shipping_address.get("country_code"), shipping_address.get("country"))
    full_name = " ".join(
        part for part in (_clean(delivery_address.get("firstName")), _clean(delivery_address.get("lastName"))) if part
    )
    name = _first(delivery_address.get("name"), full_name, delivery_address.get("companyName"), delivery_address.get("company"), shipping_address.get("name"), buyer.get("name"))
    phone = _first(delivery_address.get("phoneNumber"), delivery_address.get("phone"), buyer.get("phone"), config.get("auto_recipient_phone"))
    email = _first(delivery_address.get("email"), buyer.get("email"), config.get("auto_recipient_email"))
    postcode = _first(delivery_address.get("zipCode"), delivery_address.get("postCode"), delivery_address.get("postcode"), shipping_address.get("postcode"))
    if not name:
        raise WanbangApiError("Wanbang shipment requires recipient name")
    if not street:
        raise WanbangApiError("Wanbang shipment requires recipient street")
    if not city:
        raise WanbangApiError("Wanbang shipment requires recipient city")
    if not country_code:
        raise WanbangApiError("Wanbang shipment requires recipient country code")
    if not postcode:
        raise WanbangApiError("Wanbang shipment requires recipient postcode")
    return {
        "Contacter": name,
        "Company": _first(delivery_address.get("companyName"), delivery_address.get("company")),
        "Street1": street,
        "Street2": _first(delivery_address.get("street2"), delivery_address.get("secondLine")),
        "Street3": _first(delivery_address.get("street3")),
        "City": city,
        "Province": _first(delivery_address.get("state"), delivery_address.get("province")),
        "CountryCode": country_code.upper(),
        "Postcode": postcode,
        "Tel": phone,
        "Email": email,
        "TaxId": _first(delivery_address.get("taxId"), buyer.get("taxId")),
    }


def _items_from_order(db: Session, order: Order, raw_payload: dict) -> list[dict]:
    items: list[dict] = []
    for item in _list(raw_payload.get("products")):
        if isinstance(item, dict):
            items.append(item)
    if items:
        return items
    if getattr(order, "id", None):
        rows = db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id.asc())).all()
        for row in rows:
            items.append(
                {
                    "offer_id": row.sku,
                    "name": row.platform_product_name or row.sku,
                    "quantity": row.quantity,
                    "price": row.unit_price,
                    "currency_code": row.currency,
                    "raw_payload": row.raw_payload or {},
                }
            )
    return items


def _offer_id_from_item(item: dict) -> str:
    offer = _dict(item.get("offer"))
    raw_payload = _dict(item.get("raw_payload"))
    raw_offer = _dict(raw_payload.get("offer"))
    return _first(
        item.get("offer_id"),
        item.get("sku"),
        item.get("GoodsId"),
        offer.get("id"),
        raw_payload.get("offer_id"),
        raw_payload.get("offerId"),
        raw_offer.get("id"),
    )


def _allegro_offer_ids_from_order(db: Session, order: Order, raw_payload: dict) -> list[str]:
    offer_ids: list[str] = []
    for item in _items_from_order(db, order, raw_payload):
        offer_id = _offer_id_from_item(item)
        if offer_id and offer_id not in offer_ids:
            offer_ids.append(offer_id)
    for item in _list(raw_payload.get("lineItems")):
        if not isinstance(item, dict):
            continue
        offer_id = _first(_nested(item, "offer", "id"), item.get("offerId"))
        if offer_id and offer_id not in offer_ids:
            offer_ids.append(offer_id)
    return offer_ids


def _allegro_account_for_order(db: Session, order: Order) -> PlatformAccount | None:
    candidates = _unique_texts(getattr(order, "shop_id", ""), getattr(order, "account_id", ""))
    for account_id in candidates:
        row = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == "allegro",
                PlatformAccount.account_id == account_id,
                PlatformAccount.enabled == True,
            )
        )
        if row is not None:
            return row
    return db.scalar(
        select(PlatformAccount)
        .where(
            PlatformAccount.platform == "allegro",
            PlatformAccount.enabled == True,
            PlatformAccount.encrypted_credentials.is_not(None),
        )
        .order_by(PlatformAccount.id.asc())
    )


def _allegro_headers(credentials: dict) -> dict:
    access_token = _first(credentials.get("access_token"), credentials.get("token"))
    if not access_token:
        raise WanbangApiError("Allegro access_token is required to fetch product-offer details")
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.allegro.public.v1+json",
        "Content-Type": "application/vnd.allegro.public.v1+json",
    }


async def _fetch_allegro_offer_product_info(db: Session, order: Order, offer_ids: list[str]) -> dict[str, dict]:
    if not offer_ids or _clean(getattr(order, "platform", "")).lower() != "allegro":
        return {}
    account = _allegro_account_for_order(db, order)
    if account is None or not account.encrypted_credentials:
        return {}
    credentials = get_credential_manager().decrypt_credentials(account.encrypted_credentials)
    headers = _allegro_headers(credentials)
    settings = dict(account.settings or {})
    base_url = _first(settings.get("base_url"), "https://api.allegro.pl")
    result: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=60) as client:
        for offer_id in offer_ids:
            url = f"{base_url.rstrip('/')}/sale/product-offers/{offer_id}"
            started = perf_counter()
            response_status: int | None = None
            response_body: dict | None = None
            try:
                response = await client.get(url, headers=headers)
                response_status = response.status_code
                response.raise_for_status()
                data = response.json() if response.content else {}
                response_body = data if isinstance(data, dict) else {}
                if response_body:
                    result[offer_id] = _allegro_product_info_from_offer(response_body)
                log_api_call(
                    platform="allegro",
                    account_id=account.account_id,
                    method="GET",
                    url=url,
                    operation="allegro_product_offer",
                    response_status=response_status,
                    response_body=response_body,
                    duration_ms=int((perf_counter() - started) * 1000),
                )
            except Exception as exc:
                log_api_call(
                    platform="allegro",
                    account_id=account.account_id,
                    method="GET",
                    url=url,
                    operation="allegro_product_offer",
                    response_status=response_status,
                    response_body=response_body,
                    error_message=str(exc),
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                raise WanbangApiError(f"Failed to fetch Allegro product-offer {offer_id}: {exc}") from exc
    return result


def _merge_allegro_product_info(raw_payload: dict, product_info_by_offer_id: dict[str, dict]) -> dict:
    if not product_info_by_offer_id:
        return raw_payload
    merged = dict(raw_payload)
    products: list[dict] = []
    source_products = _list(raw_payload.get("products"))
    if source_products:
        for item in source_products:
            if not isinstance(item, dict):
                continue
            next_item = dict(item)
            offer_id = _offer_id_from_item(next_item)
            info = product_info_by_offer_id.get(offer_id)
            if info:
                next_item["allegro_product_info"] = info
                if info.get("external_id") and not next_item.get("external_id"):
                    next_item["external_id"] = info.get("external_id")
            products.append(next_item)
    else:
        for item in _list(raw_payload.get("lineItems")):
            if not isinstance(item, dict):
                continue
            offer = _dict(item.get("offer"))
            price = _dict(item.get("price"))
            offer_id = _first(offer.get("id"), item.get("offerId"), item.get("id"))
            next_item = {
                "offer_id": offer_id,
                "name": _first(offer.get("name"), item.get("name")),
                "quantity": item.get("quantity") or 1,
                "price": price.get("amount") if price else item.get("price"),
                "currency_code": price.get("currency") if price else "",
                "raw_payload": item,
            }
            info = product_info_by_offer_id.get(offer_id)
            if info:
                next_item["allegro_product_info"] = info
                next_item["external_id"] = info.get("external_id")
            products.append(next_item)
    if products:
        merged["products"] = products
    merged["allegro_product_offers"] = product_info_by_offer_id
    return merged


def _declared_value(item: dict, config: dict) -> Decimal:
    default_value = _to_decimal(config.get("default_declared_value"), "1")
    price = _to_decimal(item.get("price"), str(default_value))
    return price if price > 0 else default_value


def _declared_currency(order: Order, raw_payload: dict, items: list[dict] | None = None) -> str:
    item_currency = ""
    for item in items or _list(raw_payload.get("products")):
        if not isinstance(item, dict):
            continue
        price = _dict(item.get("price"))
        item_currency = _first(item.get("currency_code"), price.get("currency"))
        if item_currency:
            break
    currency = _first(
        getattr(order, "currency", ""),
        raw_payload.get("currency_code"),
        item_currency,
    )
    if not currency:
        raise WanbangApiError("Wanbang declared currency is required from order or item data")
    return currency


def _item_product_info(item: dict) -> dict:
    return _dict(item.get("allegro_product_info"))


def _item_weight_kg(item: dict, config: dict) -> float:
    info = _item_product_info(item)
    return _positive_float(info.get("weight_kg"), _positive_float(config.get("item_weight_kg"), _positive_float(config.get("default_weight_kg"), 0.2)))


def _item_declared_names(item: dict, config: dict) -> tuple[str, str]:
    default_name_en = _first(config.get("default_declared_name_en"), "goods")
    default_name_cn = _first(config.get("default_declared_name_cn"), "goods")
    info = _item_product_info(item)
    raw_payload = _dict(item.get("raw_payload"))
    raw_offer = _dict(raw_payload.get("offer"))
    raw_external = _dict(raw_offer.get("external"))
    haystack = " ".join(
        _clean(value)
        for value in (
            info.get("external_id"),
            item.get("external_id"),
            item.get("offer_id"),
            item.get("sku"),
            item.get("name"),
            raw_external.get("id"),
            raw_offer.get("name"),
            info.get("name"),
        )
        if _clean(value)
    ).casefold()
    if any(marker in haystack for marker in ("album", "mini album", "专辑", "相册", "pop_")):
        return "album", "相册"
    if any(marker in haystack for marker in ("book", "dictionary", "brochure", "guide", "libro", "książ", "书", "图书")):
        return "book", "书籍"
    return default_name_en, default_name_cn


def _item_details(db: Session, order: Order, raw_payload: dict, config: dict) -> list[dict]:
    default_name_en = _first(config.get("default_declared_name_en"), "goods")
    default_name_cn = _first(config.get("default_declared_name_cn"), "goods")
    details: list[dict] = []
    items = _items_from_order(db, order, raw_payload)
    currency = _declared_currency(order, raw_payload, items)
    for item in items:
        info = _item_product_info(item)
        name = _first(item.get("name"), default_name_en)
        quantity = _positive_int(item.get("quantity"), 1)
        value = _declared_value(item, config)
        declared_name_en, declared_name_cn = _item_declared_names(item, config)
        details.append(
            {
                "GoodsId": _first(info.get("external_id"), item.get("external_id"), item.get("offer_id"), item.get("sku"), name),
                "GoodsTitle": name[:100],
                "DeclaredNameEn": declared_name_en[:100],
                "DeclaredNameCn": declared_name_cn[:100],
                "Quantity": quantity,
                "DeclaredValue": {"Code": currency, "Value": float(value)},
                "ExportDeclaredValue": {"Code": currency, "Value": float(value)},
                "WeightInKg": _item_weight_kg(item, config),
                "HSCode": _first(config.get("default_hs_code")),
            }
        )
    if not details:
        details.append(
            {
                "GoodsId": _first(order.platform_order_id, order.posting_number, "item"),
                "GoodsTitle": default_name_en,
                "DeclaredNameEn": default_name_en,
                "DeclaredNameCn": default_name_cn,
                "Quantity": 1,
                "DeclaredValue": {"Code": currency, "Value": float(_to_decimal(config.get("default_declared_value"), "1"))},
                "ExportDeclaredValue": {"Code": currency, "Value": float(_to_decimal(config.get("default_declared_value"), "1"))},
                "WeightInKg": _positive_float(config.get("item_weight_kg"), _positive_float(config.get("default_weight_kg"), 0.2)),
                "HSCode": _first(config.get("default_hs_code")),
            }
        )
    return details


def _package_dimension(raw_payload: dict, config: dict, key: str, config_key: str, default: float) -> float:
    values = []
    for item in _list(raw_payload.get("products")):
        if not isinstance(item, dict):
            continue
        info = _item_product_info(item)
        value = _positive_float(info.get(key), 0)
        if value > 0:
            values.append(value)
    if values:
        return max(values)
    return _positive_float(config.get(config_key), default)


def _package_weight_kg(raw_payload: dict, config: dict) -> float:
    total = 0.0
    for item in _list(raw_payload.get("products")):
        if not isinstance(item, dict):
            continue
        info = _item_product_info(item)
        weight = _positive_float(info.get("weight_kg"), 0)
        if weight <= 0:
            continue
        total += weight * _positive_int(item.get("quantity"), 1)
    if total > 0:
        return total
    return _positive_float(config.get("default_weight_kg"), 0.2)


def _payload_battery_type(raw_payload: dict, config: dict) -> str:
    for item in _list(raw_payload.get("products")):
        if not isinstance(item, dict):
            continue
        battery_type = _first(_item_product_info(item).get("with_battery_type"))
        if battery_type and battery_type != "NOBattery":
            return battery_type
    for item in _list(raw_payload.get("products")):
        if not isinstance(item, dict):
            continue
        battery_type = _first(_item_product_info(item).get("with_battery_type"))
        if battery_type:
            return battery_type
    return _first(config.get("with_battery_type"), "NOBattery")


def build_wanbang_parcel_payload(db: Session, order: Order, config: dict) -> dict:
    raw_payload = order.raw_payload if isinstance(order.raw_payload, dict) else {}
    warehouse_code = _first(config.get("warehouse_code"))
    shipping_method = _first(config.get("shipping_method"), config.get("service_code"))
    if not warehouse_code:
        raise WanbangApiError("Wanbang warehouse_code is required in logistics authorization config")
    if not shipping_method:
        raise WanbangApiError("Wanbang shipping_method is required in logistics authorization config")

    item_details = _item_details(db, order, raw_payload, config)
    total_value = sum(
        _to_decimal(_dict(item.get("DeclaredValue")).get("Value"), "0") * Decimal(str(item.get("Quantity") or 1))
        for item in item_details
    )
    total_currency = _dict(item_details[0].get("DeclaredValue")).get("Code") if item_details else ""
    weight = _package_weight_kg(raw_payload, config)
    length = _package_dimension(raw_payload, config, "length_cm", "length_cm", 1.0)
    width = _package_dimension(raw_payload, config, "width_cm", "width_cm", 1.0)
    height = _package_dimension(raw_payload, config, "height_cm", "height_cm", 1.0)
    reference_id = _first(config.get("reference_prefix")) + _first(
        getattr(order, "internal_order_no", ""),
        order.posting_number,
        order.platform_order_id,
        order.platform_order_no,
    )
    payload = {
        "ReferenceId": reference_id,
        "ShippingAddress": _shipping_address(raw_payload, config),
        "WeightInKg": weight,
        "ItemDetails": item_details,
        "TotalValue": {
            "Code": total_currency,
            "Value": float(total_value if total_value > 0 else _to_decimal(config.get("default_declared_value"), "1")),
        },
        "TotalVolume": {
            "Length": length,
            "Width": width,
            "Height": height,
            "Unit": "CM",
        },
        "WithBatteryType": _payload_battery_type(raw_payload, config),
        "WarehouseCode": warehouse_code,
        "ShippingMethod": shipping_method,
        "ItemType": _first(config.get("item_type"), "SPX"),
        "TradeType": _first(config.get("trade_type"), "B2C"),
        "AutoConfirm": _bool_setting(config.get("auto_confirm"), True),
        "AllowRemoteArea": _bool_setting(config.get("allow_remote_area"), True),
    }
    company_name = _first(config.get("production_company_name"), config.get("company_name_en"))
    company_uscc = _first(config.get("production_company_uscc"))
    if company_name or company_uscc:
        payload["ProductionOrSalesCompany"] = {
            "Name": company_name,
            "USCC": company_uscc,
        }
    return payload


def _wanbang_result_data(response: dict) -> dict:
    data = response.get("Data") if isinstance(response, dict) else {}
    return data if isinstance(data, dict) else {}


def wanbang_reference_lookup_from_trackpoints(response: dict) -> WanbangReferenceLookupResult:
    data = _wanbang_result_data(response)
    metadata = _dict(data.get("Metadata"))
    match = _first(data.get("Match"))
    if _normalize_status(match) == "unknown":
        return WanbangReferenceLookupResult(match=match, raw_response=response if isinstance(response, dict) else {})
    return WanbangReferenceLookupResult(
        reference_id=_first(metadata.get("ReferenceId"), metadata.get("ReferenceID"), metadata.get("reference_id"), data.get("ReferenceId"), data.get("reference_id")),
        tracking_number=_first(metadata.get("TrackingNumber"), metadata.get("tracking_number"), data.get("TrackingNumber")),
        match=match,
        track_item_id=_first(metadata.get("TrackItemId"), metadata.get("track_item_id"), data.get("TrackItemId"), data.get("ProcessCode")),
        raw_response=response if isinstance(response, dict) else {},
    )


def _looks_like_tracking_number(value: object) -> bool:
    text = _clean(value)
    if not text:
        return False
    lowered = text.casefold()
    if lowered in {"success", "processing", "processed", "failed", "error", "pending", "created", "confirmed"}:
        return False
    return bool(re.search(r"\d", text))


def _tracking_from_parcel(data: dict) -> str:
    tracking_result = _dict(data.get("TrackingNoProcessResult"))
    for value in (
        data.get("FinalTrackingNumber"),
        data.get("TrackingNumber"),
        data.get("RealTrackingNumber"),
        tracking_result.get("Code"),
    ):
        if _looks_like_tracking_number(value):
            return _clean(value)
    return ""


def _shipment_from_parcel(data: dict, *, raw_payload: dict | None = None) -> ShipmentResult:
    raw_payload = raw_payload or data
    process_code = _first(data.get("ProcessCode"), _nested(raw_payload, "Data", "ProcessCode"))
    return ShipmentResult(
        platform_shipment_id=process_code,
        tracking_number=_tracking_from_parcel(data),
        carrier=WANBANG_CARRIER_NAME,
        status=_first(data.get("Status"), "created"),
        raw_payload=raw_payload,
    )


async def run_wanbang_test_flow_for_order(
    db: Session,
    order: Order,
    *,
    status_retry_attempts: int = 5,
    status_retry_delay_seconds: float = 2.0,
    label_retry_attempts: int = 5,
    label_retry_delay_seconds: float = 2.0,
) -> tuple[WanbangTestFlowResult, LabelResult, ShipmentResult]:
    auth = resolve_wanbang_test_authorization(db, order)
    credentials = _decrypt_credentials(auth)
    config = dict(auth.config_json or {})
    settings = {**config, **dict(auth.settings_json or {})}
    client = WanbangClient(credentials, settings)
    payload = build_wanbang_parcel_payload(db, order, config)

    create_response = await client.create_parcel(payload)
    data = _wanbang_result_data(create_response)
    process_code = _first(data.get("ProcessCode"))
    if not process_code:
        raise WanbangApiError("Wanbang create parcel response missing ProcessCode")

    confirm_response = None
    if not _bool_setting(payload.get("AutoConfirm"), True):
        confirm_response = await client.confirm_parcel(process_code)
        confirm_data = _wanbang_result_data(confirm_response)
        if confirm_data:
            data = {**data, **confirm_data}

    parcel_response: dict | None = None
    status_attempts = max(1, int(status_retry_attempts or 1))
    parcel_status = ""
    for attempt in range(1, status_attempts + 1):
        parcel_response = await client.get_parcel(process_code)
        parcel_data = _wanbang_result_data(parcel_response)
        if parcel_data:
            data = {**data, **parcel_data}
        parcel_status = _first(data.get("Status"))
        if not parcel_status or _wanbang_status_is_processable(parcel_status) or not _wanbang_status_is_unprocessable(parcel_status):
            break
        if attempt < status_attempts:
            await asyncio.sleep(max(0.0, float(status_retry_delay_seconds or 0)))

    if parcel_status and _wanbang_status_is_unprocessable(parcel_status):
        raise WanbangApiError(f"Wanbang parcel status is not ready for label after {status_attempts} attempts: {parcel_status}")

    content: bytes | None = None
    last_error: Exception | None = None
    attempts = max(1, int(label_retry_attempts or 1))
    for attempt in range(1, attempts + 1):
        try:
            content = await client.get_label(process_code, parcel_number_type="ProcessCode")
            attempts = attempt
            break
        except WanbangLabelNotReady as exc:
            last_error = exc
            if attempt >= attempts:
                break
            await asyncio.sleep(max(0.0, float(label_retry_delay_seconds or 0)))

    if content is None:
        raise WanbangApiError(f"Wanbang label is not ready after {attempts} attempts") from last_error

    shipment_result = _shipment_from_parcel(
        data or {"ProcessCode": process_code},
        raw_payload={"create": create_response, "confirm": confirm_response or {}, "parcel": parcel_response, "request": payload},
    )
    label_raw = _label_raw_payload(
        content=content,
        shipment_result=shipment_result,
        parcel_response=parcel_response,
        label_number=process_code,
        label_number_type="ProcessCode",
    )
    label_result = LabelResult(content=content, raw_payload=label_raw)
    result = WanbangTestFlowResult(
        order_id=getattr(order, "id", 0) or 0,
        order_no=_first(getattr(order, "platform_order_no", ""), getattr(order, "posting_number", ""), getattr(order, "platform_order_id", "")),
        account_name=_first(
            getattr(auth, "account_name", ""),
            getattr(auth, "carrier_name", ""),
            getattr(auth, "carrier_code", ""),
        ),
        process_code=process_code,
        tracking_number=shipment_result.tracking_number,
        parcel_status=shipment_result.status,
        reference_id=_first(payload.get("ReferenceId")),
        label_bytes=len(content),
        label_sha256=hashlib.sha256(content).hexdigest(),
        label_attempts=attempts,
        label_ready=True,
        create_response=create_response,
        confirm_response=confirm_response,
        parcel_response=parcel_response,
        request_payload=payload,
    )
    return result, label_result, shipment_result


def _unique_texts(*values: object) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _looks_like_imported_wanbang_process_code(value: object) -> bool:
    return bool(WANBANG_IMPORTED_PROCESS_CODE_RE.fullmatch(_clean(value)))


def _order_raw_payload(order: Order) -> dict:
    return order.raw_payload if isinstance(getattr(order, "raw_payload", None), dict) else {}


def _tracking_candidates(order: Order, shipment: Shipment | None) -> list[str]:
    raw_payload = _order_raw_payload(order)
    shipment_payload = _dict(raw_payload.get("shipment"))
    shipping_payload = _dict(raw_payload.get("shipping"))
    logistics_payload = _dict(raw_payload.get("logistics"))
    tracking_payload = _dict(raw_payload.get("tracking"))
    return _unique_texts(
        getattr(shipment, "tracking_number", ""),
        getattr(order, "shipment_tracking_number", ""),
        raw_payload.get("FinalTrackingNumber"),
        raw_payload.get("TrackingNumber"),
        raw_payload.get("RealTrackingNumber"),
        raw_payload.get("shipment_tracking_number"),
        raw_payload.get("tracking_number"),
        shipment_payload.get("tracking_number"),
        shipment_payload.get("trackingNumber"),
        shipping_payload.get("tracking_number"),
        shipping_payload.get("trackingNumber"),
        logistics_payload.get("tracking_number"),
        logistics_payload.get("trackingNumber"),
        tracking_payload.get("tracking_number"),
        tracking_payload.get("trackingNumber"),
    )


def _process_code_candidates(order: Order, shipment: Shipment | None) -> list[str]:
    raw_payload = _order_raw_payload(order)
    tracking_values = set(_tracking_candidates(order, shipment))
    internal_order_no = _first(getattr(order, "internal_order_no", ""))
    candidates = _unique_texts(
        _nested(raw_payload, "wanbang", "ProcessCode"),
        _nested(raw_payload, "wanbang", "process_code"),
        _nested(raw_payload, "wanbang", "TrackItemId"),
        _nested(raw_payload, "wanbang_trackpoints", "track_item_id"),
        _nested(raw_payload, "wanbang_trackpoints", "metadata", "TrackItemId"),
        _nested(raw_payload, "create", "Data", "ProcessCode"),
        _nested(raw_payload, "parcel", "Data", "ProcessCode"),
        raw_payload.get("ProcessCode"),
        raw_payload.get("process_code"),
        internal_order_no if _looks_like_imported_wanbang_process_code(internal_order_no) else "",
        getattr(shipment, "platform_shipment_id", ""),
    )
    return [candidate for candidate in candidates if candidate not in tracking_values]


def _reference_id_candidates(order: Order, shipment: Shipment | None, config: dict) -> list[str]:
    raw_payload = _order_raw_payload(order)
    prefix = _first(config.get("reference_prefix"))
    base_values = _unique_texts(
        _nested(raw_payload, "wanbang", "ReferenceId"),
        _nested(raw_payload, "wanbang", "reference_id"),
        _nested(raw_payload, "create", "request", "ReferenceId"),
        _nested(raw_payload, "request", "ReferenceId"),
        _nested(raw_payload, "parcel", "Data", "ReferenceId"),
        raw_payload.get("ReferenceId"),
        raw_payload.get("reference_id"),
        getattr(order, "internal_order_no", ""),
        raw_payload.get("hawb"),
        raw_payload.get("HAWB"),
        getattr(order, "posting_number", ""),
        getattr(order, "platform_order_id", ""),
        getattr(order, "platform_order_no", ""),
        _nested(raw_payload, "checkoutForm", "id"),
        _nested(raw_payload, "checkout", "id"),
        raw_payload.get("id"),
        getattr(shipment, "platform_shipment_id", ""),
    )
    tracking_values = set(_tracking_candidates(order, shipment))
    result: list[str] = []
    for value in base_values:
        if value in tracking_values:
            continue
        if prefix and not value.startswith(prefix):
            result.append(f"{prefix}{value}")
        result.append(value)
    return _unique_texts(*result)


def _tracking_fallback(order: Order, shipment: Shipment | None) -> str:
    return _first(*_tracking_candidates(order, shipment))


def _label_raw_payload(
    *,
    content: bytes,
    shipment_result: ShipmentResult,
    parcel_response: dict | None,
    label_number: str,
    label_number_type: str,
) -> dict:
    return {
        "shipment_tracking_number": shipment_result.tracking_number,
        "tracking_number": shipment_result.tracking_number,
        "waybill_number": shipment_result.tracking_number,
        "shipment": {
            "tracking_number": shipment_result.tracking_number,
            "trackingNumber": shipment_result.tracking_number,
            "shipment_id": shipment_result.platform_shipment_id,
            "carrier": WANBANG_CARRIER_NAME,
        },
        "parcel": parcel_response or {},
        "wanbang_label_number": label_number,
        "wanbang_label_number_type": label_number_type,
        "label_sha256": hashlib.sha256(content).hexdigest(),
    }


async def create_wanbang_shipment_for_order(db: Session, order: Order) -> ShipmentResult:
    auth = resolve_wanbang_authorization(db, order)
    credentials = _decrypt_credentials(auth)
    config = dict(auth.config_json or {})
    settings = {**config, **dict(auth.settings_json or {})}
    client = WanbangClient(credentials, settings)
    raw_payload = order.raw_payload if isinstance(order.raw_payload, dict) else {}
    product_info_by_offer_id = await _fetch_allegro_offer_product_info(db, order, _allegro_offer_ids_from_order(db, order, raw_payload))
    payload_order = SimpleNamespace(
        id=getattr(order, "id", None),
        platform=getattr(order, "platform", ""),
        internal_order_no=getattr(order, "internal_order_no", ""),
        posting_number=getattr(order, "posting_number", ""),
        platform_order_id=getattr(order, "platform_order_id", ""),
        platform_order_no=getattr(order, "platform_order_no", ""),
        currency=getattr(order, "currency", ""),
        raw_payload=_merge_allegro_product_info(raw_payload, product_info_by_offer_id),
    )
    payload = build_wanbang_parcel_payload(db, payload_order, config)
    create_response = await client.create_parcel(payload)
    data = _wanbang_result_data(create_response)
    process_code = _first(data.get("ProcessCode"))
    if not process_code:
        raise WanbangApiError("Wanbang create parcel response missing ProcessCode")

    raw_payload = {"create": create_response, "request": payload}
    if not _bool_setting(payload.get("AutoConfirm"), True):
        confirm_response = await client.confirm_parcel(process_code)
        raw_payload["confirm"] = confirm_response
        confirm_data = _wanbang_result_data(confirm_response)
        if confirm_data:
            data = {**data, **confirm_data}

    if not _tracking_from_parcel(data):
        parcel_response = await client.get_parcel(process_code)
        raw_payload["parcel"] = parcel_response
        parcel_data = _wanbang_result_data(parcel_response)
        if parcel_data:
            data = {**data, **parcel_data}

    return _shipment_from_parcel(data, raw_payload=raw_payload)


async def fetch_existing_wanbang_shipment_for_order(db: Session, order: Order) -> ShipmentResult:
    auth = resolve_wanbang_authorization(db, order)
    credentials = _decrypt_credentials(auth)
    config = dict(auth.config_json or {})
    settings = {**config, **dict(auth.settings_json or {})}
    client = WanbangClient(credentials, settings)
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id).order_by(Shipment.id.desc()))
    if shipment is not None and not is_wanbang_shipment(shipment):
        shipment = None

    candidates = _process_code_candidates(order, shipment)
    errors: list[str] = []
    for process_code in candidates:
        try:
            parcel_response = await client.get_parcel(process_code)
        except Exception as exc:
            errors.append(f"{process_code}: {exc}")
            continue
        parcel_data = _wanbang_result_data(parcel_response)
        shipment_result = _shipment_from_parcel(
            parcel_data or {"ProcessCode": process_code},
            raw_payload={"parcel": parcel_response},
        )
        if not shipment_result.platform_shipment_id:
            shipment_result.platform_shipment_id = process_code
        if not shipment_result.tracking_number:
            shipment_result.tracking_number = _tracking_fallback(order, shipment)
        shipment_result.carrier = shipment_result.carrier or WANBANG_CARRIER_NAME
        shipment_result.status = _first(shipment_result.status, "existing")
        return shipment_result

    if not candidates:
        errors.append("missing Wanbang ProcessCode")
    raise WanbangApiError("Wanbang parcel query failed: " + "; ".join(errors))


async def fetch_wanbang_reference_id_by_tracking(db: Session, order: Order, tracking_number: str) -> WanbangReferenceLookupResult:
    auth = resolve_wanbang_authorization(db, order)
    credentials = _decrypt_credentials(auth)
    config = dict(auth.config_json or {})
    settings = {**config, **dict(auth.settings_json or {})}
    client = WanbangClient(credentials, settings)
    response = await client.get_trackpoints(tracking_number)
    return wanbang_reference_lookup_from_trackpoints(response)


async def fetch_wanbang_label_for_order(db: Session, order: Order) -> tuple[LabelResult, ShipmentResult]:
    auth = resolve_wanbang_authorization(db, order)
    credentials = _decrypt_credentials(auth)
    config = dict(auth.config_json or {})
    settings = {**config, **dict(auth.settings_json or {})}
    client = WanbangClient(credentials, settings)
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id).order_by(Shipment.id.desc()))
    if shipment is not None and not is_wanbang_shipment(shipment):
        shipment = None

    tracking_fallback = _tracking_fallback(order, shipment)
    process_candidates = _process_code_candidates(order, shipment)
    reference_candidates = _reference_id_candidates(order, shipment, config)
    shipment_result: ShipmentResult | None = None

    if not process_candidates and not reference_candidates and not tracking_fallback:
        shipment_result = await create_wanbang_shipment_for_order(db, order)
        tracking_fallback = _first(shipment_result.tracking_number, tracking_fallback)
        process_candidates = _unique_texts(shipment_result.platform_shipment_id, *process_candidates)

    label_number_type = _first(config.get("label_parcel_number_type"), "auto").lower()
    attempts: list[tuple[str, str]] = []
    if label_number_type == "referenceid":
        attempts.extend((candidate, "ReferenceId") for candidate in reference_candidates)
        attempts.extend((candidate, "ProcessCode") for candidate in process_candidates)
    else:
        attempts.extend((candidate, "ProcessCode") for candidate in process_candidates)
        attempts.extend((candidate, "ReferenceId") for candidate in reference_candidates)

    errors: list[str] = []
    seen_attempts: set[tuple[str, str]] = set()
    for label_number, parcel_number_type in attempts:
        label_number = _clean(label_number)
        key = (label_number, parcel_number_type)
        if not label_number or key in seen_attempts:
            continue
        seen_attempts.add(key)

        parcel_response: dict | None = None
        parcel_data: dict = {}
        try:
            parcel_response = await client.get_parcel(label_number)
            parcel_data = _wanbang_result_data(parcel_response)
        except Exception as exc:
            errors.append(f"{parcel_number_type}:{label_number}: parcel query failed: {exc}")

        try:
            content = await client.get_label(label_number, parcel_number_type=parcel_number_type)
        except Exception as exc:
            errors.append(f"{parcel_number_type}:{label_number}: label query failed: {exc}")
            continue

        data_for_result = parcel_data or ({"ProcessCode": label_number} if parcel_number_type == "ProcessCode" else {})
        current_result = _shipment_from_parcel(data_for_result, raw_payload={"parcel": parcel_response or {}})
        if shipment_result and not current_result.platform_shipment_id:
            current_result.platform_shipment_id = shipment_result.platform_shipment_id
        if parcel_number_type == "ProcessCode" and not current_result.platform_shipment_id:
            current_result.platform_shipment_id = label_number
        if not current_result.tracking_number:
            current_result.tracking_number = tracking_fallback
        current_result.carrier = current_result.carrier or WANBANG_CARRIER_NAME
        current_result.status = _first(current_result.status, "label_ready")

        label_raw = _label_raw_payload(
            content=content,
            shipment_result=current_result,
            parcel_response=parcel_response,
            label_number=label_number,
            label_number_type=parcel_number_type,
        )
        return LabelResult(content=content, raw_payload=label_raw), current_result

    if not tracking_fallback and not process_candidates:
        shipment_result = await create_wanbang_shipment_for_order(db, order)
        process_code = _clean(shipment_result.platform_shipment_id)
        if process_code:
            parcel_response = await client.get_parcel(process_code)
            parcel_data = _wanbang_result_data(parcel_response)
            current_result = _shipment_from_parcel(parcel_data or {"ProcessCode": process_code}, raw_payload={"parcel": parcel_response})
            if not current_result.tracking_number:
                current_result.tracking_number = _first(shipment_result.tracking_number, tracking_fallback)
            content = await client.get_label(process_code, parcel_number_type="ProcessCode")
            label_raw = _label_raw_payload(
                content=content,
                shipment_result=current_result,
                parcel_response=parcel_response,
                label_number=process_code,
                label_number_type="ProcessCode",
            )
            return LabelResult(content=content, raw_payload=label_raw), current_result

    detail = "; ".join(errors[-6:]) if errors else "no ProcessCode or ReferenceId candidates"
    raise WanbangApiError(f"Wanbang label fetch failed: {detail}")
