# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import hashlib
import hmac
import json
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from urllib.parse import urlencode

import httpx

from .base import LabelResult, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .pdf_preview import build_preview_pdf


def first_value(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def first_dict(*values) -> dict:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def as_list(value) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def deep_get(payload: dict, *paths: str):
    for path in paths:
        current: Any = payload
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                current = current[index] if 0 <= index < len(current) else None
            else:
                current = None
                break
        if current not in (None, "", [], {}):
            return current
    return None


def iso_utc(value: datetime) -> str:
    if value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat() + "Z"


def unix_seconds(value: datetime | None = None) -> int:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())


def hmac_sha256_hex(secret: str | bytes, message: str | bytes) -> str:
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    data = message.encode("utf-8") if isinstance(message, str) else message
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def normalize_money(value):
    if isinstance(value, dict):
        return first_value(value.get("amount"), value.get("value"), value.get("price"))
    return value


def normalize_currency(*values) -> str:
    for value in values:
        if isinstance(value, dict):
            value = first_value(value.get("currency"), value.get("currency_code"), value.get("currencyCode"), value.get("CurrencyCode"))
        if value not in (None, ""):
            return str(value)
    return ""


def normalize_fulfillment_type(value, default: str = "FBS") -> str:
    text = str(value or default).strip()
    return (text or default).upper().replace("-", "_").replace(" ", "_")[:40]


def response_data(value):
    if not isinstance(value, dict):
        return value
    data = value.get("data")
    result = value.get("result")
    response = value.get("response")
    payload = value.get("payload")
    return first_value(data, result, response, payload, value)


def extract_items(payload: dict, *keys: str) -> list[dict]:
    for key in keys:
        value = deep_get(payload, key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for nested_key in ("items", "orders", "order_list", "order_items", "products", "list"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
    for key in ("items", "orders", "order_list", "orderList", "data", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = extract_items(value)
            if nested:
                return nested
    return []


def order_identifier(payload: dict, *keys: str) -> str:
    return str(first_value(*(deep_get(payload, key) for key in keys), payload.get("id"), payload.get("order_id"), payload.get("orderId")) or "")


class MarketplaceApiError(RuntimeError):
    def __init__(self, platform: str, status_code: int, url: str, body: str) -> None:
        super().__init__(f"{platform} API HTTP {status_code} for {url}: {body}")
        self.platform = platform
        self.status_code = status_code
        self.url = url
        self.body = body


class LoggedHttpMixin:
    platform = ""

    def _account_id(self) -> str:
        return str(getattr(self, "account_id", "") or getattr(self, "seller_id", "") or "")

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        params: dict | None = None,
        json_body: dict | list | None = None,
        data: Any = None,
        timeout: float = 60,
        binary: bool = False,
    ) -> dict | bytes:
        from ..api_logger import log_api_call

        started = perf_counter()
        request_body = json_body if json_body is not None else data
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, headers=headers, params=params, json=json_body, data=data)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if binary or "application/pdf" in content_type or response.content.startswith(b"%PDF"):
                log_api_call(
                    platform=self.platform,
                    account_id=self._account_id(),
                    method=method,
                    url=str(response.request.url),
                    request_body=request_body,
                    response_status=response.status_code,
                    response_body={"_binary": True, "content_type": content_type, "content_length": len(response.content)},
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                return response.content
            try:
                body = response.json()
            except ValueError:
                body = {"text": response.text}
            log_api_call(
                platform=self.platform,
                account_id=self._account_id(),
                method=method,
                url=str(response.request.url),
                request_body=request_body,
                response_status=response.status_code,
                response_body=body,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return body
        except httpx.HTTPStatusError as exc:
            response = exc.response
            body = response.text[:4000] if response is not None else str(exc)[:4000]
            log_api_call(
                platform=self.platform,
                account_id=self._account_id(),
                method=method,
                url=str(response.request.url) if response is not None else url,
                request_body=request_body,
                response_status=response.status_code if response is not None else None,
                response_body=None,
                error_message=body,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise MarketplaceApiError(self.platform, response.status_code if response is not None else 0, url, body) from exc
        except Exception as exc:
            log_api_call(
                platform=self.platform,
                account_id=self._account_id(),
                method=method,
                url=url,
                request_body=request_body,
                response_status=None,
                response_body=None,
                error_message=str(exc)[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise


class DryRunFulfillmentMixin:
    settings: dict
    platform = ""

    def _dry_run(self) -> bool:
        return bool(self.settings.get("dry_run_fulfillment", False))

    def _preview_label(self, title: str, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        return LabelResult(
            content=build_preview_pdf(
                title,
                [
                    f"Order: {order.platform_order_no or order.platform_order_id}",
                    f"Posting: {order.posting_number or order.platform_order_id}",
                    f"Shipment: {shipment.platform_shipment_id}",
                    f"Tracking: {shipment.tracking_number}",
                ],
            )
        )


def product_payload(
    item: dict,
    *,
    sku_keys: tuple[str, ...],
    name_keys: tuple[str, ...],
    quantity_keys: tuple[str, ...],
    price_keys: tuple[str, ...],
    currency_keys: tuple[str, ...],
) -> dict:
    sku = first_value(*(deep_get(item, key) for key in sku_keys))
    name = first_value(*(deep_get(item, key) for key in name_keys))
    quantity = first_value(*(deep_get(item, key) for key in quantity_keys), 1)
    price = normalize_money(first_value(*(deep_get(item, key) for key in price_keys)))
    currency = normalize_currency(*(deep_get(item, key) for key in currency_keys))
    return {
        "offer_id": sku,
        "sku": sku,
        "name": name,
        "quantity": quantity or 1,
        "price": price,
        "currency_code": currency,
        "raw_payload": item,
    }


def label_from_platform_response(data: dict | bytes, *, default_content_type: str = "application/pdf") -> LabelResult:
    if isinstance(data, bytes):
        return LabelResult(content=data, content_type=default_content_type)
    if not isinstance(data, dict):
        raise RuntimeError(f"Label response is not binary or JSON: {data}")
    payload = response_data(data)
    if isinstance(payload, dict):
        for key in ("content", "content_base64", "file", "document", "pdf", "label", "label_base64", "shipping_document"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                try:
                    return LabelResult(content=bytes(value, "utf-8") if value.startswith("%PDF") else __import__("base64").b64decode(value))
                except Exception:
                    continue
        for path in (
            "Label.FileContents.Contents",
            "label.fileContents.contents",
            "FileContents.Contents",
            "fileContents.contents",
            "document.file",
            "shipping_document.file",
        ):
            value = deep_get(payload, path)
            if isinstance(value, str) and value:
                try:
                    return LabelResult(content=bytes(value, "utf-8") if value.startswith("%PDF") else __import__("base64").b64decode(value))
                except Exception:
                    continue
        url = first_value(payload.get("url"), payload.get("file_url"), payload.get("download_url"))
        if url:
            raise RuntimeError(f"Label response returned URL instead of content: {url}")
    raise RuntimeError(f"Label response did not contain printable content: {data}")


def compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def canonical_query(params: dict) -> str:
    cleaned = {key: value for key, value in params.items() if value not in (None, "")}
    return urlencode(sorted(cleaned.items()), doseq=True)
