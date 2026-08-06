# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import asyncio
import base64
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from .connectors.base import LabelResult, NormalizedOrder, OrderStatusUpdate, ShipmentResult


TRAFFIC_SYNC_TIMEOUT_SECONDS = {
    "allegro": 5 * 60,
    "joom_logistics": 15 * 60,
    "ozon": 30 * 60,
    "wildberries": 30 * 60,
    "mercadolibre": 130 * 60,
}
MIN_TRAFFIC_SYNC_TIMEOUT_SECONDS = 60
MAX_TRAFFIC_SYNC_TIMEOUT_SECONDS = 4 * 60 * 60
TRAFFIC_RUNTIME_TIMEOUT_BUFFER_SECONDS = 60
TRAFFIC_RUNTIME_RETRY_ATTEMPTS = 5
TRAFFIC_RUNTIME_RETRY_MAX_DELAY_SECONDS = 10


class ConnectorRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ConnectorRuntimeClient:
    def __init__(
        self,
        *,
        runtime_url: str,
        platform: str,
        credentials: dict,
        settings: dict,
        account_id: str = "",
        internal_service_token: str = "",
    ) -> None:
        self.runtime_url = runtime_url.rstrip("/")
        self.platform = platform
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.account_id = account_id or str(self.settings.get("account_id") or "")
        self.internal_service_token = str(internal_service_token or "").strip()

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        data = await self._post(
            "orders/unprocessed",
            {"since": since.isoformat() if since else None},
            timeout=90,
        )
        return [self._order_from_dict(item) for item in data or []]

    async def fetch_orders_by_date_range(
        self,
        start: datetime,
        end: datetime | None = None,
        *,
        date_field: str = "lineItems.boughtAt",
        status: str = "",
        fulfillment_status: str = "",
        limit: int = 100,
        max_pages: int = 0,
    ) -> list[NormalizedOrder]:
        data = await self._post(
            "orders/search",
            {
                "start": start.isoformat(),
                "end": end.isoformat() if end else None,
                "date_field": date_field,
                "status": status,
                "fulfillment_status": fulfillment_status,
                "limit": limit,
                "max_pages": max_pages,
            },
            timeout=600,
        )
        return [self._order_from_dict(item) for item in data or []]

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        data = await self._post(
            "orders/status-updates",
            {"posting_numbers": posting_numbers},
            timeout=90,
        )
        return [self._status_update_from_dict(item) for item in data or []]

    async def fetch_traffic(self, start: datetime, end: datetime) -> list[dict]:
        timeout_seconds = self._traffic_sync_timeout_seconds()
        payload = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timeout_seconds": timeout_seconds,
        }
        last_error: Exception | None = None
        for attempt in range(TRAFFIC_RUNTIME_RETRY_ATTEMPTS):
            try:
                data = await self._post(
                    "traffic/fetch",
                    payload,
                    timeout=timeout_seconds + TRAFFIC_RUNTIME_TIMEOUT_BUFFER_SECONDS,
                )
                return [item for item in data or [] if isinstance(item, dict)]
            except httpx.TimeoutException as exc:
                minutes = max(1, round(timeout_seconds / 60))
                raise ConnectorRuntimeError(
                    "TRAFFIC_SYNC_TIMEOUT",
                    f"流量同步超过 {minutes} 分钟，已停止当前店铺任务",
                    retryable=True,
                ) from exc
            except (httpx.TransportError, ConnectorRuntimeError) as exc:
                if not self._is_retryable_traffic_runtime_error(exc):
                    raise
                last_error = exc
                if attempt + 1 >= TRAFFIC_RUNTIME_RETRY_ATTEMPTS:
                    break
                await asyncio.sleep(min(2**attempt, TRAFFIC_RUNTIME_RETRY_MAX_DELAY_SECONDS))

        raise ConnectorRuntimeError(
            "TEMPORARY_PLATFORM_ERROR",
            "连接器服务连接中断，已自动重试 5 次仍未恢复，请稍后重新同步",
            retryable=True,
        ) from last_error

    @staticmethod
    def _is_retryable_traffic_runtime_error(exc: Exception) -> bool:
        if isinstance(exc, httpx.TransportError):
            return True
        return isinstance(exc, ConnectorRuntimeError) and exc.retryable and exc.code != "TRAFFIC_SYNC_TIMEOUT"

    def _traffic_sync_timeout_seconds(self) -> float:
        default = TRAFFIC_SYNC_TIMEOUT_SECONDS.get(self.platform, 30 * 60)
        requested = self.settings.get("traffic_sync_timeout_seconds", default)
        try:
            timeout = float(requested)
        except (TypeError, ValueError):
            timeout = float(default)
        return min(MAX_TRAFFIC_SYNC_TIMEOUT_SECONDS, max(MIN_TRAFFIC_SYNC_TIMEOUT_SECONDS, timeout))

    async def get_products_by_offer_ids(self, offer_ids: list[str]) -> dict:
        data = await self._post("products/info", {"offer_ids": offer_ids or []}, timeout=120)
        return data if isinstance(data, dict) else {"items": []}

    async def fetch_platform_products(self, since: datetime | None = None) -> list[dict]:
        data = await self._post(
            "products/catalog",
            {"since": since.isoformat() if since else None},
            timeout=600,
        )
        return [item for item in data or [] if isinstance(item, dict)]

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        data = await self._post("shipments/create", {"order": self._payload_dict(order)}, timeout=90)
        return self._shipment_from_dict(data or {})

    async def register_tracking_number(
        self,
        order: NormalizedOrder,
        tracking_number: str,
        carrier: str = "",
    ) -> ShipmentResult:
        data = await self._post(
            "shipments/register-tracking",
            {
                "order": self._payload_dict(order),
                "tracking_number": str(tracking_number or "").strip(),
                "carrier": str(carrier or "").strip(),
            },
            timeout=90,
        )
        return self._shipment_from_dict(data or {})

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        data = await self._post(
            "labels/fetch",
            {"shipment": self._payload_dict(shipment), "order": self._payload_dict(order)},
            timeout=120,
        )
        return self._label_from_dict(data or {})

    async def fetch_label_batch(self, orders: list[NormalizedOrder]) -> LabelResult:
        data = await self._post(
            "labels/fetch-batch",
            {"orders": [self._payload_dict(order) for order in orders]},
            timeout=120,
        )
        return self._label_from_dict(data or {})

    async def _post(self, action: str, payload: dict, *, timeout: float) -> Any:
        body = {
            "credentials": self.credentials,
            "settings": self.settings,
            "account_id": self.account_id,
            **payload,
        }
        url = f"{self.runtime_url}/api/v1/connectors/{self.platform}/{action}"
        runtime_host = urlparse(self.runtime_url).hostname
        trust_env = runtime_host not in {"127.0.0.1", "localhost", "::1"}
        async with httpx.AsyncClient(timeout=timeout, trust_env=trust_env) as client:
            headers = {}
            if self.internal_service_token:
                headers["X-Internal-Service-Token"] = self.internal_service_token
            response = await client.post(url, json=body, headers=headers)
        if response.status_code >= 400:
            raise ConnectorRuntimeError("RUNTIME_HTTP_ERROR", f"Connector Runtime HTTP {response.status_code}: {response.text[:500]}", retryable=True)
        result = response.json()
        if not result.get("ok"):
            error = result.get("error") or {}
            raise ConnectorRuntimeError(
                str(error.get("code") or "CONNECTOR_ERROR"),
                str(error.get("message") or "Connector Runtime 调用失败"),
                retryable=bool(error.get("retryable")),
            )
        return result.get("data")

    @staticmethod
    def _payload_dict(value):
        if is_dataclass(value):
            return asdict(value)
        return value

    @staticmethod
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

    @staticmethod
    def _status_update_from_dict(value: dict) -> OrderStatusUpdate:
        return OrderStatusUpdate(
            posting_number=str(value.get("posting_number") or ""),
            platform_order_id=str(value.get("platform_order_id") or ""),
            platform_status=str(value.get("platform_status") or ""),
            platform_order_no=str(value.get("platform_order_no") or ""),
            shipment_tracking_number=str(value.get("shipment_tracking_number") or ""),
            handover_at=str(value.get("handover_at") or ""),
            raw_payload=value.get("raw_payload") if isinstance(value.get("raw_payload"), dict) else {},
        )

    @staticmethod
    def _shipment_from_dict(value: dict) -> ShipmentResult:
        return ShipmentResult(
            platform_shipment_id=str(value.get("platform_shipment_id") or ""),
            tracking_number=str(value.get("tracking_number") or ""),
            carrier=str(value.get("carrier") or ""),
            status=str(value.get("status") or "created"),
            raw_payload=value.get("raw_payload") if isinstance(value.get("raw_payload"), dict) else {},
        )

    @staticmethod
    def _label_from_dict(value: dict) -> LabelResult:
        content = base64.b64decode(value.get("content_base64") or "")
        return LabelResult(
            content=content,
            content_type=str(value.get("content_type") or "application/pdf"),
            file_extension=str(value.get("file_extension") or ".pdf"),
            raw_payload=value.get("raw_payload") if isinstance(value.get("raw_payload"), dict) else {},
        )
