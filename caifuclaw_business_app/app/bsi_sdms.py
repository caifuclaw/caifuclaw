from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .credential_manager import get_credential_manager
from .email_service import (
    EMAIL_NOTIFICATION_BSI_ADDRESS_ANOMALY,
    get_email_setting,
    notification_recipients_for,
    send_email,
)
from .models import (
    LogisticsAuthorization,
    LogisticsOrderSubmission,
    Order,
    OrderItem,
    OrderOperationLog,
    PlatformAccount,
)
from .order_operation_logs import (
    ORDER_LOG_SYSTEM_SOURCE,
    SYSTEM_OPERATOR,
    add_order_operation_logs,
)
from .order_types import JOOM_PLATFORM_CODES
from .product_models import Product, ProductShopMapping


logger = logging.getLogger(__name__)

BSI_CARRIER_CODE = "bsi_overseas"
BSI_ADDRESS_ALERT_OPERATION_TYPE = "bsi_address_anomaly_email"
SDMS_DEFAULT_BASE_URL = "https://gateway.gotofreight.com/sdmspanel"
SDMS_CREATE_DRAFT_PATH = "/apitask/v1/ReceiveStockOrderOut"
SDMS_QUERY_SKU_PATH = "/apitask/v1/QueryProductSkuList"
SDMS_QUERY_WAREHOUSE_PATH = "/apitask/v1/QueryCustomerVisibleWarehouseList"
SDMS_QUERY_CHANNEL_PATH = "/apitask/v1/QueryCustomerVisibleChannelList"
SDMS_QUERY_SKU_TRACKING_PATH = "/apitask/v1/QuerySkuTracking"


class SdmsApiError(RuntimeError):
    def __init__(self, message: str, *, uncertain: bool = False, response_json: dict | None = None):
        super().__init__(message)
        self.uncertain = uncertain
        self.response_json = response_json or {}


@dataclass(frozen=True)
class SdmsCredentials:
    app_id: str
    customer_code: str
    customer_secret: str


@dataclass
class SdmsAuthorization:
    row: LogisticsAuthorization
    credentials: SdmsCredentials
    config: dict[str, Any]


@dataclass
class PreparedBsiDraft:
    transaction_id: str
    customer_order_no: str
    rows: list[Order]
    delivery_info: dict[str, Any]
    goods_list: list[dict[str, Any]]


@dataclass(frozen=True)
class BsiAddressAnomaly:
    code: str
    reason: str
    normalized_address: str
    fingerprint: str


@dataclass
class BsiDraftGroupResult:
    rows: list[Order]
    status: str
    message: str
    provider_order_no: str = ""
    reused: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"


@dataclass
class BsiDraftProcessingResult:
    groups: list[BsiDraftGroupResult] = field(default_factory=list)

    @property
    def succeeded_rows(self) -> list[Order]:
        return [row for group in self.groups if group.succeeded for row in group.rows]

    @property
    def succeeded_group_count(self) -> int:
        return sum(1 for group in self.groups if group.succeeded)

    @property
    def waiting_group_count(self) -> int:
        return sum(1 for group in self.groups if not group.succeeded)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _recursive_sorted(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _recursive_sorted(value[key])
            for key in sorted(value, key=lambda item: (str(item).casefold(), str(item)))
        }
    if isinstance(value, list):
        return [_recursive_sorted(item) for item in value]
    return value


