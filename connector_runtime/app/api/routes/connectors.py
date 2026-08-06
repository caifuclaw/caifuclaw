import asyncio
import base64
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends

from ...adapters.base import LabelResult, NormalizedOrder, ShipmentResult
from ...factory import canonical_platform, connector_for
from ...security import require_internal_service_token
from ...schemas import (
    ConnectorError,
    ConnectorResponse,
    FetchOrdersRequest,
    LabelBatchRequest,
    LabelRequest,
    PlatformProductCatalogRequest,
    ProductInfoRequest,
    SearchOrdersRequest,
    ShipmentRequest,
    StatusUpdatesRequest,
    TrackingRegistrationRequest,
    TrafficRequest,
)


router = APIRouter(
    prefix="/api/v1/connectors",
    tags=["connectors"],
    dependencies=[Depends(require_internal_service_token)],
)
ADAPTER_VERSION = "1.0.0"
TRAFFIC_SYNC_TIMEOUT_SECONDS = {
    "allegro": 5 * 60,
    "joom_logistics": 15 * 60,
    "ozon": 30 * 60,
    "wildberries": 30 * 60,
    "mercadolibre": 130 * 60,
}
MIN_TRAFFIC_SYNC_TIMEOUT_SECONDS = 60
MAX_TRAFFIC_SYNC_TIMEOUT_SECONDS = 4 * 60 * 60


def _success(platform: str, data: Any) -> ConnectorResponse:
    return ConnectorResponse(
        ok=True,
        platform=canonical_platform(platform),
        adapter_version=ADAPTER_VERSION,
        data=data,
    )


def _failure(platform: str, exc: Exception) -> ConnectorResponse:
    code = "CONNECTOR_ERROR"
    retryable = False
    message = str(exc)
    lowered = message.lower()
    if "401" in message or "unauthorized" in lowered or "token" in lowered:
        code = "AUTH_EXPIRED"
    elif "invalid_argument" in lowered:
        code = "INVALID_ARGUMENT"
    elif (
        isinstance(exc, httpx.TransportError)
        or "timeout" in lowered
        or "temporar" in lowered
        or "429" in message
        or "rate" in lowered
        or "server disconnected" in lowered
        or "connection reset" in lowered
        or "connection aborted" in lowered
        or "connection refused" in lowered
    ):
        code = "TEMPORARY_PLATFORM_ERROR"
        retryable = True
    return ConnectorResponse(
        ok=False,
        platform=canonical_platform(platform),
        adapter_version=ADAPTER_VERSION,
        error=ConnectorError(code=code, message=message, retryable=retryable),
    )


def _traffic_sync_timeout_seconds(platform: str, payload: TrafficRequest) -> float:
    canonical = canonical_platform(platform)
    requested = payload.timeout_seconds
    if requested is None:
        requested = TRAFFIC_SYNC_TIMEOUT_SECONDS.get(canonical, 30 * 60)
    try:
        timeout = float(requested)
    except (TypeError, ValueError):
        timeout = float(TRAFFIC_SYNC_TIMEOUT_SECONDS.get(canonical, 30 * 60))
    return min(
        MAX_TRAFFIC_SYNC_TIMEOUT_SECONDS,
        max(MIN_TRAFFIC_SYNC_TIMEOUT_SECONDS, timeout),
    )


def _traffic_timeout_failure(platform: str, timeout_seconds: float) -> ConnectorResponse:
    minutes = max(1, round(timeout_seconds / 60))
    return ConnectorResponse(
        ok=False,
        platform=canonical_platform(platform),
        adapter_version=ADAPTER_VERSION,
        error=ConnectorError(
            code="TRAFFIC_SYNC_TIMEOUT",
            message=f"流量同步超过 {minutes} 分钟，已停止当前店铺任务",
            retryable=True,
        ),
    )


def _connector(platform: str, payload):
    settings = dict(payload.settings or {})
    if payload.account_id:
        settings["account_id"] = payload.account_id
    return connector_for(platform, payload.credentials or {}, settings)


def _dataclass_dict(value):
    if is_dataclass(value):
        return asdict(value)
    return value


def _parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _order_from_dict(value: dict) -> NormalizedOrder:
    return NormalizedOrder(
        platform_order_id=str(value.get("platform_order_id") or ""),
        platform_status=str(value.get("platform_status") or ""),
        raw_payload=value.get("raw_payload") if isinstance(value.get("raw_payload"), dict) else {},
        platform_order_no=str(value.get("platform_order_no") or ""),
        posting_number=str(value.get("posting_number") or ""),
        fulfillment_type=str(value.get("fulfillment_type") or "FBS"),
        is_overseas_warehouse=bool(value.get("is_overseas_warehouse", False)),
    )


