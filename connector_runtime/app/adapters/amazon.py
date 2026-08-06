import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    canonical_query,
    deep_get,
    first_value,
    iso_utc,
    label_from_platform_response,
    product_payload,
    response_data,
)


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


class AmazonConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "amazon"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.lwa_client_id = str(self.credentials.get("lwa_client_id") or self.credentials.get("client_id") or "")
        self.lwa_client_secret = str(self.credentials.get("lwa_client_secret") or self.credentials.get("client_secret") or "")
        self.refresh_token = str(self.credentials.get("refresh_token") or "")
        self.access_token = str(self.credentials.get("access_token") or "")
        self.aws_access_key_id = str(self.credentials.get("aws_access_key_id") or "")
        self.aws_secret_access_key = str(self.credentials.get("aws_secret_access_key") or "")
        self.aws_session_token = str(self.credentials.get("aws_session_token") or "")
        self.seller_id = str(self.credentials.get("seller_id") or self.settings.get("account_id") or "")
        self.base_url = str(self.settings.get("base_url") or "https://sellingpartnerapi-na.amazon.com").rstrip("/")
        self.aws_region = str(self.settings.get("aws_region") or "us-east-1")
        self.account_id = str(self.settings.get("account_id") or self.seller_id)
        self._lwa_access_token = self.access_token

    async def _ensure_lwa_access_token(self) -> str:
        if self._lwa_access_token:
            return self._lwa_access_token
        if not (self.lwa_client_id and self.lwa_client_secret and self.refresh_token):
            raise ValueError("Amazon LWA client id, client secret and refresh token are required")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.lwa_client_id,
            "client_secret": self.lwa_client_secret,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.amazon.com/auth/o2/token", data=data)
            response.raise_for_status()
            payload = response.json()
        self._lwa_access_token = str(payload.get("access_token") or "")
        if not self._lwa_access_token:
            raise RuntimeError(f"Amazon LWA did not return access_token: {payload}")
        return self._lwa_access_token

    def _sigv4_headers(self, method: str, path: str, params: dict | None, body: bytes, access_token: str) -> dict:
        if not (self.aws_access_key_id and self.aws_secret_access_key):
            raise ValueError("Amazon AWS access key id and secret access key are required")
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        host = self.base_url.removeprefix("https://").removeprefix("http://")
        canonical_uri = quote(path, safe="/-_.~")
        canonical_querystring = canonical_query(params or {})
        payload_hash = hashlib.sha256(body).hexdigest()
        canonical_headers = f"host:{host}\nx-amz-access-token:{access_token}\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-access-token;x-amz-date"
        headers = {
            "host": host,
            "x-amz-access-token": access_token,
            "x-amz-date": amz_date,
        }
        if self.aws_session_token:
            canonical_headers += f"x-amz-security-token:{self.aws_session_token}\n"
            signed_headers += ";x-amz-security-token"
            headers["x-amz-security-token"] = self.aws_session_token
        canonical_request = "\n".join([method, canonical_uri, canonical_querystring, canonical_headers, signed_headers, payload_hash])
        credential_scope = f"{date_stamp}/{self.aws_region}/execute-api/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])
        signing_key = _sign(_sign(_sign(_sign(("AWS4" + self.aws_secret_access_key).encode("utf-8"), date_stamp), self.aws_region), "execute-api"), "aws4_request")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.aws_access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return headers

    async def _spapi_request(self, method: str, path: str, *, params: dict | None = None, json_body: dict | None = None, binary: bool = False):
        access_token = await self._ensure_lwa_access_token()
        body = b""
        if json_body is not None:
            import json

            body = json.dumps(json_body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = self._sigv4_headers(method, path, params, body, access_token)
        if json_body is not None:
            headers["content-type"] = "application/json"
        return await self._request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            params=params,
            data=body if json_body is not None else None,
            binary=binary,
            timeout=90,
        )

    async def _get_order_items(self, order_id: str) -> list[dict]:
        path = str(self.settings.get("order_items_path") or "/orders/v0/orders/{order_id}/orderItems").format(order_id=order_id)
        data = await self._spapi_request("GET", path)
        payload = response_data(data)
        if isinstance(payload, dict):
            return [item for item in as_list(first_value(payload.get("OrderItems"), payload.get("orderItems"), payload.get("items"))) if isinstance(item, dict)]
        return []

    async def _get_order_address(self, order_id: str) -> dict:
        if not bool(self.settings.get("use_restricted_data_token", False)):
            return {}
        path = str(self.settings.get("order_address_path") or f"/orders/v0/orders/{order_id}/address")
        path = path.format(order_id=order_id)
        try:
            data = await self._spapi_request("GET", path)
        except Exception:
            return {}
        payload = response_data(data)
        return payload if isinstance(payload, dict) else {}

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("AmazonOrderId"), order.get("amazonOrderId"), order.get("order_id"), order.get("id")) or "")
        if not order_id:
            return None
        items = [item for item in as_list(first_value(order.get("OrderItems"), order.get("orderItems"), order.get("items"))) if isinstance(item, dict)]
        products = [
            product_payload(
                item,
                sku_keys=("SellerSKU", "sellerSKU", "seller_sku", "sku"),
                name_keys=("Title", "title", "name"),
                quantity_keys=("QuantityOrdered", "quantityOrdered", "quantity"),
                price_keys=("ItemPrice.Amount", "itemPrice.Amount", "price.amount", "price"),
                currency_keys=("ItemPrice.CurrencyCode", "itemPrice.CurrencyCode", "price.currency", "currency"),
            )
            for item in items
        ]
        address = first_value(order.get("ShippingAddress"), order.get("shippingAddress"), order.get("address"), {})
        address = address if isinstance(address, dict) else {}
        raw_payload = {
            **order,
            "id": order_id,
            "site": first_value(order.get("MarketplaceId"), self.settings.get("marketplace_ids", [""])[0] if self.settings.get("marketplace_ids") else "", "amazon"),
            "created_at": first_value(order.get("PurchaseDate"), order.get("purchaseDate")),
            "order_date": first_value(order.get("PurchaseDate"), order.get("purchaseDate")),
            "payment_at": first_value(order.get("PurchaseDate"), order.get("purchaseDate"), order.get("LastUpdateDate")),
            "shipping_deadline_at": first_value(order.get("LatestShipDate"), order.get("latestShipDate")),
            "buyer_selected_logistics": first_value(order.get("ShipmentServiceLevelCategory"), order.get("ShipServiceLevel"), order.get("shipServiceLevel")),
            "country_code": first_value(address.get("CountryCode"), address.get("countryCode"), address.get("country_code")),
            "order_amount": first_value(deep_get(order, "OrderTotal.Amount"), deep_get(order, "orderTotal.Amount")),
            "currency_code": first_value(deep_get(order, "OrderTotal.CurrencyCode"), deep_get(order, "orderTotal.CurrencyCode"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": first_value(order.get("FulfillmentChannel"), order.get("fulfillmentChannel"), "FBS"),
        }
        fulfillment_type = "FBA" if str(raw_payload["fulfillment_type"]).upper() == "AFN" else "FBS"
        raw_payload["fulfillment_type"] = fulfillment_type
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=order_id,
            posting_number=order_id,
            platform_status=str(first_value(order.get("OrderStatus"), order.get("orderStatus"), order.get("status")) or ""),
            fulfillment_type=fulfillment_type,
            is_overseas_warehouse=fulfillment_type == "FBA",
            raw_payload=raw_payload,
        )

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        path = str(self.settings.get("orders_path") or "/orders/v0/orders")
        marketplace_ids = list(self.settings.get("marketplace_ids") or [])
        if not marketplace_ids:
            raise ValueError("Amazon settings.marketplace_ids is required")
        statuses = list(self.settings.get("pull_order_statuses") or ["Unshipped", "PartiallyShipped"])
        created_after = since or (datetime.now(timezone.utc) - timedelta(days=int(self.settings.get("lookback_days") or 7)))
        params = {
            "MarketplaceIds": ",".join(marketplace_ids),
            "OrderStatuses": ",".join(statuses),
            "CreatedAfter": iso_utc(created_after),
        }
        orders: list[NormalizedOrder] = []
        while True:
            data = await self._spapi_request("GET", path, params=params)
            payload = response_data(data)
            rows = [item for item in as_list(first_value(payload.get("Orders"), payload.get("orders"))) if isinstance(item, dict)] if isinstance(payload, dict) else []
            for row in rows:
                order_id = str(first_value(row.get("AmazonOrderId"), row.get("amazonOrderId")) or "")
                if bool(self.settings.get("fetch_order_items", True)) and order_id:
                    row["OrderItems"] = await self._get_order_items(order_id)
                address = await self._get_order_address(order_id) if order_id else {}
                if address:
                    row["ShippingAddress"] = first_value(address.get("ShippingAddress"), address.get("shippingAddress"), address)
                normalized = self._normalize_order(row)
                if normalized:
                    orders.append(normalized)
            next_token = payload.get("NextToken") if isinstance(payload, dict) else ""
            if not next_token:
                break
            params = {"NextToken": next_token}
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for order_id in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            path = str(self.settings.get("order_detail_path") or f"/orders/v0/orders/{order_id}")
            path = path.format(order_id=order_id)
            data = await self._spapi_request("GET", path)
            payload = response_data(data)
            row = payload if isinstance(payload, dict) else {}
            if bool(self.settings.get("fetch_order_items_for_status", False)):
                row["OrderItems"] = await self._get_order_items(order_id)
            normalized = self._normalize_order(row)
            if not normalized:
                continue
            updates.append(
                OrderStatusUpdate(
                    posting_number=normalized.posting_number,
                    platform_order_id=normalized.platform_order_id,
                    platform_order_no=normalized.platform_order_no,
                    platform_status=normalized.platform_status,
                    shipment_tracking_number=str(normalized.raw_payload.get("shipment_tracking_number") or ""),
                    raw_payload=normalized.raw_payload,
                )
            )
        return updates

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        if self._dry_run():
            return ShipmentResult(order.platform_order_id, str(order.raw_payload.get("tracking_number") or order.platform_order_id), "Amazon", "dry_run_created", order.raw_payload)
        path = str(self.settings.get("confirm_shipment_path") or "/orders/v0/orders/{order_id}/shipmentConfirmation").format(order_id=order.platform_order_id)
        payload = dict(self.settings.get("confirm_shipment_payload_template") or {})
        payload.setdefault("marketplaceId", first_value(order.raw_payload.get("MarketplaceId"), self.settings.get("marketplace_ids", [""])[0] if self.settings.get("marketplace_ids") else ""))
        payload.setdefault("packageDetail", {})
        payload["packageDetail"].setdefault("packageReferenceId", order.platform_order_id)
        payload["packageDetail"].setdefault("carrierCode", self.settings.get("carrier_code", "Other"))
        payload["packageDetail"].setdefault("carrierName", self.settings.get("carrier_name", "Seller Shipping"))
        payload["packageDetail"].setdefault("trackingNumber", first_value(order.raw_payload.get("tracking_number"), order.platform_order_id))
        data = await self._spapi_request("POST", path, json_body=payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=order.platform_order_id,
            tracking_number=str(payload["packageDetail"].get("trackingNumber") or order.platform_order_id),
            carrier=str(first_value(payload["packageDetail"].get("carrierName"), payload["packageDetail"].get("carrierCode"), "Amazon")),
            status=str(first_value(raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("Amazon Label Preview", shipment, order)
        path_template = str(self.settings.get("merchant_fulfillment_label_path") or "/mfn/v0/shipments/{shipment_id}")
        path = path_template.format(shipment_id=shipment.platform_shipment_id or order.platform_order_id, order_id=order.platform_order_id)
        data = await self._spapi_request("GET", path, binary=bool(self.settings.get("label_binary_response", False)))
        return label_from_platform_response(data)