def sdms_signing_json(payload: dict[str, Any]) -> str:
    unsigned = {
        key: value
        for key, value in payload.items()
        if str(key).casefold() not in {"requesttime", "sign"}
    }
    serialized = json.dumps(
        _recursive_sorted(unsigned),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return serialized.replace("/", "\\/")


def generate_sdms_sign(
    payload: dict[str, Any],
    *,
    customer_code: str,
    customer_secret: str,
    request_time: str,
) -> str:
    sha1_value = hashlib.sha1((customer_code + sdms_signing_json(payload)).encode("utf-8")).hexdigest()
    return hashlib.md5((request_time + sha1_value + customer_secret).encode("utf-8")).hexdigest()


def sdms_request_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(sdms_signing_json(payload).encode("utf-8")).hexdigest()


def _api_success(response_json: dict[str, Any]) -> bool:
    value = response_json.get("Value") if isinstance(response_json.get("Value"), dict) else {}
    result = value.get("Result") if isinstance(value.get("Result"), dict) else {}
    try:
        status_ok = int(response_json.get("Status")) == 200
    except (TypeError, ValueError):
        status_ok = False
    return status_ok and result.get("IsSuccess") is True


def _api_message(response_json: dict[str, Any]) -> str:
    value = response_json.get("Value") if isinstance(response_json.get("Value"), dict) else {}
    result = value.get("Result") if isinstance(value.get("Result"), dict) else {}
    return _clean_text(
        response_json.get("Message")
        or response_json.get("Code")
        or result.get("Message")
        or result.get("ErrorMessage")
        or "SDMS 接口返回失败"
    )


class SdmsClient:
    def __init__(
        self,
        credentials: SdmsCredentials,
        *,
        base_url: str = SDMS_DEFAULT_BASE_URL,
        timeout_seconds: float = 30,
        include_customer_secret: bool = False,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.include_customer_secret = include_customer_secret

    def signed_payload(self, payload: dict[str, Any], request_time: str | None = None) -> dict[str, Any]:
        request_time = request_time or datetime.now().strftime("%Y%m%d%H%M%S")
        signed = dict(payload)
        if self.include_customer_secret:
            signed["CustomerSecret"] = self.credentials.customer_secret
        signed["RequestTime"] = request_time
        signed["Sign"] = generate_sdms_sign(
            signed,
            customer_code=self.credentials.customer_code,
            customer_secret=self.credentials.customer_secret,
            request_time=request_time,
        )
        return signed

    async def _post(self, path: str, payload: dict[str, Any], *, creates_order: bool = False) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}{path}",
                    headers={"Content-Type": "application/json"},
                    json=self.signed_payload(payload),
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise SdmsApiError(f"SDMS 网络请求失败：{exc}", uncertain=creates_order) from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            raise SdmsApiError(
                f"SDMS 返回了无法解析的响应（HTTP {response.status_code}）",
                uncertain=creates_order and response.status_code < 500,
            ) from exc
        if not isinstance(response_json, dict):
            raise SdmsApiError("SDMS 返回格式无效", uncertain=creates_order, response_json={})
        if response.status_code >= 400:
            raise SdmsApiError(
                f"SDMS HTTP {response.status_code}：{_api_message(response_json)}",
                uncertain=creates_order and response.status_code >= 500,
                response_json=response_json,
            )
        if not _api_success(response_json):
            raise SdmsApiError(_api_message(response_json), response_json=response_json)
        return response_json

    def _base_payload(self, warehouse_code: str) -> dict[str, Any]:
        return {
            "AppId": self.credentials.app_id,
            "WarehouseCode": warehouse_code,
            "CustomerCode": self.credentials.customer_code,
        }

    async def query_warehouses(self, warehouse_code: str) -> list[dict[str, Any]]:
        response = await self._post(SDMS_QUERY_WAREHOUSE_PATH, self._base_payload(warehouse_code))
        value = response.get("Value") if isinstance(response.get("Value"), dict) else {}
        return [item for item in value.get("List") or [] if isinstance(item, dict)]

    async def query_channels(self, warehouse_code: str) -> list[dict[str, Any]]:
        response = await self._post(SDMS_QUERY_CHANNEL_PATH, self._base_payload(warehouse_code))
        value = response.get("Value") if isinstance(response.get("Value"), dict) else {}
        return [item for item in value.get("List") or [] if isinstance(item, dict)]

    async def query_skus(self, warehouse_code: str, sku_codes: Iterable[str]) -> set[str]:
        requested = list(dict.fromkeys(_clean_text(item) for item in sku_codes if _clean_text(item)))
        if not requested:
            return set()
        found: set[str] = set()
        for offset in range(0, len(requested), 100):
            batch = requested[offset : offset + 100]
            payload = {
                **self._base_payload(warehouse_code),
                "PageRequest": {"Index": 1, "Size": max(10, len(batch))},
                "SkuCode": batch,
            }
            response = await self._post(SDMS_QUERY_SKU_PATH, payload)
            value = response.get("Value") if isinstance(response.get("Value"), dict) else {}
            for item in value.get("List") or []:
                if (
                    isinstance(item, dict)
                    and item.get("IsEnable") in (None, "", 1, "1")
                    and _clean_text(item.get("SkuCode"))
                ):
                    found.add(_clean_text(item.get("SkuCode")))
        return found

    async def query_sku_catalog(self, warehouse_code: str) -> list[dict[str, Any]]:
        catalog: list[dict[str, Any]] = []
        page_index = 1
        page_size = 200
        while True:
            payload = {
                **self._base_payload(warehouse_code),
                "PageRequest": {"Index": page_index, "Size": page_size},
            }
            response = await self._post(SDMS_QUERY_SKU_PATH, payload)
            value = response.get("Value") if isinstance(response.get("Value"), dict) else {}
            items = [item for item in value.get("List") or [] if isinstance(item, dict)]
            catalog.extend(items)
            pagination = value.get("Pagination") if isinstance(value.get("Pagination"), dict) else {}
            try:
                total = int(pagination.get("Total") or len(catalog))
            except (TypeError, ValueError):
                total = len(catalog)
            if not items or len(catalog) >= total:
                break
            page_index += 1
        return catalog

    async def resolve_sku_codes(
        self,
        warehouse_code: str,
        identifiers: Iterable[str],
        *,
        lookup_names: dict[str, str] | None = None,
    ) -> dict[str, str]:
        requested = list(dict.fromkeys(_clean_text(item) for item in identifiers if _clean_text(item)))
        if not requested:
            return {}
        direct = await self.query_skus(warehouse_code, requested)
        resolved = {item.casefold(): item for item in direct}
        missing = [item for item in requested if item.casefold() not in resolved]
        if not missing:
            return resolved
        catalog = await self.query_sku_catalog(warehouse_code)
        names: dict[str, list[str]] = defaultdict(list)
        for item in catalog:
            sku_code = _clean_text(item.get("SkuCode"))
            if not sku_code or item.get("IsEnable") not in (None, "", 1, "1"):
                continue
            for identifier in (sku_code, _clean_text(item.get("ProductCode"))):
                if identifier:
                    resolved.setdefault(identifier.casefold(), sku_code)
            normalized_name = _normalized_product_name(item.get("ProductName"))
            if normalized_name and sku_code not in names[normalized_name]:
                names[normalized_name].append(sku_code)
        for identifier in missing:
            lookup_name = (lookup_names or {}).get(identifier.casefold(), "")
            candidates = names.get(_normalized_product_name(lookup_name), [])
            if len(candidates) == 1:
                resolved[identifier.casefold()] = candidates[0]
        return resolved

    async def create_draft(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        response = await self._post(SDMS_CREATE_DRAFT_PATH, payload, creates_order=True)
        value = response.get("Value") if isinstance(response.get("Value"), dict) else {}
        provider_order_no = _clean_text(value.get("Data"))
        if not provider_order_no:
            raise SdmsApiError("SDMS 返回成功但缺少物流商订单号", uncertain=True, response_json=response)
        return provider_order_no, response

    async def cancel_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        cancellation = dict(payload)
        cancellation["Mode"] = 3
        return await self._post(SDMS_CREATE_DRAFT_PATH, cancellation)

    async def delete_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        deletion = dict(payload)
        deletion["Mode"] = 4
        return await self._post(SDMS_CREATE_DRAFT_PATH, deletion)

    async def query_sku_tracking(self, warehouse_code: str, order_no: str) -> dict[str, Any]:
        return await self._post(
            SDMS_QUERY_SKU_TRACKING_PATH,
            {
                **self._base_payload(warehouse_code),
                "OrderNO": _clean_text(order_no),
            },
        )


def _credentials_from_dict(credentials: dict[str, Any]) -> SdmsCredentials:
    return SdmsCredentials(
        app_id=_clean_text(credentials.get("app_id")),
        customer_code=_clean_text(credentials.get("customer_code")),
        customer_secret=_clean_text(credentials.get("customer_secret")),
    )


def load_bsi_authorization(db: Session) -> SdmsAuthorization | None:
    row = db.scalar(
        select(LogisticsAuthorization)
        .where(
            LogisticsAuthorization.carrier_code == BSI_CARRIER_CODE,
            LogisticsAuthorization.enabled == True,
        )
        .order_by(LogisticsAuthorization.id.asc())
        .limit(1)
    )
    if not row or not row.encrypted_credentials:
        return None
    credentials = get_credential_manager().decrypt_credentials(row.encrypted_credentials)
    return SdmsAuthorization(row=row, credentials=_credentials_from_dict(credentials), config=dict(row.config_json or {}))


def _channel_id(item: dict[str, Any]) -> int | None:
    try:
        return int(item.get("ChannelId"))
    except (TypeError, ValueError):
        return None


def _channel_name(item: dict[str, Any]) -> str:
    return _clean_text(item.get("AlphaCode") or item.get("ChannelNameEn") or item.get("ChannelNameZh"))


def _find_channel(
    channels: list[dict[str, Any]],
    *,
    configured_id: Any,
    configured_name: Any,
    fallback_markers: tuple[str, ...],
) -> dict[str, Any] | None:
    try:
        wanted_id = int(configured_id)
    except (TypeError, ValueError):
        wanted_id = None
    if wanted_id is not None:
        matched = next((item for item in channels if _channel_id(item) == wanted_id), None)
        if matched:
            return matched
    wanted_name = _clean_text(configured_name).casefold()
    if wanted_name:
        matched = next(
            (
                item
                for item in channels
                if wanted_name
                in " ".join(
                    _clean_text(item.get(key)).casefold()
                    for key in ("ChannelNameZh", "ChannelNameEn", "AlphaCode")
                )
            ),
            None,
        )
        if matched:
            return matched
    for item in channels:
        haystack = " ".join(
            _clean_text(item.get(key)).casefold()
            for key in ("ChannelNameZh", "ChannelNameEn", "AlphaCode")
        )
        if any(marker.casefold() in haystack for marker in fallback_markers):
            return item
    return None


def refresh_bsi_channel_config(channels: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    refreshed = dict(config)
    poland = _find_channel(
        channels,
        configured_id=config.get("poland_channel_id", 1061),
        configured_name=config.get("poland_channel_name"),
        fallback_markers=("波兰", "poland"),
    )
    pan_eu = _find_channel(
        channels,
        configured_id=config.get("pan_eu_channel_id", 3102),
        configured_name=config.get("pan_eu_channel_name"),
        fallback_markers=("泛欧", "pan-eu", "pan eu"),
    )
    if poland and _channel_id(poland) is not None:
        refreshed["poland_channel_id"] = _channel_id(poland)
        refreshed["poland_channel_name"] = _channel_name(poland)
    if pan_eu and _channel_id(pan_eu) is not None:
        refreshed["pan_eu_channel_id"] = _channel_id(pan_eu)
        refreshed["pan_eu_channel_name"] = _channel_name(pan_eu)
    return refreshed


async def verify_bsi_authorization(
    credentials: dict[str, Any],
    config: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    parsed = _credentials_from_dict(credentials)
    missing_credentials = [
        key
        for key, value in {
            "app_id": parsed.app_id,
            "customer_code": parsed.customer_code,
            "customer_secret": parsed.customer_secret,
        }.items()
        if not value
    ]
    warehouse_code = _clean_text(config.get("warehouse_code"))
    callback_url = _clean_text(config.get("callback_url"))
    missing_config = [key for key, value in {"warehouse_code": warehouse_code, "callback_url": callback_url}.items() if not value]
    if missing_credentials or missing_config:
        missing = missing_credentials + missing_config
        return False, f"缺少授权或下单配置：{', '.join(missing)}", dict(config)

    client = SdmsClient(
        parsed,
        base_url=_clean_text(config.get("base_url")) or SDMS_DEFAULT_BASE_URL,
        timeout_seconds=float(config.get("timeout_seconds") or 30),
        include_customer_secret=bool(config.get("include_customer_secret", False)),
    )
    try:
        warehouses = await client.query_warehouses(warehouse_code)
        visible_codes = {_clean_text(item.get("WarehouseCode")).casefold() for item in warehouses}
        if warehouse_code.casefold() not in visible_codes:
            return False, f"SDMS 授权中未找到仓库 {warehouse_code}", dict(config)
        channels = await client.query_channels(warehouse_code)
        refreshed = refresh_bsi_channel_config(channels, config)
        missing_roles = [
            label
            for key, label in (("poland_channel_id", "波兰渠道"), ("pan_eu_channel_id", "泛欧预付渠道"))
            if not refreshed.get(key)
        ]
        if missing_roles:
            return False, f"SDMS 授权中未找到：{', '.join(missing_roles)}", refreshed
        return True, f"SDMS 授权有效，仓库 {warehouse_code}，可见渠道 {len(channels)} 个", refreshed
    except SdmsApiError as exc:
        return False, f"SDMS 授权校验失败：{exc}", dict(config)


def _transaction_id(row: Order) -> str:
    payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    return _clean_text(payload.get("transactionId") or payload.get("transaction_id"))


def _platform_code(row: Order) -> str:
    return _clean_text(getattr(row, "platform", None)).lower()


def _order_number(row: Order) -> str:
    return _clean_text(getattr(row, "platform_order_no", None) or getattr(row, "platform_order_id", None))


def bsi_customer_order_no(rows: Iterable[Order]) -> str:
    """Return the single platform order number suitable for BSI's customer number."""
    numbers = {_order_number(row) for row in rows}
    numbers.discard("")
    if not numbers:
        raise ValueError("订单缺少平台订单编号，无法生成 BSI 客户订单号")
    if len(numbers) > 1:
        raise ValueError("同一 BSI 下单分组包含多个订单编号，无法安全生成单一 BSI 客户订单号")
    return next(iter(numbers))


def group_bsi_orders(rows: Iterable[Order]) -> list[tuple[str, list[Order]]]:
    grouped: dict[str, list[Order]] = defaultdict(list)
    missing_index = 0
    for row in rows:
        platform = _platform_code(row)
        if platform in JOOM_PLATFORM_CODES:
            transaction_id = _transaction_id(row)
            if not transaction_id:
                missing_index += 1
                transaction_id = f"__missing_joom_transaction__:{missing_index}:{getattr(row, 'id', 0)}"
            grouped[transaction_id].append(row)
            continue
        order_number = _order_number(row)
        if not order_number:
            missing_index += 1
            order_number = f"__missing_platform_order__:{missing_index}:{getattr(row, 'id', 0)}"
        grouped[f"{platform}:{_clean_text(getattr(row, 'account_id', None))}:{order_number}"].append(row)
    return list(grouped.items())


def _payload_with_best_address(row: Order) -> dict[str, Any]:
    raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    latest = row.last_api_payload if isinstance(getattr(row, "last_api_payload", None), dict) else {}
    raw_address = raw_payload.get("shippingAddress") if isinstance(raw_payload.get("shippingAddress"), dict) else {}
    latest_address = latest.get("shippingAddress") if isinstance(latest.get("shippingAddress"), dict) else {}
    return latest if len([value for value in latest_address.values() if value]) > len([value for value in raw_address.values() if value]) else raw_payload


def _shipping_address(row: Order) -> dict[str, Any]:
    payload = _payload_with_best_address(row)
    value = payload.get("shippingAddress") if isinstance(payload.get("shippingAddress"), dict) else {}
    return value


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _allegro_payload_with_best_address(row: Order) -> dict[str, Any]:
    raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    latest_payload = row.last_api_payload if isinstance(getattr(row, "last_api_payload", None), dict) else {}

    def address_count(payload: dict[str, Any]) -> int:
        delivery = payload.get("delivery") if isinstance(payload.get("delivery"), dict) else {}
        address = delivery.get("address") if isinstance(delivery.get("address"), dict) else {}
        return sum(1 for value in address.values() if _clean_text(value))

    return latest_payload if address_count(latest_payload) > address_count(raw_payload) else raw_payload


def build_allegro_bsi_delivery_info(row: Order) -> dict[str, Any]:
    payload = _allegro_payload_with_best_address(row)
    raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    delivery = payload.get("delivery") if isinstance(payload.get("delivery"), dict) else {}
    address = delivery.get("address") if isinstance(delivery.get("address"), dict) else {}
    shipping = payload.get("shipping") if isinstance(payload.get("shipping"), dict) else {}
    receiver = shipping.get("receiver_address") if isinstance(shipping.get("receiver_address"), dict) else {}
    buyer = payload.get("buyer") if isinstance(payload.get("buyer"), dict) else {}
    raw_buyer = raw_payload.get("buyer") if isinstance(raw_payload.get("buyer"), dict) else {}

    full_name = " ".join(
        value
        for value in (_first_text(address.get("firstName"), address.get("first_name")), _first_text(address.get("lastName"), address.get("last_name")))
        if value
    )
    city = _first_text(address.get("city"), receiver.get("city"))
    return {
        "ReceiverName": _first_text(address.get("name"), full_name, address.get("companyName"), receiver.get("name"), buyer.get("name"), raw_buyer.get("name")),
        "CountryCode": _first_text(
            address.get("countryCode"),
            address.get("country_code"),
            receiver.get("countryCode"),
            receiver.get("country_code"),
            receiver.get("country"),
            row.country_code,
        ).upper(),
        "ProvinceName": _first_text(address.get("province"), address.get("state"), city),
        "CityName": city,
        "AddressLineOne": _first_text(
            address.get("street"),
            address.get("streetAddress1"),
            address.get("addressLine1"),
            receiver.get("street"),
            receiver.get("street1"),
        ),
        "AddressLineTwo": _first_text(
            address.get("street2"),
            address.get("streetAddress2"),
            address.get("addressLine2"),
            receiver.get("street2"),
        ),
        "ReceiverPostcode": _first_text(
            address.get("zipCode"),
            address.get("postalCode"),
            address.get("postcode"),
            receiver.get("zipCode"),
            receiver.get("postcode"),
        ),
        "ReceiverPhone": _first_text(
            address.get("phoneNumber"),
            address.get("phone"),
            receiver.get("phoneNumber"),
            receiver.get("phone"),
        ),
        "ReceiverEmail": _first_text(address.get("email"), receiver.get("email"), buyer.get("email"), raw_buyer.get("email")),
        "BusinessMode": 1,
        "LabelObtainMethod": 1,
        "ShippingMethod": 1,
    }


def build_bsi_delivery_info(row: Order) -> dict[str, Any]:
    if _platform_code(row) == "allegro":
        return build_allegro_bsi_delivery_info(row)
    address = _shipping_address(row)
    city = _clean_text(address.get("city"))
    street = _clean_text(address.get("streetAddress1") or address.get("street"))
    if not street:
        street = " ".join(
            value
            for value in (
                _clean_text(address.get("streetName")),
                _clean_text(address.get("houseNumber")),
                _clean_text(address.get("flatNumber") or address.get("apartmentNumber")),
            )
            if value
        )
    return {
        "ReceiverName": _clean_text(address.get("name")),
        "CountryCode": _clean_text(address.get("country") or row.country_code).upper(),
        "ProvinceName": _clean_text(address.get("state") or address.get("province") or city),
        "CityName": city,
        "AddressLineOne": street,
        "AddressLineTwo": _clean_text(address.get("streetAddress2") or address.get("addressLine2")),
        "ReceiverPostcode": _clean_text(address.get("zipCode") or address.get("postalCode")),
        "ReceiverPhone": _clean_text(address.get("phoneNumber") or address.get("phone")),
        "ReceiverEmail": _clean_text(address.get("email")),
        "BusinessMode": 1,
        "LabelObtainMethod": 1,
        "ShippingMethod": 1,
    }


def missing_bsi_delivery_fields(delivery_info: dict[str, Any]) -> list[str]:
    required = (
        "ReceiverName",
        "CountryCode",
        "ProvinceName",
        "CityName",
        "AddressLineOne",
        "ReceiverPostcode",
        "ReceiverPhone",
    )
    return [key for key in required if not _clean_text(delivery_info.get(key))]


def detect_bsi_address_anomaly(delivery_info: dict[str, Any]) -> BsiAddressAnomaly | None:
    address = unicodedata.normalize("NFKC", _clean_text(delivery_info.get("AddressLineOne")))
    normalized = " ".join(address.split())
    if not normalized:
        return None
    compact = "".join(normalized.split())
    if compact.isdecimal():
        code = "numeric_only"
        reason = "收货地址为纯数字"
    elif len(normalized.split()) == 1:
        code = "single_word"
        reason = "收货地址只有一个单词"
    else:
        return None
    fingerprint = hashlib.sha256(f"{code}:{normalized.casefold()}".encode("utf-8")).hexdigest()
    return BsiAddressAnomaly(code, reason, normalized, fingerprint)


def build_bsi_address_anomaly_email(
    rows: Iterable[Order],
    customer_order_no: str,
    delivery_info: dict[str, Any],
    anomaly: BsiAddressAnomaly,
    *,
    bsi_result: str,
    provider_order_no: str = "",
) -> tuple[str, str]:
    group_rows = list(rows)
    first = group_rows[0] if group_rows else None
    order_number = _clean_text(customer_order_no) or (_order_number(first) if first is not None else "未知")
    subject = f"BSI收货地址异常：{order_number}订单收货地址异常"
    body = "\n".join(
        (
            "检测到 BSI 订单收货地址异常。",
            "",
            f"异常原因：{anomaly.reason}",
            f"BSI提交结果：{_clean_text(bsi_result) or '未知'}",
            f"BSI草稿单号：{_clean_text(provider_order_no) or '未生成'}",
            f"平台：{_clean_text(getattr(first, 'platform', None)) or '-'}",
            f"店铺：{_clean_text(getattr(first, 'shop_name', None) or getattr(first, 'account_id', None)) or '-'}",
            f"平台订单号：{order_number}",
            f"系统订单ID：{', '.join(str(getattr(row, 'id', '')) for row in group_rows) or '-'}",
            "",
            f"收件人：{_clean_text(delivery_info.get('ReceiverName')) or '-'}",
            f"国家：{_clean_text(delivery_info.get('CountryCode')) or '-'}",
            f"省/州：{_clean_text(delivery_info.get('ProvinceName')) or '-'}",
            f"城市：{_clean_text(delivery_info.get('CityName')) or '-'}",
            f"地址一：{_clean_text(delivery_info.get('AddressLineOne')) or '-'}",
            f"地址二：{_clean_text(delivery_info.get('AddressLineTwo')) or '-'}",
            f"邮编：{_clean_text(delivery_info.get('ReceiverPostcode')) or '-'}",
            f"电话：{_clean_text(delivery_info.get('ReceiverPhone')) or '-'}",
            f"邮箱：{_clean_text(delivery_info.get('ReceiverEmail')) or '-'}",
        )
    )
    return subject, body


def _bsi_address_alert_event_key(order_id: int, fingerprint: str, status: str) -> str:
    return f"system:{order_id}:{BSI_ADDRESS_ALERT_OPERATION_TYPE}:{status}:{fingerprint[:32]}"[:180]


def send_bsi_address_anomaly_alert(
    db: Session,
    rows: Iterable[Order],
    customer_order_no: str,
    delivery_info: dict[str, Any],
    *,
    bsi_result: str,
    provider_order_no: str = "",
) -> tuple[bool, str]:
    group_rows = list(rows)
    anomaly = detect_bsi_address_anomaly(delivery_info)
    if not anomaly or not group_rows:
        return False, "地址正常，无需发送邮件"

    sent_keys = [
        _bsi_address_alert_event_key(int(row.id), anomaly.fingerprint, "sent")
        for row in group_rows
        if getattr(row, "id", None) is not None
    ]
    if sent_keys and hasattr(db, "scalar"):
        try:
            existing = db.scalar(
                select(OrderOperationLog.id)
                .where(OrderOperationLog.event_key.in_(sent_keys))
                .limit(1)
            )
        except Exception as exc:
            logger.exception("Unable to check BSI address alert history for %s", customer_order_no)
            if hasattr(db, "rollback"):
                db.rollback()
            return False, f"无法检查地址异常邮件发送记录：{str(exc).strip() or exc.__class__.__name__}"
        if existing:
            return False, "地址异常邮件已发送，跳过重复通知"

    subject, body = build_bsi_address_anomaly_email(
        group_rows,
        customer_order_no,
        delivery_info,
        anomaly,
        bsi_result=bsi_result,
        provider_order_no=provider_order_no,
    )
    recipient_text = ""
    try:
        email_setting = get_email_setting(db)
        recipients = notification_recipients_for(email_setting, EMAIL_NOTIFICATION_BSI_ADDRESS_ANOMALY)
        recipient_text = ", ".join(recipients)
        if not recipients:
            raise RuntimeError("未配置 BSI 收货地址异常的邮件收件人")
        send_email(email_setting, recipients, subject, body)
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        logger.exception("Unable to send BSI address anomaly email for %s", customer_order_no)
        try:
            add_order_operation_logs(
                db,
                group_rows,
                operation_type=BSI_ADDRESS_ALERT_OPERATION_TYPE,
                operation_attribute="BSI收货地址异常邮件发送失败",
                description=lambda order: (
                    f"BSI订单 {_order_number(order) or customer_order_no} {anomaly.reason}，"
                    f"异常邮件发送失败：{message[:500]}"
                ),
                operator=SYSTEM_OPERATOR,
                source=ORDER_LOG_SYSTEM_SOURCE,
                event_key=lambda order: _bsi_address_alert_event_key(order.id, anomaly.fingerprint, "failed"),
                extra={
                    "address_anomaly": anomaly.code,
                    "address_fingerprint": anomaly.fingerprint,
                    "recipient": recipient_text,
                    "provider_order_no": provider_order_no,
                    "bsi_result": bsi_result,
                },
            )
            if hasattr(db, "commit"):
                db.commit()
        except Exception:
            logger.exception("Unable to record BSI address alert failure for %s", customer_order_no)
            if hasattr(db, "rollback"):
                db.rollback()
        return False, f"地址异常邮件发送失败：{message}"

    try:
        add_order_operation_logs(
            db,
            group_rows,
            operation_type=BSI_ADDRESS_ALERT_OPERATION_TYPE,
            operation_attribute="发送BSI收货地址异常邮件",
            description=lambda order: (
                f"BSI订单 {_order_number(order) or customer_order_no} {anomaly.reason}，"
                f"异常邮件已发送至 {recipient_text}"
            ),
            operator=SYSTEM_OPERATOR,
            source=ORDER_LOG_SYSTEM_SOURCE,
            event_key=lambda order: _bsi_address_alert_event_key(order.id, anomaly.fingerprint, "sent"),
            extra={
                "address_anomaly": anomaly.code,
                "address_fingerprint": anomaly.fingerprint,
                "recipient": recipient_text,
                "provider_order_no": provider_order_no,
                "bsi_result": bsi_result,
            },
        )
        if hasattr(db, "commit"):
            db.commit()
    except Exception:
        logger.exception("Unable to record successful BSI address alert for %s", customer_order_no)
        if hasattr(db, "rollback"):
            db.rollback()
    return True, "地址异常邮件已发送"


async def _refresh_missing_bsi_payloads(db: Session, rows: list[Order]) -> None:
    missing_rows = [row for row in rows if missing_bsi_delivery_fields(build_bsi_delivery_info(row))]
    if not missing_rows:
        return
    from .sync_engine import _connector_for_account

    grouped: dict[tuple[str, str], list[Order]] = defaultdict(list)
    for row in missing_rows:
        grouped[(row.platform, row.account_id)].append(row)
    for (platform, account_id), account_rows in grouped.items():
        try:
            connector = _connector_for_account(db, platform, account_id)
            order_ids = list(dict.fromkeys(_clean_text(row.platform_order_id) for row in account_rows if row.platform_order_id))
            updates = await connector.fetch_order_status_updates(order_ids)
            update_map = {}
            for update in updates:
                for key in (
                    _clean_text(update.platform_order_id),
                    _clean_text(update.platform_order_no),
                    _clean_text(update.posting_number),
                ):
                    if key:
                        update_map[key] = update
            for row in account_rows:
                update = next(
                    (
                        update_map.get(key)
                        for key in (_order_number(row), _clean_text(row.posting_number))
                        if update_map.get(key)
                    ),
                    None,
                )
                if update and isinstance(update.raw_payload, dict):
                    row.last_api_payload = update.raw_payload
        except Exception as exc:
            logger.warning("Unable to refresh BSI order payload for %s/%s: %s", platform, account_id, exc)


async def _refresh_missing_joom_payloads(db: Session, rows: list[Order]) -> None:
    """Backward-compatible alias for callers outside the shared BSI flow."""
    await _refresh_missing_bsi_payloads(db, rows)


def _platform_account_for_order(db: Session, row: Order) -> PlatformAccount | None:
    account_ids = list(dict.fromkeys(value for value in (_clean_text(row.account_id), _clean_text(row.shop_id)) if value))
    if not account_ids:
        return None
    return db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.platform == row.platform, PlatformAccount.account_id.in_(account_ids))
        .order_by(PlatformAccount.id.asc())
        .limit(1)
    )


def _normalized_product_name(value: Any) -> str:
    return "".join(char.casefold() for char in _clean_text(value) if char.isalnum())


def _mapped_bsi_product(db: Session, account: PlatformAccount, shop_sku: str) -> Product | None:
    shop_sku = _clean_text(shop_sku)
    if not shop_sku:
        return None
    stmt = (
        select(Product)
        .select_from(ProductShopMapping)
        .join(Product, Product.id == ProductShopMapping.product_id)
        .where(
            ProductShopMapping.shop_id == account.id,
            func.lower(func.trim(ProductShopMapping.shop_sku)) == shop_sku.casefold(),
            Product.enabled == True,
        )
        .order_by(ProductShopMapping.id.asc())
        .limit(1)
    )
    return db.scalar(stmt)


def _goods_for_rows(db: Session, rows: list[Order]) -> tuple[list[dict[str, Any]], list[str]]:
    quantities: dict[str, int] = defaultdict(int)
    lookup_names: dict[str, str] = {}
    missing: list[str] = []
    for row in rows:
        account = _platform_account_for_order(db, row)
        items = db.scalars(select(OrderItem).where(OrderItem.order_id == row.id).order_by(OrderItem.id.asc())).all()
        if not account:
            missing.append(f"订单 {row.id} 未找到店铺账号")
            continue
        for item in items:
            product = _mapped_bsi_product(db, account, item.sku)
            if not product:
                missing.append(f"订单 {row.id} 的 SKU {item.sku or '-'} 未配置产品映射")
                continue
            identifier = _clean_text(product.ean or product.product_code)
            if not identifier:
                missing.append(f"订单 {row.id} 的 SKU {item.sku or '-'} 对应产品缺少识别编码")
                continue
            quantities[identifier] += max(1, int(item.quantity or 1))
            lookup_names[identifier] = _clean_text(product.internal_name)
    goods = [
        {"SkuCode": identifier, "Quantity": quantity, "LookupName": lookup_names.get(identifier, "")}
        for identifier, quantity in sorted(quantities.items())
    ]
    if not goods and not missing:
        missing.append("订单没有可下单的商品明细")
    return goods, missing


def _channel_id_for_country(config: dict[str, Any], country_code: str) -> int:
    config_key = "poland_channel_id" if _clean_text(country_code).upper() == "PL" else "pan_eu_channel_id"
    try:
        channel_id = int(config.get(config_key))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"未配置有效的 {config_key}") from exc
    if channel_id <= 0:
        raise ValueError(f"未配置有效的 {config_key}")
    return channel_id


def build_bsi_draft_payload(
    prepared: PreparedBsiDraft,
    authorization: SdmsAuthorization,
) -> tuple[dict[str, Any], int]:
    channel_id = _channel_id_for_country(authorization.config, prepared.delivery_info.get("CountryCode"))
    delivery_info = dict(prepared.delivery_info)
    delivery_info["ChannelId"] = channel_id
    payload = {
        "AppId": authorization.credentials.app_id,
        "WarehouseCode": _clean_text(authorization.config.get("warehouse_code")),
        "CustomerCode": authorization.credentials.customer_code,
        "Mode": 1,
        "PoType": 1,
        "CustomerOrderNo": prepared.customer_order_no,
        "DeliveryInfo": delivery_info,
        "GoodsList": prepared.goods_list,
        "IsSplit": 2,
        "CallbackUrl": _clean_text(authorization.config.get("callback_url")),
        "Status": 2,
    }
    return payload, channel_id


def _submission_for(db: Session, row: Order, customer_order_no: str) -> LogisticsOrderSubmission | None:
    return db.scalar(
        select(LogisticsOrderSubmission)
        .where(
            LogisticsOrderSubmission.tenant_id == row.tenant_id,
            LogisticsOrderSubmission.carrier_code == BSI_CARRIER_CODE,
            LogisticsOrderSubmission.customer_order_no == customer_order_no,
        )
        .limit(1)
    )


def _upsert_submission(
    db: Session,
    prepared: PreparedBsiDraft,
    *,
    request_hash: str,
    channel_id: int,
) -> LogisticsOrderSubmission:
    first = prepared.rows[0]
    submission = _submission_for(db, first, prepared.customer_order_no)
    if submission is None:
        submission = LogisticsOrderSubmission(
            tenant_id=first.tenant_id,
            carrier_code=BSI_CARRIER_CODE,
            platform=first.platform,
            account_id=first.account_id or "",
            transaction_id=prepared.transaction_id,
            customer_order_no=prepared.customer_order_no,
            created_at=datetime.utcnow(),
        )
        db.add(submission)
    submission.local_order_ids = [row.id for row in prepared.rows]
    submission.request_hash = request_hash
    submission.channel_id = channel_id
    submission.updated_at = datetime.utcnow()
    return submission


def _write_bsi_order_no(rows: Iterable[Order], provider_order_no: str, submitted_at: datetime | None = None) -> None:
    order_no = _clean_text(provider_order_no)
    if not order_no:
        return
    for row in rows:
        row.bsi_order_no = order_no
        if submitted_at is not None:
            row.bsi_submitted_at = submitted_at
        elif not getattr(row, "bsi_submitted_at", None):
            row.bsi_submitted_at = datetime.utcnow()


def _stored_bsi_order_no(rows: Iterable[Order]) -> tuple[str, str]:
    """Return the already persisted BSI number, rejecting conflicting values."""
    order_numbers = {_clean_text(getattr(row, "bsi_order_no", None)) for row in rows}
    order_numbers.discard("")
    if not order_numbers:
        return "", ""
    if len(order_numbers) > 1:
        return "", "同一 BSI 下单分组已回写多个不同的 BSI 单号，为避免重复提交已暂停自动处理"
    return next(iter(order_numbers)), ""


async def process_bsi_drafts(db: Session, rows: list[Order]) -> BsiDraftProcessingResult:
    result = BsiDraftProcessingResult()
    grouped = group_bsi_orders(rows)
    pending_groups: list[tuple[str, list[Order], str]] = []
    for transaction_key, group_rows in grouped:
        if transaction_key.startswith("__missing_joom_transaction__:"):
            result.groups.append(BsiDraftGroupResult(group_rows, "failed", "Joom 订单缺少 transactionId，无法安全聚合下单"))
            continue
        if transaction_key.startswith("__missing_platform_order__:") or ":__missing_platform_order__:" in transaction_key:
            result.groups.append(BsiDraftGroupResult(group_rows, "failed", "订单缺少平台订单编号，无法安全创建 BSI 草稿"))
            continue
        try:
            customer_order_no = bsi_customer_order_no(group_rows)
        except ValueError as exc:
            result.groups.append(BsiDraftGroupResult(group_rows, "failed", str(exc)))
            continue

        stored_order_no, stored_order_error = _stored_bsi_order_no(group_rows)
        if stored_order_error:
            result.groups.append(BsiDraftGroupResult(group_rows, "uncertain", stored_order_error))
            continue
        if stored_order_no:
            _write_bsi_order_no(group_rows, stored_order_no)
            send_bsi_address_anomaly_alert(
                db,
                group_rows,
                customer_order_no,
                build_bsi_delivery_info(group_rows[0]),
                bsi_result="复用已有BSI草稿",
                provider_order_no=stored_order_no,
            )
            result.groups.append(
                BsiDraftGroupResult(
                    group_rows,
                    "succeeded",
                    "订单已回写 BSI 草稿单号，跳过重复提交",
                    provider_order_no=stored_order_no,
                    reused=True,
                )
            )
            continue

        existing = _submission_for(db, group_rows[0], customer_order_no)
        if existing and existing.status == "succeeded" and existing.provider_order_no:
            _write_bsi_order_no(group_rows, existing.provider_order_no, getattr(existing, "submitted_at", None))
            send_bsi_address_anomaly_alert(
                db,
                group_rows,
                customer_order_no,
                build_bsi_delivery_info(group_rows[0]),
                bsi_result="复用已有BSI草稿",
                provider_order_no=existing.provider_order_no,
            )
            result.groups.append(
                BsiDraftGroupResult(
                    group_rows,
                    "succeeded",
                    "BSI 备货草稿已存在，跳过重复提交",
                    provider_order_no=existing.provider_order_no,
                    reused=True,
                )
            )
            continue
        if existing and existing.status == "uncertain":
            send_bsi_address_anomaly_alert(
                db,
                group_rows,
                customer_order_no,
                build_bsi_delivery_info(group_rows[0]),
                bsi_result="BSI草稿提交结果不明确",
            )
            result.groups.append(
                BsiDraftGroupResult(
                    group_rows,
                    "uncertain",
                    "此前 BSI 下单结果不明确，为避免重复下单已暂停自动重试",
                )
            )
            continue
        if existing and existing.status == "pending":
            send_bsi_address_anomaly_alert(
                db,
                group_rows,
                customer_order_no,
                build_bsi_delivery_info(group_rows[0]),
                bsi_result="BSI草稿提交尚未确认",
            )
            result.groups.append(
                BsiDraftGroupResult(
                    group_rows,
                    "uncertain",
                    "此前 BSI 下单请求未完成确认，为避免重复下单已暂停自动重试",
                )
            )
            continue
        pending_groups.append((transaction_key, group_rows, customer_order_no))

    if not pending_groups:
        db.commit()
        return result

    authorization = load_bsi_authorization(db)
    if authorization is None:
        message = "未找到已启用的 BSI海外仓物流授权"
        result.groups.extend(BsiDraftGroupResult(group_rows, "failed", message) for _key, group_rows, _customer_no in pending_groups)
        db.commit()
        return result

    missing_credentials = [
        key
        for key, value in {
            "app_id": authorization.credentials.app_id,
            "customer_code": authorization.credentials.customer_code,
            "customer_secret": authorization.credentials.customer_secret,
        }.items()
        if not value
    ]
    warehouse_code = _clean_text(authorization.config.get("warehouse_code"))
    callback_url = _clean_text(authorization.config.get("callback_url"))
    if missing_credentials or not warehouse_code or not callback_url:
        missing = missing_credentials + (["warehouse_code"] if not warehouse_code else []) + (["callback_url"] if not callback_url else [])
        message = f"BSI海外仓授权配置不完整：{', '.join(missing)}"
        result.groups.extend(BsiDraftGroupResult(group_rows, "failed", message) for _key, group_rows, _customer_no in pending_groups)
        db.commit()
        return result
    if not bool(authorization.config.get("auto_create_drafts", False)):
        message = "BSI 备货草稿自动创建尚未启用，订单保留待处理"
        result.groups.extend(BsiDraftGroupResult(group_rows, "disabled", message) for _key, group_rows, _customer_no in pending_groups)
        db.commit()
        return result

    pending_rows = [row for _key, group_rows, _customer_no in pending_groups for row in group_rows]
    await _refresh_missing_bsi_payloads(db, pending_rows)
    prepared_groups: list[PreparedBsiDraft] = []
    for transaction_key, group_rows, customer_order_no in pending_groups:
        delivery_info = build_bsi_delivery_info(group_rows[0])
        missing_delivery = missing_bsi_delivery_fields(delivery_info)
        goods_list, missing_goods = _goods_for_rows(db, group_rows)
        if missing_delivery or missing_goods:
            details = []
            if missing_delivery:
                details.append(f"收件信息缺少 {', '.join(missing_delivery)}")
            details.extend(missing_goods)
            failure_message = "；".join(details)
            send_bsi_address_anomaly_alert(
                db,
                group_rows,
                customer_order_no,
                delivery_info,
                bsi_result=f"BSI草稿未提交：{failure_message}",
            )
            result.groups.append(BsiDraftGroupResult(group_rows, "failed", failure_message))
            continue
        prepared_groups.append(
            PreparedBsiDraft(
                transaction_id=transaction_key,
                customer_order_no=customer_order_no,
                rows=group_rows,
                delivery_info=delivery_info,
                goods_list=goods_list,
            )
        )

    client = SdmsClient(
        authorization.credentials,
        base_url=_clean_text(authorization.config.get("base_url")) or SDMS_DEFAULT_BASE_URL,
        timeout_seconds=float(authorization.config.get("timeout_seconds") or 30),
        include_customer_secret=bool(authorization.config.get("include_customer_secret", False)),
    )
    try:
        warehouses = await client.query_warehouses(warehouse_code)
        visible_codes = {_clean_text(item.get("WarehouseCode")).casefold() for item in warehouses}
        if warehouse_code.casefold() not in visible_codes:
            raise SdmsApiError(f"SDMS 授权中未找到仓库 {warehouse_code}")
        channels = await client.query_channels(warehouse_code)
        refreshed_config = refresh_bsi_channel_config(channels, authorization.config)
        authorization.config = refreshed_config
        authorization.row.config_json = refreshed_config
        all_skus = [item["SkuCode"] for group in prepared_groups for item in group.goods_list]
        lookup_names = {
            _clean_text(item["SkuCode"]).casefold(): _clean_text(item.get("LookupName"))
            for group in prepared_groups
            for item in group.goods_list
        }
        resolved_skus = await client.resolve_sku_codes(
            warehouse_code,
            all_skus,
            lookup_names=lookup_names,
        )
    except SdmsApiError as exc:
        message = f"BSI 下单前校验失败：{exc}"
        for group in prepared_groups:
            send_bsi_address_anomaly_alert(
                db,
                group.rows,
                group.customer_order_no,
                group.delivery_info,
                bsi_result=message,
            )
        result.groups.extend(BsiDraftGroupResult(group.rows, "failed", message) for group in prepared_groups)
        db.commit()
        return result

    for prepared in prepared_groups:
        missing_provider_skus = [item["SkuCode"] for item in prepared.goods_list if _clean_text(item["SkuCode"]).casefold() not in resolved_skus]
        if missing_provider_skus:
            failure_message = f"SDMS 仓库未找到 SKU：{', '.join(missing_provider_skus)}"
            send_bsi_address_anomaly_alert(
                db,
                prepared.rows,
                prepared.customer_order_no,
                prepared.delivery_info,
                bsi_result=f"BSI草稿未提交：{failure_message}",
            )
            result.groups.append(
                BsiDraftGroupResult(
                    prepared.rows,
                    "failed",
                    failure_message,
                )
            )
            continue

        provider_quantities: dict[str, int] = defaultdict(int)
        for item in prepared.goods_list:
            provider_sku = resolved_skus[_clean_text(item["SkuCode"]).casefold()]
            provider_quantities[provider_sku] += int(item["Quantity"])
        prepared.goods_list = [
            {"SkuCode": sku, "Quantity": quantity}
            for sku, quantity in sorted(provider_quantities.items())
        ]

        existing = _submission_for(db, prepared.rows[0], prepared.customer_order_no)
        if existing and existing.status == "succeeded" and existing.provider_order_no:
            _write_bsi_order_no(prepared.rows, existing.provider_order_no, getattr(existing, "submitted_at", None))
            send_bsi_address_anomaly_alert(
                db,
                prepared.rows,
                prepared.customer_order_no,
                prepared.delivery_info,
                bsi_result="复用已有BSI草稿",
                provider_order_no=existing.provider_order_no,
            )
            result.groups.append(
                BsiDraftGroupResult(
                    prepared.rows,
                    "succeeded",
                    "BSI 备货草稿已存在，跳过重复提交",
                    provider_order_no=existing.provider_order_no,
                    reused=True,
                )
            )
            db.commit()
            continue
        if existing and existing.status == "uncertain":
            send_bsi_address_anomaly_alert(
                db,
                prepared.rows,
                prepared.customer_order_no,
                prepared.delivery_info,
                bsi_result="BSI草稿提交结果不明确",
            )
            result.groups.append(
                BsiDraftGroupResult(
                    prepared.rows,
                    "uncertain",
                    "此前 BSI 下单结果不明确，为避免重复下单已暂停自动重试",
                )
            )
            continue
        if existing and existing.status == "pending":
            send_bsi_address_anomaly_alert(
                db,
                prepared.rows,
                prepared.customer_order_no,
                prepared.delivery_info,
                bsi_result="BSI草稿提交尚未确认",
            )
            result.groups.append(
                BsiDraftGroupResult(
                    prepared.rows,
                    "uncertain",
                    "此前 BSI 下单请求未完成确认，为避免重复下单已暂停自动重试",
                )
            )
            continue

        try:
            payload, channel_id = build_bsi_draft_payload(prepared, authorization)
        except ValueError as exc:
            send_bsi_address_anomaly_alert(
                db,
                prepared.rows,
                prepared.customer_order_no,
                prepared.delivery_info,
                bsi_result=f"BSI草稿未提交：{exc}",
            )
            result.groups.append(BsiDraftGroupResult(prepared.rows, "failed", str(exc)))
            continue
        submission = _upsert_submission(
            db,
            prepared,
            request_hash=sdms_request_fingerprint(payload),
            channel_id=channel_id,
        )
        submission.status = "pending"
        submission.attempts = int(submission.attempts or 0) + 1
        submission.error_message = ""
        # Persist the submission intent before the external request. A process
        # interruption must leave a record that blocks an automatic duplicate.
        db.commit()
        try:
            provider_order_no, response_json = await client.create_draft(payload)
            submission.status = "succeeded"
            submission.provider_order_no = provider_order_no
            submission.response_json = response_json
            submission.submitted_at = datetime.utcnow()
            submission.updated_at = datetime.utcnow()
            _write_bsi_order_no(prepared.rows, provider_order_no, submission.submitted_at)
            db.commit()
            send_bsi_address_anomaly_alert(
                db,
                prepared.rows,
                prepared.customer_order_no,
                prepared.delivery_info,
                bsi_result="BSI草稿创建成功",
                provider_order_no=provider_order_no,
            )
            result.groups.append(
                BsiDraftGroupResult(
                    prepared.rows,
                    "succeeded",
                    "BSI 备货订单草稿创建成功",
                    provider_order_no=provider_order_no,
                )
            )
        except SdmsApiError as exc:
            submission.status = "uncertain" if exc.uncertain else "failed"
            submission.error_message = str(exc)[:1000]
            submission.response_json = exc.response_json
            submission.updated_at = datetime.utcnow()
            db.commit()
            send_bsi_address_anomaly_alert(
                db,
                prepared.rows,
                prepared.customer_order_no,
                prepared.delivery_info,
                bsi_result=f"BSI草稿创建失败：{exc}",
            )
            result.groups.append(
                BsiDraftGroupResult(prepared.rows, submission.status, f"BSI 备货草稿创建失败：{exc}")
            )

    return result


async def process_joom_bsi_drafts(db: Session, rows: list[Order]) -> BsiDraftProcessingResult:
    """Backward-compatible entry point for existing callers."""
    return await process_bsi_drafts(db, rows)