def _shipment_from_dict(value: dict) -> ShipmentResult:
    return ShipmentResult(
        platform_shipment_id=str(value.get("platform_shipment_id") or ""),
        tracking_number=str(value.get("tracking_number") or ""),
        carrier=str(value.get("carrier") or ""),
        status=str(value.get("status") or "created"),
        raw_payload=value.get("raw_payload") if isinstance(value.get("raw_payload"), dict) else {},
    )


def _label_payload(label: LabelResult) -> dict:
    return {
        "content_base64": base64.b64encode(label.content).decode("ascii"),
        "content_type": label.content_type,
        "file_extension": label.file_extension,
        "raw_payload": label.raw_payload if isinstance(label.raw_payload, dict) else {},
    }


@router.post("/{platform}/orders/unprocessed", response_model=ConnectorResponse)
async def fetch_unprocessed_orders(platform: str, payload: FetchOrdersRequest) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        rows = await connector.fetch_unprocessed_orders(_parse_since(payload.since))
        return _success(platform, [_dataclass_dict(row) for row in rows])
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/orders/search", response_model=ConnectorResponse)
async def search_orders(platform: str, payload: SearchOrdersRequest) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        rows = await connector.fetch_orders_by_date_range(
            _parse_since(payload.start),
            _parse_since(payload.end),
            date_field=payload.date_field,
            status=payload.status,
            fulfillment_status=payload.fulfillment_status,
            limit=payload.limit,
            max_pages=payload.max_pages,
        )
        return _success(platform, [_dataclass_dict(row) for row in rows])
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/orders/status-updates", response_model=ConnectorResponse)
async def fetch_order_status_updates(platform: str, payload: StatusUpdatesRequest) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        rows = await connector.fetch_order_status_updates(payload.posting_numbers)
        return _success(platform, [_dataclass_dict(row) for row in rows])
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/traffic/fetch", response_model=ConnectorResponse)
async def fetch_traffic(platform: str, payload: TrafficRequest) -> ConnectorResponse:
    timeout_seconds = _traffic_sync_timeout_seconds(platform, payload)
    try:
        connector = _connector(platform, payload)
        async with asyncio.timeout(timeout_seconds):
            rows = await connector.fetch_traffic(
                _parse_since(payload.start),
                _parse_since(payload.end),
            )
        return _success(platform, rows)
    except TimeoutError:
        return _traffic_timeout_failure(platform, timeout_seconds)
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/products/info", response_model=ConnectorResponse)
async def get_products_by_offer_ids(platform: str, payload: ProductInfoRequest) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        result = await connector.get_products_by_offer_ids(payload.offer_ids)
        return _success(platform, result)
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/products/catalog", response_model=ConnectorResponse)
async def fetch_platform_product_catalog(
    platform: str,
    payload: PlatformProductCatalogRequest,
) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        result = await connector.fetch_platform_products(_parse_since(payload.since))
        return _success(platform, result)
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/shipments/create", response_model=ConnectorResponse)
async def create_platform_shipment(platform: str, payload: ShipmentRequest) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        result = await connector.create_platform_shipment(_order_from_dict(payload.order))
        return _success(platform, _dataclass_dict(result))
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/shipments/register-tracking", response_model=ConnectorResponse)
async def register_tracking_number(
    platform: str,
    payload: TrackingRegistrationRequest,
) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        result = await connector.register_tracking_number(
            _order_from_dict(payload.order),
            payload.tracking_number,
            payload.carrier,
        )
        return _success(platform, _dataclass_dict(result))
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/labels/fetch", response_model=ConnectorResponse)
async def fetch_label(platform: str, payload: LabelRequest) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        label = await connector.fetch_label(
            _shipment_from_dict(payload.shipment),
            _order_from_dict(payload.order),
        )
        return _success(platform, _label_payload(label))
    except Exception as exc:
        return _failure(platform, exc)


@router.post("/{platform}/labels/fetch-batch", response_model=ConnectorResponse)
async def fetch_label_batch(platform: str, payload: LabelBatchRequest) -> ConnectorResponse:
    try:
        connector = _connector(platform, payload)
        label = await connector.fetch_label_batch(
            [_order_from_dict(item) for item in payload.orders]
        )
        return _success(platform, _label_payload(label))
    except Exception as exc:
        return _failure(platform, exc)
